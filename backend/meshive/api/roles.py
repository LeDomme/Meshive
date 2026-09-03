from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from meshive.auth.access import require_global_permission
from meshive.auth.permissions import ALL_PERMISSION_KEYS, ROLES_MANAGE, normalize_role_name
from meshive.database import get_session
from meshive.models.authorization import Role, RolePermission
from meshive.models.user import User
from meshive.schemas.user import RoleRead, RoleWrite

router = APIRouter(
    prefix="/admin/roles",
    tags=["roles"],
    dependencies=[Depends(require_global_permission(ROLES_MANAGE))],
)
permissions_router = APIRouter(
    prefix="/admin/permissions",
    tags=["roles"],
    dependencies=[Depends(require_global_permission(ROLES_MANAGE))],
)

SessionDependency = Annotated[Session, Depends(get_session)]


def _role_read(session: Session, role: Role) -> RoleRead:
    return RoleRead(
        id=role.id,
        name=role.name,
        description=role.description,
        is_system=role.is_system,
        is_superuser=role.is_superuser,
        permission_keys=sorted(permission.permission_key for permission in role.permissions),
        user_count=int(
            session.scalar(select(func.count()).select_from(User).where(User.role_id == role.id))
            or 0
        ),
    )


def _get_role_or_404(session: Session, role_id: int) -> Role:
    role = session.get(Role, role_id)
    if role is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")
    return role


def _validate_permission_keys(permission_keys: list[str]) -> None:
    unknown = sorted(set(permission_keys) - ALL_PERMISSION_KEYS)
    if unknown:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Unknown permission keys: {', '.join(unknown)}",
        )


@router.get("", response_model=list[RoleRead])
def list_roles(session: SessionDependency) -> list[RoleRead]:
    roles = list(session.scalars(select(Role).order_by(Role.normalized_name)))
    return [_role_read(session, role) for role in roles]


@router.get("/permissions", response_model=list[str])
def list_permissions() -> list[str]:
    return sorted(ALL_PERMISSION_KEYS)


@permissions_router.get("", response_model=list[str])
def list_all_permissions() -> list[str]:
    return sorted(ALL_PERMISSION_KEYS)


@router.post("", response_model=RoleRead, status_code=status.HTTP_201_CREATED)
def create_role(payload: RoleWrite, session: SessionDependency) -> RoleRead:
    _validate_permission_keys(payload.permission_keys)
    role = Role(
        name=payload.name,
        normalized_name=normalize_role_name(payload.name),
        description=payload.description,
        is_system=False,
        is_superuser=False,
    )
    role.permissions = [
        RolePermission(permission_key=permission_key)
        for permission_key in sorted(payload.permission_keys)
    ]
    session.add(role)
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A role with this name already exists",
        ) from error
    session.refresh(role)
    return _role_read(session, role)


@router.put("/{role_id}", response_model=RoleRead)
def update_role(role_id: int, payload: RoleWrite, session: SessionDependency) -> RoleRead:
    role = _get_role_or_404(session, role_id)
    if role.is_system:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="System roles cannot be changed",
        )
    _validate_permission_keys(payload.permission_keys)
    role.name = payload.name
    role.normalized_name = normalize_role_name(payload.name)
    role.description = payload.description
    role.permissions = [
        RolePermission(permission_key=permission_key)
        for permission_key in sorted(payload.permission_keys)
    ]
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A role with this name already exists",
        ) from error
    session.refresh(role)
    return _role_read(session, role)


@router.delete("/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_role(role_id: int, session: SessionDependency) -> None:
    role = _get_role_or_404(session, role_id)
    if role.is_system:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="System roles cannot be deleted",
        )
    user_count = int(
        session.scalar(select(func.count()).select_from(User).where(User.role_id == role.id))
        or 0
    )
    if user_count:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Role is assigned to {user_count} users",
        )
    session.delete(role)
    session.commit()
