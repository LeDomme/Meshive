from dataclasses import dataclass

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from meshive.auth.dependencies import get_current_user
from meshive.auth.permissions import ALL_PERMISSION_KEYS
from meshive.database import get_session
from meshive.models.authorization import RolePermission, UserLibrarySource
from meshive.models.user import User

CURRENT_USER_DEPENDENCY = Depends(get_current_user)
SESSION_DEPENDENCY = Depends(get_session)


@dataclass(frozen=True)
class AccessContext:
    user: User
    permission_keys: frozenset[str]
    all_sources: bool
    source_ids: frozenset[int]
    is_superuser: bool


def get_access_context(session: Session, user: User) -> AccessContext:
    role = user.role_definition
    is_superuser = bool(role and role.is_superuser)
    if is_superuser:
        permission_keys = ALL_PERMISSION_KEYS
    elif user.role_id is None:
        permission_keys = frozenset()
    else:
        permission_keys = frozenset(
            key
            for key in session.scalars(
                select(RolePermission.permission_key).where(RolePermission.role_id == user.role_id)
            )
            if key in ALL_PERMISSION_KEYS
        )
    all_sources = bool(user.all_sources) or is_superuser
    source_ids = (
        frozenset()
        if all_sources or is_superuser
        else frozenset(
            session.scalars(
                select(UserLibrarySource.library_source_id).where(
                    UserLibrarySource.user_id == user.id
                )
            )
        )
    )
    return AccessContext(
        user=user,
        permission_keys=permission_keys,
        all_sources=all_sources,
        source_ids=source_ids,
        is_superuser=is_superuser,
    )


def can_access_source(access: AccessContext, source_id: int) -> bool:
    return access.is_superuser or access.all_sources or source_id in access.source_ids


def get_visible_source_ids(access: AccessContext) -> set[int] | None:
    if access.is_superuser or access.all_sources:
        return None
    return set(access.source_ids)


def require_permission(permission_key: str):
    if permission_key not in ALL_PERMISSION_KEYS:
        raise ValueError(f"Unknown permission key: {permission_key}")

    def dependency(
        user: User = CURRENT_USER_DEPENDENCY,
        session: Session = SESSION_DEPENDENCY,
    ) -> AccessContext:
        access = get_access_context(session, user)
        if permission_key not in access.permission_keys:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Permission denied",
            )
        return access

    return dependency
