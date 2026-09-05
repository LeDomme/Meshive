from meshive.auth.passwords import hash_password
from meshive.auth.permissions import CATALOGUE_VIEW, ROLES_MANAGE, USERS_MANAGE
from meshive.models.audit import AuditEvent
from meshive.models.authorization import Role, RolePermission, UserLibrarySource
from meshive.models.library_source import LibrarySource
from meshive.models.user import User
from meshive.repositories.roles import ensure_system_roles
from tests.test_auth import authenticated_test_client


def _admin_client():
    return authenticated_test_client()


def _add_admin(sessions):
    with sessions() as session:
        ensure_system_roles(session)
        administrator = next(
            role for role in session.query(Role) if role.name == "Administrator"
        )
        user = User(
            username="Admin",
            normalized_username="admin",
            password_hash=hash_password("correct horse battery staple"),
            role="admin",
            role_definition=administrator,
            all_sources=True,
            is_active=True,
        )
        session.add(user)
        session.commit()


def test_custom_role_crud_rejects_invalid_permissions_and_system_roles() -> None:
    with _admin_client() as (client, sessions):
        _add_admin(sessions)
        assert client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "correct horse battery staple"},
        ).status_code == 200

        roles = client.get("/api/admin/roles")
        assert roles.status_code == 200
        assert [role["name"] for role in roles.json()] == [
            "Administrator",
            "Curator",
            "Member",
            "Operator",
            "Viewer",
        ]
        assert client.post(
            "/api/admin/roles",
            json={"name": "Invalid", "permission_keys": ["unknown.permission"]},
        ).status_code == 422
        assert client.post(
            "/api/admin/roles",
            json={"name": "Duplicate", "permission_keys": [CATALOGUE_VIEW, CATALOGUE_VIEW]},
        ).status_code == 422
        created = client.post(
            "/api/admin/roles",
            json={"name": "Limited", "permission_keys": [CATALOGUE_VIEW]},
        )
        assert created.status_code == 201
        role_id = created.json()["id"]
        assert created.json()["permission_keys"] == [CATALOGUE_VIEW]
        assert client.put(
            f"/api/admin/roles/{roles.json()[0]['id']}",
            json={"name": "Changed", "permission_keys": []},
        ).status_code == 409
        assert client.delete(f"/api/admin/roles/{role_id}").status_code == 204
        with sessions() as session:
            events = session.query(AuditEvent).order_by(AuditEvent.id).all()
            assert [event.action for event in events] == ["role.created", "role.deleted"]
            assert all("correct horse" not in str(event.details) for event in events)


def test_user_access_assignments_are_validated_and_hidden_grants_are_cleared() -> None:
    with _admin_client() as (client, sessions):
        _add_admin(sessions)
        with sessions() as session:
            source_a = LibrarySource(name="A", root_path="/a", directory_pattern="{model}")
            source_b = LibrarySource(name="B", root_path="/b", directory_pattern="{model}")
            session.add_all([source_a, source_b])
            session.commit()
            source_a_id, source_b_id = source_a.id, source_b.id
            member = next(role for role in session.query(Role) if role.name == "Member")
            member_id = member.id
        assert client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "correct horse battery staple"},
        ).status_code == 200

        duplicate = client.post(
            "/api/admin/users",
            json={
                "username": "Duplicate", "password": "a sufficiently long password",
                "role_id": member_id, "all_sources": False,
                "source_ids": [source_a_id, source_a_id], "is_active": True,
            },
        )
        assert duplicate.status_code == 422
        selected = client.post(
            "/api/admin/users",
            json={
                "username": "Selected", "password": "a sufficiently long password",
                "role_id": member_id, "all_sources": False,
                "source_ids": [source_a_id], "is_active": True,
            },
        )
        assert selected.status_code == 201
        assert selected.json()["source_ids"] == [source_a_id]
        user_id = selected.json()["id"]
        all_sources = client.put(
            f"/api/admin/users/{user_id}",
            json={
                "username": "Selected", "role_id": member_id, "all_sources": True,
                "source_ids": [source_b_id], "is_active": True,
                "must_change_password": False,
            },
        )
        assert all_sources.status_code == 200
        assert all_sources.json()["source_ids"] == []
        with sessions() as session:
            assert not session.query(UserLibrarySource).filter_by(user_id=user_id).count()
            events = session.query(AuditEvent).order_by(AuditEvent.id).all()
            assert "user.created" in [event.action for event in events]
            assert "user.source_access_changed" in [event.action for event in events]
            assert all("sufficiently long password" not in str(event.details) for event in events)
            assert all("@" not in f"{event.actor_username} {event.target_label} {event.details}" for event in events)


