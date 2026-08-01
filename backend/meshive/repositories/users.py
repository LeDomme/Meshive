from sqlalchemy import func, select
from sqlalchemy.orm import Session

from meshive.models.user import User


def normalize_username(username: str) -> str:
    return username.strip().casefold()


def normalize_email(email: str) -> str:
    return email.strip().casefold()


def get_user(session: Session, user_id: int) -> User | None:
    return session.get(User, user_id)


def get_user_by_username(session: Session, username: str) -> User | None:
    statement = select(User).where(
        User.normalized_username == normalize_username(username)
    )
    return session.scalar(statement)


def get_user_by_recovery_identifier(
    session: Session, identifier: str
) -> User | None:
    normalized = identifier.strip().casefold()
    user = session.scalar(
        select(User).where(
            User.normalized_email == normalized,
            User.email_verified_at.is_not(None),
        )
    )
    if user is not None:
        return user
    return session.scalar(select(User).where(User.normalized_username == normalized))


def list_users(session: Session) -> list[User]:
    return list(session.scalars(select(User).order_by(User.normalized_username)))


def count_active_admins(session: Session) -> int:
    statement = select(func.count()).select_from(User).where(
        User.role == "admin", User.is_active.is_(True)
    )
    return int(session.scalar(statement) or 0)


def count_users(session: Session) -> int:
    statement = select(func.count()).select_from(User)
    return int(session.scalar(statement) or 0)
