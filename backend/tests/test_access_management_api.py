from datetime import UTC, datetime

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


def test_audit_events_cover_role_and_user_mutations_without_sensitive_values() -> None:
    with _admin_client() as (client, sessions):
        _add_admin(sessions)
        with sessions() as session:
            session.add_all([
                LibrarySource(name="A", root_path="/private/a", directory_pattern="{model}"),
                LibrarySource(name="B", root_path="/private/b", directory_pattern="{model}"),
            ])
            session.commit()
            source_ids = [source.id for source in session.query(LibrarySource).order_by(LibrarySource.id)]
            member_id = next(role.id for role in session.query(Role) if role.name == "Member")
            viewer_id = next(role.id for role in session.query(Role) if role.name == "Viewer")
        assert client.post("/api/auth/login", json={"username": "admin", "password": "correct horse battery staple"}).status_code == 200
        created_role = client.post("/api/admin/roles", json={"name": "Audit role", "permission_keys": [CATALOGUE_VIEW]})
        role_id = created_role.json()["id"]
        assert client.put(f"/api/admin/roles/{role_id}", json={"name": "Audited role", "permission_keys": [USERS_MANAGE]}).status_code == 200
        created_user = client.post("/api/admin/users", json={"username": "Audited", "password": "secret never audit", "role_id": member_id, "all_sources": False, "source_ids": [source_ids[0]], "is_active": True, "must_change_password": False})
        user_id = created_user.json()["id"]
        assert client.put(f"/api/admin/users/{user_id}", json={"username": "Audited", "password": "changed never audit", "role_id": viewer_id, "all_sources": True, "source_ids": source_ids, "is_active": False, "must_change_password": True}).status_code == 200
        assert client.delete(f"/api/admin/users/{user_id}").status_code == 204
        with sessions() as session:
            events = session.query(AuditEvent).order_by(AuditEvent.id).all()
            updated_role = next(event for event in events if event.action == "role.updated")
            assert set(updated_role.details) == {"permissions_added", "permissions_removed"}
            actions = {event.action for event in events}
            assert {"user.role_changed", "user.source_access_changed", "user.status_changed", "user.password_changed", "user.require_password_change_changed", "user.deleted"} <= actions
            assert "user.updated" not in actions
            deleted = next(event for event in events if event.action == "user.deleted")
            assert deleted.target_label == "Audited" and deleted.target_id == user_id
            assert session.get(User, user_id) is None
            serialized = " ".join(f"{event.actor_username} {event.target_label} {event.details}" for event in events)
            for forbidden in ("secret never audit", "changed never audit", "/private/a", "/private/b"):
                assert forbidden not in serialized


def test_failed_role_mutation_does_not_persist_an_audit_event() -> None:
    with _admin_client() as (client, sessions):
        _add_admin(sessions)
        assert client.post("/api/auth/login", json={"username": "admin", "password": "correct horse battery staple"}).status_code == 200
        assert client.post("/api/admin/roles", json={"name": "Duplicate", "permission_keys": []}).status_code == 201
        assert client.post("/api/admin/roles", json={"name": "Duplicate", "permission_keys": []}).status_code == 409
        with sessions() as session:
            assert [event.action for event in session.query(AuditEvent)] == ["role.created"]


def test_audit_event_api_paginates_filters_and_exposes_safe_snapshots() -> None:
    with _admin_client() as (client, sessions):
        _add_admin(sessions)
        with sessions() as session:
            source = LibrarySource(name="Source", root_path="/secret/path", directory_pattern="{model}")
            session.add(source)
            session.flush()
            session.add_all([
                AuditEvent(actor_username="Alice", action="role.updated", target_type="role", target_label="One", details={"safe": True}),
                AuditEvent(actor_username="Bob", action="user.updated", target_type="user", target_label="Two", library_source_id=source.id, details={"safe": True}),
            ])
            session.commit()
        assert client.post("/api/auth/login", json={"username": "admin", "password": "correct horse battery staple"}).status_code == 200
        first = client.get("/api/admin/audit-events?page=1&page_size=1")
        second = client.get("/api/admin/audit-events?page=2&page_size=1")
        assert first.status_code == second.status_code == 200
        assert first.json()["items"][0]["id"] > second.json()["items"][0]["id"]
        assert client.get("/api/admin/audit-events?action=role.updated&actor=Alice").json()["total"] == 1
        item = client.get("/api/admin/audit-events?source_id=1").json()["items"][0]
        assert item["library_source_id"] == 1 and "/secret/path" not in str(item)


def test_audit_event_api_uses_utc_time_filters_and_stable_pagination() -> None:
    with _admin_client() as (client, sessions):
        _add_admin(sessions)
        with sessions() as session:
            session.add_all([
                AuditEvent(actor_username="A", action="user.updated", target_type="user", target_label="old", created_at=datetime(2026, 1, 1, tzinfo=UTC)),
                AuditEvent(actor_username="A", action="user.updated", target_type="user", target_label="same one", created_at=datetime(2026, 1, 2, tzinfo=UTC)),
                AuditEvent(actor_username="A", action="user.updated", target_type="user", target_label="same two", created_at=datetime(2026, 1, 2, tzinfo=UTC)),
                AuditEvent(actor_username="A", action="user.updated", target_type="user", target_label="new", created_at=datetime(2026, 1, 3, tzinfo=UTC)),
            ])
            session.commit()
        assert client.post("/api/auth/login", json={"username": "admin", "password": "correct horse battery staple"}).status_code == 200
        window = client.get("/api/admin/audit-events?from_at=2026-01-02T00:00:00Z&to_at=2026-01-02T23:59:59%2B00:00")
        assert window.status_code == 200 and window.json()["total"] == 2
        assert [item["target_label"] for item in window.json()["items"]] == ["same two", "same one"]
        older_excluded = client.get("/api/admin/audit-events?from_at=2026-01-02T00:00:00Z").json()
        newer_excluded = client.get("/api/admin/audit-events?to_at=2026-01-02T23:59:59Z").json()
        assert older_excluded["total"] == 3 and newer_excluded["total"] == 3
        first = client.get("/api/admin/audit-events?page=1&page_size=2").json()["items"]
        second = client.get("/api/admin/audit-events?page=2&page_size=2").json()["items"]
        assert not {item["id"] for item in first} & {item["id"] for item in second}
        assert [item["target_label"] for item in first] == ["new", "same two"]


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
