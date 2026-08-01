from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import delete
from sqlalchemy.orm import Session

from meshive.auth.dependencies import (
    get_current_user_allow_password_change,
)
from meshive.auth.passwords import DUMMY_HASH, hash_password, verify_password
from meshive.auth.rate_limit import login_limiter
from meshive.auth.sessions import create_user_session, hash_session_token, utc_now
from meshive.config import Settings, get_settings
from meshive.database import get_session
from meshive.models.session import UserSession
from meshive.models.user import User
from meshive.repositories.users import get_user_by_username, normalize_username
from meshive.schemas.user import LoginRequest, PasswordChange, UserRead

router = APIRouter(prefix="/auth", tags=["authentication"])


@router.post("/login", response_model=UserRead)
def login(
    payload: LoginRequest,
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
    raw_token, _record = create_user_session(session, user, settings)
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
