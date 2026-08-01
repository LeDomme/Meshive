import hashlib
import secrets
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from meshive.auth.user_agents import parse_user_agent
from meshive.config import Settings
from meshive.models.session import UserSession
from meshive.models.user import User


def utc_now() -> datetime:
    return datetime.utcnow()


def hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_user_session(
    session: Session,
    user: User,
    settings: Settings,
    user_agent: str | None = None,
) -> tuple[str, UserSession]:
    raw_token = secrets.token_urlsafe(48)
    now = utc_now()
    client = parse_user_agent(user_agent)
    record = UserSession(
        token_hash=hash_session_token(raw_token),
        user=user,
        expires_at=now + timedelta(days=settings.session_lifetime_days),
        last_used_at=now,
        browser=client.browser,
        operating_system=client.operating_system,
        device_type=client.device_type,
    )
    session.add(record)
    return raw_token, record


def public_session_id(token_hash: str) -> str:
    """Create a stable public identifier that does not expose the token hash."""
    value = f"meshive-session-id:{token_hash}"
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]
