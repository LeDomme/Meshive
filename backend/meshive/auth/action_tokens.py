import hashlib
import secrets
from datetime import timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from meshive.auth.sessions import utc_now
from meshive.models.user import User
from meshive.models.user_token import UserActionToken

PASSWORD_RESET = "password_reset"
EMAIL_VERIFICATION = "email_verification"


def hash_action_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def issue_action_token(
    session: Session,
    user: User,
    *,
    purpose: str,
    lifetime: timedelta,
    email: str | None = None,
) -> str:
    session.execute(
        delete(UserActionToken).where(
            UserActionToken.user_id == user.id,
            UserActionToken.purpose == purpose,
        )
    )
    raw_token = secrets.token_urlsafe(48)
    session.add(
        UserActionToken(
            token_hash=hash_action_token(raw_token),
            user=user,
            purpose=purpose,
            email=email,
            expires_at=utc_now() + lifetime,
        )
    )
    return raw_token


def find_action_token(
    session: Session, raw_token: str, purpose: str
) -> UserActionToken | None:
    return session.scalar(
        select(UserActionToken).where(
            UserActionToken.token_hash == hash_action_token(raw_token),
            UserActionToken.purpose == purpose,
        )
    )


def delete_user_action_tokens(session: Session, user_id: int) -> None:
    session.execute(
        delete(UserActionToken).where(UserActionToken.user_id == user_id)
    )
