from dataclasses import dataclass

from fastapi import Depends, HTTPException, status
from sqlalchemy import ColumnElement, Select, select
from sqlalchemy.orm import Session

from meshive.auth.dependencies import get_current_user
from meshive.auth.permissions import ALL_PERMISSION_KEYS
from meshive.database import get_session
from meshive.models.authorization import RolePermission, UserLibrarySource
from meshive.models.catalog import LibraryModel, ScanRun
from meshive.models.library_source import LibrarySource
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


def scope_models(statement: Select, access: AccessContext) -> Select:
    """Restrict a LibraryModel statement to sources visible to the user."""
    source_ids = get_visible_source_ids(access)
    return statement if source_ids is None else statement.where(
        LibraryModel.library_source_id.in_(source_ids)
    )


def visible_model_scope(access: AccessContext) -> ColumnElement[bool] | None:
    """Return the LibraryModel source predicate, or None for all sources."""
    source_ids = get_visible_source_ids(access)
    return None if source_ids is None else LibraryModel.library_source_id.in_(source_ids)


def scope_scan_runs(statement: Select, access: AccessContext) -> Select:
    """Restrict a ScanRun statement to sources visible to the user."""
    source_ids = get_visible_source_ids(access)
    return statement if source_ids is None else statement.where(
        ScanRun.library_source_id.in_(source_ids)
    )


def get_visible_model_or_404(
    session: Session, access: AccessContext, model_id: int
) -> LibraryModel:
    model = session.scalar(
        scope_models(select(LibraryModel).where(LibraryModel.id == model_id), access)
    )
    if model is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Model not found")
    return model


def get_visible_scan_or_404(session: Session, access: AccessContext, scan_id: int) -> ScanRun:
    scan = session.scalar(scope_scan_runs(select(ScanRun).where(ScanRun.id == scan_id), access))
    if scan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scan not found")
    return scan


def get_operable_source_or_404(
    session: Session, access: AccessContext, source_id: int
) -> LibrarySource:
    source_ids = get_visible_source_ids(access)
    source = (
        session.get(LibrarySource, source_id)
        if source_ids is None
        else session.scalar(
            select(LibrarySource).where(
                LibrarySource.id == source_id, LibrarySource.id.in_(source_ids)
            )
        )
    )
    if source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source not found")
    return source


def require_access_permission(access: AccessContext, permission_key: str) -> None:
    if permission_key not in access.permission_keys:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission denied",
        )


def require_permission(permission_key: str):
    if permission_key not in ALL_PERMISSION_KEYS:
        raise ValueError(f"Unknown permission key: {permission_key}")

    def dependency(
        user: User = CURRENT_USER_DEPENDENCY,
        session: Session = SESSION_DEPENDENCY,
    ) -> AccessContext:
        access = get_access_context(session, user)
        require_access_permission(access, permission_key)
        return access

    return dependency
