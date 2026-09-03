import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from meshive.auth.access import (
    can_access_source,
    get_access_context,
    get_visible_source_ids,
    require_permission,
)
from meshive.auth.permissions import ALL_PERMISSION_KEYS, CATALOGUE_VIEW
from meshive.database import Base
from meshive.models.authorization import Role, RolePermission, UserLibrarySource
from meshive.models.library_source import LibrarySource
from meshive.models.user import User
from meshive.repositories.roles import ensure_system_roles


def test_access_context_uses_current_role_permissions_and_source_grants() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as session:
            role = Role(name="Limited", normalized_name="limited")
            user = User(
                username="Limited user",
                normalized_username="limited user",
                password_hash="unused",
                role="user",
                role_definition=role,
                all_sources=False,
            )
            source = LibrarySource(
                name="Limited source",
                root_path="/library/limited",
                directory_pattern="{creator}/{model}",
            )
            session.add_all(
                [
                    role,
                    user,
                    source,
                    RolePermission(role=role, permission_key=CATALOGUE_VIEW),
                    RolePermission(role=role, permission_key="future.permission"),
                ]
            )
            session.flush()
            source_id = source.id
            session.add(UserLibrarySource(user=user, library_source_id=source.id))
            session.commit()

            access = get_access_context(session, user)

        assert access.permission_keys == frozenset({CATALOGUE_VIEW})
        assert access.source_ids == frozenset({source_id})
        assert access.all_sources is False
        assert can_access_source(access, source_id) is True
        assert can_access_source(access, source_id + 1) is False
        assert get_visible_source_ids(access) == {source_id}
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_superuser_access_context_has_all_permissions_and_sources() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as session:
            administrator = Role(
                name="Administrator",
                normalized_name="administrator",
                is_system=True,
                is_superuser=True,
            )
            user = User(
                username="Admin",
                normalized_username="admin",
                password_hash="unused",
                role="admin",
                role_definition=administrator,
                all_sources=False,
            )
            session.add_all([administrator, user])
            session.commit()

            access = get_access_context(session, user)

        assert access.permission_keys == ALL_PERMISSION_KEYS
        assert access.all_sources is True
        assert access.source_ids == frozenset()
        assert can_access_source(access, 999) is True
        assert get_visible_source_ids(access) is None
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_all_source_access_ignores_explicit_source_grants() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as session:
            role = Role(name="Member", normalized_name="member")
            user = User(
                username="Member",
                normalized_username="member",
                password_hash="unused",
                role="user",
                role_definition=role,
                all_sources=True,
            )
            source = LibrarySource(
                name="All sources grant",
                root_path="/library/all-sources",
                directory_pattern="{creator}/{model}",
            )
            session.add_all([role, user, source])
            session.flush()
            session.add(UserLibrarySource(user=user, library_source_id=source.id))
            session.commit()

            access = get_access_context(session, user)

        assert access.source_ids == frozenset()
        assert get_visible_source_ids(access) is None
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_require_permission_rejects_unknown_registry_keys() -> None:
    with pytest.raises(ValueError, match="Unknown permission key"):
        require_permission("unknown.permission")


def test_system_roles_are_created_for_a_fresh_database() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as session:
            ensure_system_roles(session)
            session.commit()
            roles = list(session.query(Role).order_by(Role.id))
            assert [role.name for role in roles] == [
                "Viewer",
                "Member",
                "Curator",
                "Operator",
                "Administrator",
            ]
            assert roles[-1].is_superuser is True
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_system_role_permission_matrix_matches_registry() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as session:
            ensure_system_roles(session)
            session.commit()
            permissions_by_role = {
                role.name: {permission.permission_key for permission in role.permissions}
                for role in session.query(Role).all()
            }

        from meshive.auth.permissions import SYSTEM_ROLE_DEFINITIONS

        assert permissions_by_role == {
            definition.name: set(definition.permission_keys)
            for definition in SYSTEM_ROLE_DEFINITIONS
        }
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()
