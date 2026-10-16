from datetime import timedelta

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from meshive.auth.api_tokens import TOKEN_PREFIX, hash_api_token
from meshive.auth.sessions import hash_session_token, utc_now
from meshive.config import get_settings
from meshive.database import get_session
from meshive.models.api_token import ApiToken
from meshive.models.session import UserSession
from meshive.models.user import User


def _get_current_session(request: Request, session: Session) -> UserSession:
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
        try:
            session.commit()
        except OperationalError:
            # Session activity is best-effort. A concurrent catalogue scan must
            # never turn an otherwise valid authenticated request into a 500.
            session.rollback()

    return record


def get_current_session_allow_password_change(
    request: Request, session: Session = Depends(get_session)
) -> UserSession:
    return _get_current_session(request, session)


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


def get_current_user_or_api_token(
    request: Request,
    session: Session = Depends(get_session),
) -> User:
    authorization = request.headers.get("authorization")
    if authorization is None:
        user = _get_current_session(request, session).user
        if user.must_change_password:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Password change is required",
            )
        return user

    scheme, separator, raw_token = authorization.partition(" ")
    if (
        not separator
        or scheme.casefold() != "bearer"
        or not raw_token.startswith(TOKEN_PREFIX)
    ):
        raise _authentication_error()

    token = session.scalar(
        select(ApiToken).where(ApiToken.token_hash == hash_api_token(raw_token))
    )
    now = utc_now()
    if (
        token is None
        or (token.expires_at is not None and token.expires_at <= now)
        or not token.user.is_active
        or token.user.must_change_password
    ):
        raise _authentication_error()

    if token.last_used_at is None or token.last_used_at <= now - timedelta(minutes=15):
        token.last_used_at = now
        try:
            session.commit()
        except OperationalError:
            # Token activity is best-effort and must not break a valid request.
            session.rollback()

    return token.user


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
