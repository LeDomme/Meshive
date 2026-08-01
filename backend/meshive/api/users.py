from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from meshive.auth.action_tokens import (
    EMAIL_VERIFICATION,
    delete_user_action_tokens,
    issue_action_token,
)
from meshive.auth.dependencies import require_admin
from meshive.auth.passwords import hash_password
from meshive.config import Settings, get_settings
from meshive.database import get_session
from meshive.models.user import User
from meshive.repositories import users as repository
from meshive.schemas.user import (
    ActionMessage,
    AdminEmailVerification,
    UserCreate,
    UserRead,
    UserUpdate,
)
from meshive.services.mailer import EmailDeliveryError, send_email_verification

router = APIRouter(
    prefix="/admin/users",
    tags=["users"],
    dependencies=[Depends(require_admin)],
)


@router.get("", response_model=list[UserRead])
def list_users(session: Session = Depends(get_session)) -> list[User]:
    return repository.list_users(session)


@router.post("", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreate, session: Session = Depends(get_session)
) -> User:
    user = User(
        username=payload.username,
        normalized_username=repository.normalize_username(payload.username),
        email=str(payload.email) if payload.email else None,
        normalized_email=(
            repository.normalize_email(str(payload.email)) if payload.email else None
        ),
        password_hash=hash_password(payload.password),
        role=payload.role,
        is_active=payload.is_active,
        must_change_password=payload.must_change_password,
    )
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
    return user


@router.put("/{user_id}", response_model=UserRead)
def update_user(
    user_id: int,
    payload: UserUpdate,
    current_admin: User = Depends(require_admin),
    session: Session = Depends(get_session),
) -> User:
    user = repository.get_user(session, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    removes_active_admin = (
        user.role == "admin"
        and user.is_active
        and (payload.role != "admin" or not payload.is_active)
    )
    if removes_active_admin and repository.count_active_admins(session) <= 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The last active administrator cannot be disabled or demoted",
        )

    if user.id == current_admin.id and not payload.is_active:
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
    user.role = payload.role
    user.is_active = payload.is_active
    user.must_change_password = payload.must_change_password
    if payload.password:
        user.password_hash = hash_password(payload.password)
        delete_user_action_tokens(session, user.id)
    if user.id != current_admin.id and (payload.password or not payload.is_active):
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
    return user


@router.post("/{user_id}/email-verification", response_model=ActionMessage)
def send_user_email_verification(
    user_id: int,
    payload: AdminEmailVerification,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
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
    current_admin: User = Depends(require_admin),
    session: Session = Depends(get_session),
) -> None:
    user = repository.get_user(session, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if user.id == current_admin.id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You cannot delete your own account",
        )
    if user.role == "admin" and user.is_active and repository.count_active_admins(session) <= 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The last active administrator cannot be deleted",
        )
    session.delete(user)
    session.commit()
