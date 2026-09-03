from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from meshive.auth.permissions import SYSTEM_ROLE_DEFINITIONS
from meshive.config import get_settings


def test_role_migration_preserves_existing_admin_and_user_access(tmp_path, monkeypatch) -> None:
    database_path = tmp_path / "role-migration.sqlite3"
    database_url = f"sqlite:///{database_path.as_posix()}"
    monkeypatch.setenv("MESHIVE_DATABASE_URL", database_url)
    get_settings.cache_clear()
    config = Config("backend/alembic.ini")
    try:
        command.upgrade(config, "20260901_33")
        engine = create_engine(database_url)
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO users "
                    "(username, normalized_username, password_hash, role, is_active, must_change_password) "
                    "VALUES "
                    "('Admin', 'admin', 'unused', 'admin', 1, 0), "
                    "('Member', 'member', 'unused', 'user', 1, 0)"
                )
            )
        engine.dispose()

        command.upgrade(config, "head")
        engine = create_engine(database_url)
        with engine.connect() as connection:
            users = connection.execute(
                text(
                    "SELECT users.username, users.role, roles.name, users.all_sources "
                    "FROM users JOIN roles ON roles.id = users.role_id "
                    "ORDER BY users.id"
                )
            ).all()
            roles = connection.execute(
                text("SELECT name, is_system, is_superuser FROM roles ORDER BY id")
            ).all()
            permission_rows = connection.execute(
                text(
                    "SELECT roles.name, role_permissions.permission_key "
                    "FROM role_permissions JOIN roles ON roles.id = role_permissions.role_id"
                )
            ).all()
            foreign_keys = connection.execute(text("PRAGMA foreign_key_list(users)")).all()
        engine.dispose()

        assert users == [("Admin", "admin", "Administrator", 1), ("Member", "user", "Member", 1)]
        assert roles == [
            ("Viewer", 1, 0),
            ("Member", 1, 0),
            ("Curator", 1, 0),
            ("Operator", 1, 0),
            ("Administrator", 1, 1),
        ]
        assert {
            name: {permission for role_name, permission in permission_rows if role_name == name}
            for name in {definition.name for definition in SYSTEM_ROLE_DEFINITIONS}
        } == {
            definition.name: set(definition.permission_keys)
            for definition in SYSTEM_ROLE_DEFINITIONS
        }
        assert any(foreign_key[2] == "roles" for foreign_key in foreign_keys)

        command.downgrade(config, "20260901_33")
        command.upgrade(config, "head")
        engine = create_engine(database_url)
        with engine.connect() as connection:
            repeated_users = connection.execute(
                text(
                    "SELECT users.username, roles.name, users.all_sources "
                    "FROM users JOIN roles ON roles.id = users.role_id "
                    "ORDER BY users.id"
                )
            ).all()
        engine.dispose()
        assert repeated_users == [("Admin", "Administrator", 1), ("Member", "Member", 1)]
    finally:
        get_settings.cache_clear()
