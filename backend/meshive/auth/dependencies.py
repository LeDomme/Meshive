from datetime import timedelta

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from meshive.auth.sessions import hash_session_token, utc_now
from meshive.config import get_settings
from meshive.database import get_session
from meshive.models.session import UserSession
from meshive.models.user import User


def get_current_session_allow_password_change(
    request: Request, session: Session = Depends(get_session)
) -> UserSession:
    settings = get_settings()
    raw_token = request.cookies.get(settings.session_cookie_name)
    if not raw_token:
        raise _authentication_error()

    record = session.get(UserSession, hash_session_token(raw_token))
    now = utc_now()
    if record is None or record.expires_at <= now or not record.user.is_active:
        if record is not None:
            session.delete(record)
            session.commit()
        raise _authentication_error()

    if record.last_used_at <= now - timedelta(minutes=15):
        record.last_used_at = now
        session.commit()

    return record


def get_current_user_allow_password_change(
    record: UserSession = Depends(get_current_session_allow_password_change),
) -> User:
    return record.user


def get_current_user(
    user: User = Depends(get_current_user_allow_password_change),
) -> User:
    if user.must_change_password:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Password change is required",
        )
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator access is required",
        )
    return user


def _authentication_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication is required",
    )
