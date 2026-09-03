import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from meshive.api.auth import set_session_cookie
from meshive.auth.passwords import hash_password
from meshive.auth.rate_limit import setup_limiter
from meshive.auth.sessions import create_user_session, utc_now
from meshive.config import Settings, get_settings
from meshive.database import get_session
from meshive.models.user import User
from meshive.repositories.roles import get_system_role_for_legacy_role
from meshive.repositories.users import count_users, normalize_username
from meshive.schemas.setup import InitialAdminCreate, SetupStatus
from meshive.schemas.user import UserRead

router = APIRouter(prefix="/setup", tags=["initial setup"])


@router.get("/status", response_model=SetupStatus)
def setup_status(
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> SetupStatus:
    return SetupStatus(
        required=count_users(session) == 0,
        enabled=settings.effective_setup_token is not None,
    )


@router.post("", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def create_initial_admin(
    payload: InitialAdminCreate,
    request: Request,
    response: Response,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> User:
    rate_limit_key = "initial-setup"
    retry_after = setup_limiter.retry_after(
        rate_limit_key,
        limit=settings.auth_rate_limit_attempts,
        window_seconds=settings.auth_rate_limit_window_seconds,
    )
    if retry_after is not None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many setup attempts; try again later",
            headers={"Retry-After": str(retry_after)},
        )

    expected_token = settings.effective_setup_token
    if expected_token is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Web setup is disabled; configure MESHIVE_SETUP_TOKEN or use the CLI",
        )

    if not secrets.compare_digest(payload.setup_token, expected_token):
        setup_limiter.record_failure(
            rate_limit_key,
            window_seconds=settings.auth_rate_limit_window_seconds,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The setup token is invalid",
        )

    # Serialize first-user creation so two simultaneous requests cannot both win.
    session.execute(text("BEGIN IMMEDIATE"))
    if count_users(session) != 0:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Initial setup has already been completed",
        )

    user = User(
        username=payload.username,
        normalized_username=normalize_username(payload.username),
        password_hash=hash_password(payload.password),
        role="admin",
        role_definition=get_system_role_for_legacy_role(session, "admin"),
        all_sources=True,
        is_active=True,
        last_login_at=utc_now(),
    )
    session.add(user)
    try:
        session.flush()
        raw_token, _record = create_user_session(
            session, user, settings, request.headers.get("user-agent")
        )
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Initial setup has already been completed",
        ) from error
    session.refresh(user)
    setup_limiter.clear(rate_limit_key)
    set_session_cookie(response, raw_token, settings)
    return user
