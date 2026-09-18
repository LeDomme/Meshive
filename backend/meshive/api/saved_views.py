import unicodedata
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from meshive.auth.access import require_permission
from meshive.auth.dependencies import get_current_user
from meshive.auth.permissions import CATALOGUE_VIEW
from meshive.database import get_session
from meshive.models.saved_view import SavedView
from meshive.models.user import User
from meshive.schemas.saved_view import (
    SavedViewRead,
    SavedViewRename,
    SavedViewWrite,
)

router = APIRouter(
    prefix="/saved-views", dependencies=[Depends(require_permission(CATALOGUE_VIEW))]
)
CurrentUser = Annotated[User, Depends(get_current_user)]
DatabaseSession = Annotated[Session, Depends(get_session)]


def _normalize(value: str) -> str:
    return unicodedata.normalize("NFKC", value).casefold()


def _read(view: SavedView) -> SavedViewRead:
    return SavedViewRead(
        id=view.id,
        name=view.name,
        state=view.catalogue_state,
        created_at=view.created_at,
        updated_at=view.updated_at,
    )


def _owned_view(session: Session, user_id: int, saved_view_id: int) -> SavedView:
    view = session.scalar(
        select(SavedView).where(SavedView.id == saved_view_id, SavedView.user_id == user_id)
    )
    if view is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Saved view not found")
    return view


@router.get("", response_model=list[SavedViewRead])
def list_saved_views(user: CurrentUser, session: DatabaseSession) -> list[SavedViewRead]:
    views = session.scalars(
        select(SavedView)
        .where(SavedView.user_id == user.id)
        .order_by(SavedView.updated_at.desc(), SavedView.name.collate("NOCASE"), SavedView.id)
    ).all()
    return [_read(view) for view in views]


@router.post("", response_model=SavedViewRead, status_code=status.HTTP_201_CREATED)
def create_saved_view(
    payload: SavedViewWrite,
    user: CurrentUser,
    session: DatabaseSession,
) -> SavedViewRead:
    view = SavedView(
        user_id=user.id,
        name=payload.name,
        normalized_name=_normalize(payload.name),
        catalogue_state=payload.state.model_dump(),
    )
    session.add(view)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A saved view with this name already exists",
        ) from None
    session.refresh(view)
    return _read(view)


@router.get("/{saved_view_id}", response_model=SavedViewRead)
def get_saved_view(
    saved_view_id: int,
    user: CurrentUser,
    session: DatabaseSession,
) -> SavedViewRead:
    return _read(_owned_view(session, user.id, saved_view_id))


@router.put("/{saved_view_id}", response_model=SavedViewRead)
def rename_saved_view(
    saved_view_id: int,
    payload: SavedViewRename,
    user: CurrentUser,
    session: DatabaseSession,
) -> SavedViewRead:
    view = _owned_view(session, user.id, saved_view_id)
    view.name = payload.name
    view.normalized_name = _normalize(payload.name)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A saved view with this name already exists",
        ) from None
    session.refresh(view)
    return _read(view)


@router.delete("/{saved_view_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_saved_view(
    saved_view_id: int,
    user: CurrentUser,
    session: DatabaseSession,
) -> Response:
    session.delete(_owned_view(session, user.id, saved_view_id))
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
