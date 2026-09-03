import unicodedata
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from meshive.auth.access import get_access_context, get_visible_model_or_404, visible_model_scope
from meshive.auth.dependencies import get_current_user
from meshive.auth.sessions import utc_now
from meshive.database import get_session
from meshive.models.catalog import LibraryModel, ModelImage
from meshive.models.favorite import FavoriteList, FavoriteListItem
from meshive.models.metadata import MetadataArtwork
from meshive.models.tag import ModelTag, Tag
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
    access = get_access_context(session, user)
    favorites = session.scalars(
        select(FavoriteList)
        .where(FavoriteList.user_id == user.id)
        .order_by(FavoriteList.updated_at.desc(), FavoriteList.name.collate("NOCASE"))
    ).all()
    return [
        _summary(favorite, len(_visible_items(session, access, favorite.id)))
        for favorite in favorites
    ]


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
    access = get_access_context(session, user)
    scope = visible_model_scope(access)
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
        .join(LibraryModel, LibraryModel.id == FavoriteListItem.model_id)
        .where(
            FavoriteList.user_id == user.id,
            FavoriteListItem.entity_type == "model",
            FavoriteListItem.model_id.in_(unique_ids),
            *([scope] if scope is not None else []),
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
    access = get_access_context(session, user)
    favorite = _owned_list(session, user.id, favorite_list_id)
    items = _visible_items(session, access, favorite.id)
    return FavoriteListDetail(
        **_summary(favorite, len(items)).model_dump(),
        items=_item_reads(session, access, items),
    )


@router.put("/{favorite_list_id}", response_model=FavoriteListSummary)
def rename_favorite_list(
    favorite_list_id: int,
    payload: FavoriteListWrite,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> FavoriteListSummary:
    access = get_access_context(session, user)
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
    return _summary(favorite, len(_visible_items(session, access, favorite.id)))


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
    item = _new_item(session, favorite.id, payload, get_access_context(session, user))
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
    return _item_reads(session, get_access_context(session, user), [item])[0]


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
    access = get_access_context(session, user)
    if item.id not in {
        visible_item.id for visible_item in _visible_items(session, access, favorite.id)
    }:
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


def _visible_items(session: Session, access, favorite_list_id: int) -> list[FavoriteListItem]:
    scope = visible_model_scope(access)
    statement = (
        select(FavoriteListItem)
        .outerjoin(LibraryModel, LibraryModel.id == FavoriteListItem.model_id)
        .where(FavoriteListItem.favorite_list_id == favorite_list_id)
        .order_by(FavoriteListItem.created_at, FavoriteListItem.id)
    )
    if scope is not None:
        statement = statement.where(
            (FavoriteListItem.entity_type != "model") | scope
        )
    items = list(session.scalars(statement))
    visible_tag_ids = _visible_tag_ids(session, access, {
        item.tag_id for item in items if item.tag_id is not None
    })
    visible_text_values = _visible_text_values(session, access, {
        item.entity_type for item in items if item.entity_type in _TEXT_COLUMNS
    })
    return [
        item
        for item in items
        if item.entity_type == "model"
        or (item.entity_type == "tag" and item.tag_id in visible_tag_ids)
        or (
            item.entity_type in _TEXT_COLUMNS
            and item.entity_key in visible_text_values[item.entity_type]
        )
    ]


def _new_item(
    session: Session, favorite_list_id: int, payload: FavoriteListItemCreate, access
) -> FavoriteListItem:
    if payload.entity_type == "model":
        model = get_visible_model_or_404(session, access, payload.model_id)
        return FavoriteListItem(
            favorite_list_id=favorite_list_id,
            entity_type="model",
            entity_key=str(model.id),
            label=_model_label(model),
            model_id=model.id,
        )
    if payload.entity_type == "tag":
        visible_tag_ids = _visible_tag_ids(session, access, {payload.tag_id})
        tag = session.get(Tag, payload.tag_id)
        if tag is None or tag.id not in visible_tag_ids:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tag not found")
        return FavoriteListItem(
            favorite_list_id=favorite_list_id,
            entity_type="tag",
            entity_key=str(tag.id),
            label=tag.name,
            tag_id=tag.id,
        )

    requested = payload.value or ""
    canonical = _visible_text_values(session, access, {payload.entity_type}).get(
        payload.entity_type, {}
    ).get(_normalize(requested))
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
    session: Session, access, items: list[FavoriteListItem]
) -> list[FavoriteListItemRead]:
    model_ids = {item.model_id for item in items if item.model_id is not None}
    tag_ids = {item.tag_id for item in items if item.tag_id is not None}
    models = {
        model.id: model
        for model in session.scalars(
            select(LibraryModel).where(LibraryModel.id.in_(model_ids))
        )
    }
    thumbnail_image_ids = {
        model_id: image_id
        for model_id, image_id in session.execute(
            select(ModelImage.model_id, ModelImage.id).where(
                ModelImage.model_id.in_(model_ids),
                ModelImage.is_primary.is_(True),
                ModelImage.is_available.is_(True),
                ModelImage.thumbnail_status == "ready",
                ModelImage.thumbnail_key.is_not(None),
            )
        )
    }
    visible_tag_ids = _visible_tag_ids(session, access, tag_ids)
    tags = {
        tag.id: tag
        for tag in session.scalars(select(Tag).where(Tag.id.in_(visible_tag_ids)))
    }
    text_values = _visible_text_values(
        session,
        access,
        {item.entity_type for item in items if item.entity_type in _TEXT_COLUMNS},
    )
    artwork = {
        (entity_type, entity_key): (artwork_id, etag)
        for artwork_id, entity_type, entity_key, etag in session.execute(
            select(
                MetadataArtwork.id,
                MetadataArtwork.entity_type,
                MetadataArtwork.entity_key,
                MetadataArtwork.etag,
            )
        )
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
                f"/api/models/{model.id}/thumbnail?v={thumbnail_image_ids[model.id]}"
                if model and model.id in thumbnail_image_ids
                    else None
                ),
                artwork_url=(
                    _artwork_url(artwork.get((item.entity_type, item.entity_key)))
                    if item.entity_type in _TEXT_COLUMNS
                    and artwork.get((item.entity_type, item.entity_key)) is not None
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


def _visible_tag_ids(session: Session, access, tag_ids: set[int]) -> set[int]:
    if not tag_ids:
        return set()
    scope = visible_model_scope(access)
    statement = (
        select(ModelTag.tag_id)
        .join(LibraryModel, LibraryModel.id == ModelTag.model_id)
        .where(ModelTag.tag_id.in_(tag_ids))
        .distinct()
    )
    if scope is not None:
        statement = statement.where(scope)
    return set(session.scalars(statement))


def _visible_text_values(session: Session, access, entity_types: set[str]) -> dict[str, dict[str, str]]:
    scope = visible_model_scope(access)
    values: dict[str, dict[str, str]] = {}
    for entity_type in entity_types:
        column = _TEXT_COLUMNS[entity_type]
        statement = select(column).where(column.is_not(None), column != "").distinct()
        if scope is not None:
            statement = statement.where(scope)
        values[entity_type] = {_normalize(value): value for value in session.scalars(statement)}
    return values


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


def _artwork_url(artwork: tuple[int, str] | None) -> str | None:
    if artwork is None:
        return None
    artwork_id, etag = artwork
    return f"/api/metadata/artwork/{artwork_id}?v={etag[:12]}"
