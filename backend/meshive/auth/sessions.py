import hashlib
import secrets
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from meshive.config import Settings
from meshive.models.session import UserSession
from meshive.models.user import User


def utc_now() -> datetime:
    return datetime.utcnow()


def hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_user_session(
    session: Session, user: User, settings: Settings
) -> tuple[str, UserSession]:
    raw_token = secrets.token_urlsafe(48)
    now = utc_now()
    record = UserSession(
        token_hash=hash_session_token(raw_token),
        user=user,
        expires_at=now + timedelta(days=settings.session_lifetime_days),
        last_used_at=now,
    )
    session.add(record)
    return raw_token, record
