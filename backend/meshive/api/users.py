from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from meshive.auth.access import require_global_permission
from meshive.auth.action_tokens import (
    EMAIL_VERIFICATION,
    delete_user_action_tokens,
    issue_action_token,
)
from meshive.auth.dependencies import get_current_user
from meshive.auth.passwords import hash_password
from meshive.auth.permissions import USERS_MANAGE
from meshive.config import Settings, get_settings
from meshive.database import get_session
from meshive.models.authorization import Role, UserLibrarySource
from meshive.models.library_source import LibrarySource
from meshive.models.user import User
from meshive.repositories import users as repository
from meshive.repositories.roles import get_system_role_for_legacy_role
from meshive.schemas.user import (
    ActionMessage,
    AdminEmailVerification,
    RoleDefinitionRead,
    UserCreate,
    UserManagementRead,
    UserSourcePickerRead,
    UserUpdate,
)
from meshive.services.mailer import EmailDeliveryError, send_email_verification

router = APIRouter(
    prefix="/admin/users",
    tags=["users"],
    dependencies=[Depends(require_global_permission(USERS_MANAGE))],
)

SessionDependency = Annotated[Session, Depends(get_session)]
CurrentUserDependency = Annotated[User, Depends(get_current_user)]
SettingsDependency = Annotated[Settings, Depends(get_settings)]


def _role_definition(role: Role | None) -> RoleDefinitionRead | None:
    if role is None:
        return None
    return RoleDefinitionRead(
        id=role.id,
        name=role.name,
        is_system=role.is_system,
        is_superuser=role.is_superuser,
    )


def _user_read(user: User) -> UserManagementRead:
    all_sources = bool(user.all_sources) or bool(
        user.role_definition and user.role_definition.is_superuser
    )
    return UserManagementRead(
        id=user.id,
        username=user.username,
        email=user.email,
        email_verified=user.email_verified,
        role=user.role,
        is_active=user.is_active,
        must_change_password=user.must_change_password,
        created_at=user.created_at,
        updated_at=user.updated_at,
        last_login_at=user.last_login_at,
        role_definition=_role_definition(user.role_definition),
        all_sources=all_sources,
        source_ids=[]
        if all_sources
        else sorted(grant.library_source_id for grant in user.library_source_grants),
    )


def _resolve_role(session: Session, payload: UserCreate | UserUpdate) -> Role:
    if payload.role_id is not None:
        role = session.get(Role, payload.role_id)
        if role is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")
        return role
    if payload.role is None:
        raise RuntimeError("Validated payload is missing a role selection")
    return get_system_role_for_legacy_role(session, payload.role)


def _resolve_source_ids(session: Session, source_ids: list[int]) -> list[int]:
    if len(source_ids) != len(set(source_ids)):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Source IDs must be unique",
        )
    if not source_ids:
        return []
    found_ids = set(
        session.scalars(select(LibrarySource.id).where(LibrarySource.id.in_(source_ids)))
    )
    if set(source_ids) - found_ids:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source not found")
    return source_ids


def _apply_access(user: User, role: Role, all_sources: bool, source_ids: list[int]) -> None:
    effective_all_sources = all_sources or role.is_superuser
    user.role_definition = role
    user.role = "admin" if role.is_superuser else "user"
    user.all_sources = effective_all_sources
    user.library_source_grants.clear()
    if not effective_all_sources:
        user.library_source_grants.extend(
            UserLibrarySource(library_source_id=source_id) for source_id in source_ids
        )


@router.get("", response_model=list[UserManagementRead])
def list_users(session: SessionDependency) -> list[UserManagementRead]:
    return [_user_read(user) for user in repository.list_users(session)]


@router.get("/library-sources", response_model=list[UserSourcePickerRead])
def list_user_source_picker(session: SessionDependency) -> list[UserSourcePickerRead]:
    """Expose only source labels needed when managing user grants."""
    return [
        UserSourcePickerRead(id=source.id, name=source.name)
        for source in session.scalars(select(LibrarySource).order_by(LibrarySource.name))
    ]


