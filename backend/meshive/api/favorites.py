import unicodedata
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from meshive.auth.dependencies import get_current_user
from meshive.auth.sessions import utc_now
from meshive.database import get_session
from meshive.models.catalog import LibraryModel, ModelImage
from meshive.models.favorite import FavoriteList, FavoriteListItem
from meshive.models.tag import Tag
from meshive.models.user import User
from meshive.schemas.favorite import (
    FavoriteListDetail,
    FavoriteListItemCreate,
    FavoriteListItemRead,
    FavoriteListSummary,
    FavoriteListWrite,
    FavoriteMembershipList,
    FavoriteModelMembership,
)

router = APIRouter(prefix="/favorite-lists", tags=["favorite lists"])

_TEXT_COLUMNS = {
    "creator": LibraryModel.creator,
    "franchise": LibraryModel.franchise,
    "series": LibraryModel.series,
    "collection": LibraryModel.collection,
}


@router.get("", response_model=list[FavoriteListSummary])
def list_favorite_lists(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[FavoriteListSummary]:
    rows = session.execute(
        select(FavoriteList, func.count(FavoriteListItem.id))
        .outerjoin(
            FavoriteListItem,
            FavoriteListItem.favorite_list_id == FavoriteList.id,
        )
        .where(FavoriteList.user_id == user.id)
        .group_by(FavoriteList.id)
        .order_by(FavoriteList.updated_at.desc(), FavoriteList.name.collate("NOCASE"))
    )
    return [_summary(favorite, count) for favorite, count in rows]


@router.post("", response_model=FavoriteListSummary, status_code=status.HTTP_201_CREATED)
def create_favorite_list(
    payload: FavoriteListWrite,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> FavoriteListSummary:
    favorite = FavoriteList(
        user_id=user.id,
        name=payload.name,
        normalized_name=_normalize(payload.name),
    )
    session.add(favorite)
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A favorite list with this name already exists",
        ) from error
    session.refresh(favorite)
    return _summary(favorite, 0)


@router.get("/model-memberships", response_model=list[FavoriteModelMembership])
def model_favorite_memberships(
    model_ids: list[int] = Query(...),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[FavoriteModelMembership]:
    unique_ids = list(dict.fromkeys(model_ids))
    if any(model_id < 1 for model_id in unique_ids):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Model IDs must be positive integers",
        )
    if len(unique_ids) > 100:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="At most 100 model IDs may be checked at once",
        )
    memberships: dict[int, list[FavoriteMembershipList]] = {
        model_id: [] for model_id in unique_ids
    }
    rows = session.execute(
        select(
            FavoriteListItem.model_id,
            FavoriteList.id,
            FavoriteList.name,
            FavoriteListItem.id,
        )
        .join(FavoriteList, FavoriteList.id == FavoriteListItem.favorite_list_id)
        .where(
            FavoriteList.user_id == user.id,
            FavoriteListItem.entity_type == "model",
            FavoriteListItem.model_id.in_(unique_ids),
        )
        .order_by(FavoriteList.name.collate("NOCASE"), FavoriteList.id)
    )
    for model_id, favorite_list_id, name, item_id in rows:
        memberships[model_id].append(
            FavoriteMembershipList(id=favorite_list_id, name=name, item_id=item_id)
        )
    return [
        FavoriteModelMembership(model_id=model_id, lists=memberships[model_id])
        for model_id in unique_ids
        if memberships[model_id]
    ]


