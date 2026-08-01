from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from meshive.auth.dependencies import require_admin
from meshive.auth.passwords import hash_password
from meshive.database import get_session
from meshive.models.user import User
from meshive.repositories import users as repository
from meshive.schemas.user import UserCreate, UserRead, UserUpdate

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
            detail="This username already exists",
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
    user.role = payload.role
    user.is_active = payload.is_active
    user.must_change_password = payload.must_change_password
    if payload.password:
        user.password_hash = hash_password(payload.password)
    if user.id != current_admin.id and (payload.password or not payload.is_active):
        user.sessions.clear()

    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This username already exists",
        ) from error
    session.refresh(user)
    return user


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
