import io
from datetime import timedelta

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from meshive import cli
from meshive.auth.action_tokens import PASSWORD_RESET, hash_action_token
from meshive.auth.passwords import hash_password, verify_password
from meshive.auth.sessions import hash_session_token, utc_now
from meshive.database import Base
from meshive.models.session import UserSession
from meshive.models.user import User
from meshive.models.user_token import UserActionToken


def test_cli_password_reset_revokes_sessions_and_tokens(
    tmp_path, monkeypatch
) -> None:
    engine = create_engine(f"sqlite:///{(tmp_path / 'cli.sqlite3').as_posix()}")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    with sessions() as session:
        user = User(
            username="Admin",
            normalized_username="admin",
            password_hash=hash_password("the previous admin password"),
            role="admin",
            is_active=True,
        )
        session.add(user)
        session.flush()
        session.add(
            UserSession(
                token_hash=hash_session_token("active-session"),
                user_id=user.id,
                expires_at=utc_now() + timedelta(days=1),
                last_used_at=utc_now(),
            )
        )
        session.add(
            UserActionToken(
                token_hash=hash_action_token("pending-reset-token"),
                user_id=user.id,
                purpose=PASSWORD_RESET,
                expires_at=utc_now() + timedelta(minutes=30),
            )
        )
        session.commit()

    monkeypatch.setattr(cli, "SessionLocal", sessions)
    monkeypatch.setattr(
        cli.sys, "stdin", io.StringIO("the replacement admin password\n")
    )
    cli._reset_password("admin", password_stdin=True)

    with sessions() as session:
        user = session.scalar(select(User).where(User.normalized_username == "admin"))
        assert user is not None
        assert verify_password("the replacement admin password", user.password_hash)
        assert session.scalar(select(func.count()).select_from(UserSession)) == 0
        assert session.scalar(select(func.count()).select_from(UserActionToken)) == 0
    engine.dispose()