@router.get("/{favorite_list_id}", response_model=FavoriteListDetail)
def get_favorite_list(
    favorite_list_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> FavoriteListDetail:
    favorite = _owned_list(session, user.id, favorite_list_id)
    items = list(
        session.scalars(
            select(FavoriteListItem)
            .where(FavoriteListItem.favorite_list_id == favorite.id)
            .order_by(FavoriteListItem.created_at, FavoriteListItem.id)
        )
    )
    return FavoriteListDetail(
        **_summary(favorite, len(items)).model_dump(),
        items=_item_reads(session, items),
    )


@router.put("/{favorite_list_id}", response_model=FavoriteListSummary)
def rename_favorite_list(
    favorite_list_id: int,
    payload: FavoriteListWrite,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> FavoriteListSummary:
    favorite = _owned_list(session, user.id, favorite_list_id)
    favorite.name = payload.name
    favorite.normalized_name = _normalize(payload.name)
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A favorite list with this name already exists",
        ) from error
    session.refresh(favorite)
    item_count = int(
        session.scalar(
            select(func.count(FavoriteListItem.id)).where(
                FavoriteListItem.favorite_list_id == favorite.id
            )
        )
        or 0
    )
    return _summary(favorite, item_count)


@router.delete("/{favorite_list_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_favorite_list(
    favorite_list_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> Response:
    session.delete(_owned_list(session, user.id, favorite_list_id))
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{favorite_list_id}/items",
    response_model=FavoriteListItemRead,
    status_code=status.HTTP_201_CREATED,
)
def add_favorite_list_item(
    favorite_list_id: int,
    payload: FavoriteListItemCreate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> FavoriteListItemRead:
    favorite = _owned_list(session, user.id, favorite_list_id)
    item = _new_item(session, favorite.id, payload)
    favorite.updated_at = utc_now()
    session.add(item)
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This entry is already on the favorite list",
        ) from error
    session.refresh(item)
    return _item_reads(session, [item])[0]


@router.delete(
    "/{favorite_list_id}/items/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_favorite_list_item(
    favorite_list_id: int,
    item_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> Response:
    favorite = _owned_list(session, user.id, favorite_list_id)
    item = session.scalar(
        select(FavoriteListItem).where(
            FavoriteListItem.id == item_id,
            FavoriteListItem.favorite_list_id == favorite.id,
        )
    )
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entry not found")
    session.delete(item)
    favorite.updated_at = utc_now()
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _owned_list(session: Session, user_id: int, favorite_list_id: int) -> FavoriteList:
    favorite = session.scalar(
        select(FavoriteList).where(
            FavoriteList.id == favorite_list_id,
            FavoriteList.user_id == user_id,
        )
    )
    if favorite is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Favorite list not found",
        )
    return favorite


def _new_item(
    session: Session, favorite_list_id: int, payload: FavoriteListItemCreate
) -> FavoriteListItem:
    if payload.entity_type == "model":
        model = session.get(LibraryModel, payload.model_id)
        if model is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Model not found")
        return FavoriteListItem(
            favorite_list_id=favorite_list_id,
            entity_type="model",
            entity_key=str(model.id),
            label=_model_label(model),
            model_id=model.id,
        )
    if payload.entity_type == "tag":
        tag = session.get(Tag, payload.tag_id)
        if tag is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tag not found")
        return FavoriteListItem(
            favorite_list_id=favorite_list_id,
            entity_type="tag",
            entity_key=str(tag.id),
            label=tag.name,
            tag_id=tag.id,
        )

    column = _TEXT_COLUMNS[payload.entity_type]
    requested = payload.value or ""
    canonical = next(
        (
            value
            for value in session.scalars(
                select(column).where(column.is_not(None), column != "").distinct()
            )
            if _normalize(value) == _normalize(requested)
        ),
        None,
    )
    if canonical is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Catalogue value not found",
        )
    return FavoriteListItem(
        favorite_list_id=favorite_list_id,
        entity_type=payload.entity_type,
        entity_key=_normalize(canonical),
        label=canonical,
    )


def _item_reads(
    session: Session, items: list[FavoriteListItem]
) -> list[FavoriteListItemRead]:
    model_ids = {item.model_id for item in items if item.model_id is not None}
    tag_ids = {item.tag_id for item in items if item.tag_id is not None}
    models = {
        model.id: model
        for model in session.scalars(
            select(LibraryModel).where(LibraryModel.id.in_(model_ids))
        )
    }
    thumbnail_model_ids = set(
        session.scalars(
            select(ModelImage.model_id).where(
                ModelImage.model_id.in_(model_ids),
                ModelImage.is_primary.is_(True),
                ModelImage.is_available.is_(True),
                ModelImage.thumbnail_status == "ready",
                ModelImage.thumbnail_key.is_not(None),
            )
        )
    )
    tags = {
        tag.id: tag
        for tag in session.scalars(select(Tag).where(Tag.id.in_(tag_ids)))
    }
    text_values = {
        entity_type: {
            _normalize(value): value
            for value in session.scalars(
                select(column).where(column.is_not(None), column != "").distinct()
            )
        }
        for entity_type, column in _TEXT_COLUMNS.items()
        if any(item.entity_type == entity_type for item in items)
    }

    reads = []
    for item in items:
        label = item.label
        url = None
        is_available = False
        model = None
        if item.entity_type == "model" and item.model_id in models:
            model = models[item.model_id]
            label = _model_label(model)
            url = f"/models/{model.id}"
            is_available = True
        elif item.entity_type == "tag" and item.tag_id in tags:
            tag = tags[item.tag_id]
            label = tag.name
            url = f"/?{urlencode({'tag_id': tag.id})}"
            is_available = True
        elif item.entity_type in _TEXT_COLUMNS:
            current_value = text_values.get(item.entity_type, {}).get(item.entity_key)
            if current_value is not None:
                label = current_value
                url = f"/?{urlencode({item.entity_type: current_value})}"
                is_available = True
        reads.append(
            FavoriteListItemRead(
                id=item.id,
                entity_type=item.entity_type,
                label=label,
                url=url,
                is_available=is_available,
                created_at=item.created_at,
                model_id=model.id if model else None,
                thumbnail_url=(
                    f"/api/models/{model.id}/thumbnail"
                    if model and model.id in thumbnail_model_ids
                    else None
                ),
                variant=model.variant if model else None,
                creator=model.creator if model else None,
                franchise=model.franchise if model else None,
                series=model.series if model else None,
                collection=model.collection if model else None,
                status=model.status if model else None,
            )
        )
    return reads


def _summary(favorite: FavoriteList, item_count: int) -> FavoriteListSummary:
    return FavoriteListSummary(
        id=favorite.id,
        name=favorite.name,
        item_count=item_count,
        created_at=favorite.created_at,
        updated_at=favorite.updated_at,
    )


def _model_label(model: LibraryModel) -> str:
    return f"{model.name} — {model.variant}" if model.variant else model.name


def _normalize(value: str) -> str:
    return unicodedata.normalize("NFKC", value.strip()).casefold()
