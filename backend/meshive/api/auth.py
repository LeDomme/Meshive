import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Request, Response, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from meshive.auth.action_tokens import delete_user_action_tokens
from meshive.auth.dependencies import (
    get_current_session_allow_password_change,
    get_current_user_allow_password_change,
)
from meshive.auth.passwords import DUMMY_HASH, hash_password, verify_password
from meshive.auth.rate_limit import login_limiter
from meshive.auth.sessions import (
    create_user_session,
    hash_session_token,
    public_session_id,
    utc_now,
)
from meshive.config import Settings, get_settings
from meshive.database import get_session
from meshive.models.session import UserSession
from meshive.models.user import User
from meshive.repositories.users import get_user_by_username, normalize_username
from meshive.schemas.user import (
    LoginRequest,
    PasswordChange,
    SessionRevocationResult,
    UserRead,
    UserSessionRead,
)

router = APIRouter(prefix="/auth", tags=["authentication"])


@router.post("/login", response_model=UserRead)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> User:
    rate_limit_key = normalize_username(payload.username)
    retry_after = login_limiter.retry_after(
        rate_limit_key,
        limit=settings.auth_rate_limit_attempts,
        window_seconds=settings.auth_rate_limit_window_seconds,
    )
    if retry_after is not None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many sign-in attempts; try again later",
            headers={"Retry-After": str(retry_after)},
        )

    user = get_user_by_username(session, payload.username)
    encoded_hash = user.password_hash if user is not None else DUMMY_HASH
    password_valid = verify_password(payload.password, encoded_hash)
    if user is None or not password_valid or not user.is_active:
        login_limiter.record_failure(
            rate_limit_key,
            window_seconds=settings.auth_rate_limit_window_seconds,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    login_limiter.clear(rate_limit_key)
    raw_token, _record = create_user_session(
        session, user, settings, request.headers.get("user-agent")
    )
    user.last_login_at = utc_now()
    session.commit()

    set_session_cookie(response, raw_token, settings)
    return user


def set_session_cookie(response: Response, raw_token: str, settings: Settings) -> None:
    response.set_cookie(
        key=settings.session_cookie_name,
        value=raw_token,
        max_age=settings.session_lifetime_days * 24 * 60 * 60,
        path="/",
        secure=settings.secure_cookies,
        httponly=True,
        samesite="strict",
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request,
    response: Response,
    session: Session = Depends(get_session),
) -> Response:
    settings = get_settings()
    raw_token = request.cookies.get(settings.session_cookie_name)
    if raw_token:
        record = session.get(UserSession, hash_session_token(raw_token))
        if record is not None:
            session.delete(record)
            session.commit()
    response.delete_cookie(
        key=settings.session_cookie_name,
        path="/",
        secure=settings.secure_cookies,
        httponly=True,
        samesite="strict",
    )
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/me", response_model=UserRead)
def current_user(
    user: User = Depends(get_current_user_allow_password_change),
) -> User:
    return user


@router.get("/sessions", response_model=list[UserSessionRead])
def list_sessions(
    current: UserSession = Depends(get_current_session_allow_password_change),
    session: Session = Depends(get_session),
) -> list[UserSessionRead]:
    now = utc_now()
    session.execute(
        delete(UserSession).where(
            UserSession.user_id == current.user_id,
            UserSession.expires_at <= now,
        )
    )
    records = session.scalars(
        select(UserSession)
        .where(UserSession.user_id == current.user_id)
        .order_by(UserSession.last_used_at.desc(), UserSession.created_at.desc())
    ).all()
    session.commit()
    return [_session_response(record, current.token_hash) for record in records]


@router.delete("/sessions/others", response_model=SessionRevocationResult)
def revoke_other_sessions(
    current: UserSession = Depends(get_current_session_allow_password_change),
    session: Session = Depends(get_session),
) -> SessionRevocationResult:
    result = session.execute(
        delete(UserSession).where(
            UserSession.user_id == current.user_id,
            UserSession.token_hash != current.token_hash,
        )
    )
    session.commit()
    return SessionRevocationResult(revoked_count=result.rowcount or 0)


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_session(
    session_id: Annotated[
        str, Path(min_length=24, max_length=24, pattern=r"^[0-9a-f]{24}$")
    ],
    response: Response,
    current: UserSession = Depends(get_current_session_allow_password_change),
    session: Session = Depends(get_session),
) -> Response:
    records = session.scalars(
        select(UserSession).where(UserSession.user_id == current.user_id)
    ).all()
    record = next(
        (
            candidate
            for candidate in records
            if secrets.compare_digest(
                public_session_id(candidate.token_hash), session_id
            )
        ),
        None,
    )
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )

    is_current = record.token_hash == current.token_hash
    session.delete(record)
    session.commit()
    if is_current:
        settings = get_settings()
        response.delete_cookie(
            key=settings.session_cookie_name,
            path="/",
            secure=settings.secure_cookies,
            httponly=True,
            samesite="strict",
        )
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


def _session_response(
    record: UserSession, current_token_hash: str
) -> UserSessionRead:
    return UserSessionRead(
        id=public_session_id(record.token_hash),
        created_at=record.created_at,
        last_used_at=record.last_used_at,
        expires_at=record.expires_at,
        browser=record.browser,
        operating_system=record.operating_system,
        device_type=record.device_type,
        is_current=record.token_hash == current_token_hash,
    )


@router.post("/change-password", response_model=UserRead)
def change_password(
    payload: PasswordChange,
    request: Request,
    user: User = Depends(get_current_user_allow_password_change),
    session: Session = Depends(get_session),
) -> User:
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The current password is incorrect",
        )
    if verify_password(payload.new_password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The new password must be different",
        )
    user.password_hash = hash_password(payload.new_password)
    user.must_change_password = False
    delete_user_action_tokens(session, user.id)
    settings = get_settings()
    current_token = request.cookies.get(settings.session_cookie_name)
    current_token_hash = hash_session_token(current_token) if current_token else None
    statement = delete(UserSession).where(UserSession.user_id == user.id)
    if current_token_hash is not None:
        statement = statement.where(UserSession.token_hash != current_token_hash)
    session.execute(statement)
    session.commit()
    session.refresh(user)
    return user