@router.post("", response_model=UserManagementRead, status_code=status.HTTP_201_CREATED)
def create_user(payload: UserCreate, session: SessionDependency) -> UserManagementRead:
    role = _resolve_role(session, payload)
    source_ids = _resolve_source_ids(session, payload.source_ids)
    user = User(
        username=payload.username,
        normalized_username=repository.normalize_username(payload.username),
        email=str(payload.email) if payload.email else None,
        normalized_email=(
            repository.normalize_email(str(payload.email)) if payload.email else None
        ),
        password_hash=hash_password(payload.password),
        is_active=payload.is_active,
        must_change_password=payload.must_change_password,
    )
    _apply_access(user, role, payload.all_sources, source_ids)
    session.add(user)
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This username or email address already exists",
        ) from error
    session.refresh(user)
    return _user_read(user)


@router.put("/{user_id}", response_model=UserManagementRead)
def update_user(
    user_id: int,
    payload: UserUpdate,
    current_user: CurrentUserDependency,
    session: SessionDependency,
) -> UserManagementRead:
    user = repository.get_user(session, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    role = _resolve_role(session, payload)
    source_ids = _resolve_source_ids(session, payload.source_ids)
    removes_active_superuser = (
        user.is_active
        and user.role_definition is not None
        and user.role_definition.is_system
        and user.role_definition.is_superuser
        and (not role.is_system or not role.is_superuser or not payload.is_active)
    )
    if (
        removes_active_superuser
        and repository.count_active_system_superusers(session) <= 1
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The last active administrator cannot be disabled or demoted",
        )

    if user.id == current_user.id and not payload.is_active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You cannot disable your own account",
        )

    user.username = payload.username
    user.normalized_username = repository.normalize_username(payload.username)
    new_email = str(payload.email) if payload.email else None
    normalized_email = repository.normalize_email(new_email) if new_email else None
    if normalized_email != user.normalized_email:
        delete_user_action_tokens(session, user.id)
        user.email_verified_at = None
    user.email = new_email
    user.normalized_email = normalized_email
    _apply_access(user, role, payload.all_sources, source_ids)
    user.is_active = payload.is_active
    user.must_change_password = payload.must_change_password
    if payload.password:
        user.password_hash = hash_password(payload.password)
        delete_user_action_tokens(session, user.id)
    if user.id != current_user.id and (payload.password or not payload.is_active):
        user.sessions.clear()

    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This username or email address already exists",
        ) from error
    session.refresh(user)
    return _user_read(user)


@router.post("/{user_id}/email-verification", response_model=ActionMessage)
def send_user_email_verification(
    user_id: int,
    payload: AdminEmailVerification,
    session: SessionDependency,
    settings: SettingsDependency,
) -> ActionMessage:
    user = repository.get_user(session, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email verification cannot be sent to an inactive user",
        )
    email = str(payload.email)
    normalized_email = repository.normalize_email(email)
    if user.normalized_email == normalized_email and user.email_verified:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This recovery email is already verified",
        )
    if not settings.email_delivery_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Email delivery is not configured",
        )
    if normalized_email != user.normalized_email:
        delete_user_action_tokens(session, user.id)
        user.email_verified_at = None
    user.email = email
    user.normalized_email = normalized_email
    raw_token = issue_action_token(
        session,
        user,
        purpose=EMAIL_VERIFICATION,
        lifetime=timedelta(hours=settings.email_verification_lifetime_hours),
        email=email,
    )
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This email address is already used by another account",
        ) from error
    try:
        send_email_verification(settings, email, raw_token)
    except EmailDeliveryError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The verification email could not be delivered",
        ) from error
    return ActionMessage(message="A verification email has been sent.")


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: int,
    current_user: CurrentUserDependency,
    session: SessionDependency,
) -> None:
    user = repository.get_user(session, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if user.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You cannot delete your own account",
        )
    if (
        user.is_active
        and user.role_definition is not None
        and user.role_definition.is_system
        and user.role_definition.is_superuser
        and repository.count_active_system_superusers(session) <= 1
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The last active administrator cannot be deleted",
        )
    session.delete(user)
    session.commit()
