from sqlalchemy import select
from sqlalchemy.orm import Session

from meshive.auth.permissions import (
    SYSTEM_ROLE_DEFINITIONS,
    normalize_role_name,
    system_role_name_for_legacy_role,
)
from meshive.models.authorization import Role, RolePermission


def ensure_system_roles(session: Session) -> None:
    existing = {
        role.normalized_name: role
        for role in session.scalars(select(Role)).all()
    }
    for definition in SYSTEM_ROLE_DEFINITIONS:
        normalized_name = normalize_role_name(definition.name)
        role = existing.get(normalized_name)
        if role is None:
            role = Role(
                name=definition.name,
                normalized_name=normalized_name,
                description=definition.description,
                is_system=True,
                is_superuser=definition.is_superuser,
            )
            session.add(role)
            session.flush()
        existing_permissions = set(
            session.scalars(
                select(RolePermission.permission_key).where(RolePermission.role_id == role.id)
            )
        )
        for permission_key in definition.permission_keys - existing_permissions:
            session.add(RolePermission(role_id=role.id, permission_key=permission_key))


def get_system_role_for_legacy_role(session: Session, legacy_role: str) -> Role:
    ensure_system_roles(session)
    normalized_name = normalize_role_name(system_role_name_for_legacy_role(legacy_role))
    role = session.scalar(select(Role).where(Role.normalized_name == normalized_name))
    if role is None:
        raise RuntimeError("Required system role is missing")
    return role