def test_user_create_defaults_to_legacy_member_role_without_role_selection() -> None:
    with _admin_client() as (client, sessions):
        _add_admin(sessions)
        assert client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "correct horse battery staple"},
        ).status_code == 200
        created = client.post(
            "/api/admin/users",
            json={
                "username": "Default member",
                "password": "a sufficiently long password",
                "is_active": True,
            },
        )
        assert created.status_code == 201
        assert created.json()["role"] == "user"
        assert created.json()["role_definition"]["name"] == "Member"
        assert created.json()["all_sources"] is True


def test_last_system_superuser_cannot_be_demoted_or_deleted() -> None:
    with _admin_client() as (client, sessions):
        _add_admin(sessions)
        assert client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "correct horse battery staple"},
        ).status_code == 200
        with sessions() as session:
            admin = session.query(User).filter_by(normalized_username="admin").one()
            member = next(role for role in session.query(Role) if role.name == "Member")
            admin_id, member_id = admin.id, member.id
        assert client.delete(f"/api/admin/users/{admin_id}").status_code == 409
        response = client.put(
            f"/api/admin/users/{admin_id}",
            json={
                "username": "Admin", "role_id": member_id, "all_sources": True,
                "source_ids": [], "is_active": True, "must_change_password": False,
            },
        )
        assert response.status_code == 409


def test_management_requires_permission_and_all_sources_and_rejects_assigned_role() -> None:
    with _admin_client() as (client, sessions):
        _add_admin(sessions)
        with sessions() as session:
            session.add(
                LibrarySource(name="Picker source", root_path="/picker", directory_pattern="{model}")
            )
            roles_manager = Role(
                name="Roles manager",
                normalized_name="roles manager",
                permissions=[RolePermission(permission_key=ROLES_MANAGE)],
            )
            users_manager = Role(
                name="Users manager",
                normalized_name="users manager",
                permissions=[RolePermission(permission_key=USERS_MANAGE)],
            )
            restricted = User(
                username="Restricted",
                normalized_username="restricted",
                password_hash=hash_password("correct horse battery staple"),
                role="user",
                role_definition=roles_manager,
                all_sources=False,
                is_active=True,
            )
            manager = User(
                username="Manager",
                normalized_username="manager",
                password_hash=hash_password("correct horse battery staple"),
                role="user",
                role_definition=users_manager,
                all_sources=True,
                is_active=True,
            )
            restricted_user_manager = User(
                username="Restricted user manager",
                normalized_username="restricted user manager",
                password_hash=hash_password("correct horse battery staple"),
                role="user",
                role_definition=users_manager,
                all_sources=False,
                is_active=True,
            )
            session.add_all(
                [roles_manager, users_manager, restricted, manager, restricted_user_manager]
            )
            session.commit()
            users_manager_id = users_manager.id

        assert client.post(
            "/api/auth/login",
            json={"username": "restricted", "password": "correct horse battery staple"},
        ).status_code == 200
        assert client.get("/api/admin/roles").status_code == 403
        assert client.get("/api/admin/users/library-sources").status_code == 403
        client.post("/api/auth/logout")
        assert client.post(
            "/api/auth/login",
            json={
                "username": "restricted user manager",
                "password": "correct horse battery staple",
            },
        ).status_code == 200
        assert client.get("/api/admin/users/library-sources").status_code == 403
        client.post("/api/auth/logout")
        assert client.post(
            "/api/auth/login",
            json={"username": "manager", "password": "correct horse battery staple"},
        ).status_code == 200
        assert client.get("/api/admin/roles").status_code == 403
        assert client.get("/api/admin/users").status_code == 200
        picker = client.get("/api/admin/users/library-sources")
        assert picker.status_code == 200
        assert picker.json() == [{"id": 1, "name": "Picker source"}]
        assert client.get("/api/admin/library-sources").status_code == 403
        assert client.post(
            "/api/admin/users",
            json={
                "username": "Unknown role", "password": "a sufficiently long password",
                "role_id": 99999, "all_sources": True, "source_ids": [], "is_active": True,
            },
        ).status_code == 404
        created = client.post(
            "/api/admin/users",
            json={
                "username": "Assigned", "password": "a sufficiently long password",
                "role_id": users_manager_id, "all_sources": False, "source_ids": [], "is_active": True,
            },
        )
        assert created.status_code == 201
        client.post("/api/auth/logout")
        assert client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "correct horse battery staple"},
        ).status_code == 200
        assert client.delete(f"/api/admin/roles/{users_manager_id}").status_code == 409
        assert client.get("/api/admin/users/library-sources").status_code == 200
