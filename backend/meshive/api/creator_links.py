from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from meshive.auth.access import require_global_permission
from meshive.auth.permissions import METADATA_MANAGE
from meshive.database import get_session
from meshive.models.catalog import LibraryModel
from meshive.models.creator import CreatorLink
from meshive.schemas.creator import (
    CreatorLinkCreate,
    CreatorLinkKind,
    CreatorLinkUpdate,
    CreatorMetadataLinkRead,
    CreatorRead,
)

router = APIRouter(
    prefix="/admin/creator-links",
    tags=["creator administration"],
    dependencies=[Depends(require_global_permission(METADATA_MANAGE))],
)
SessionDependency = Annotated[Session, Depends(get_session)]

LINK_LABELS: dict[CreatorLinkKind, str] = {
    "website": "Website",
    "patreon": "Patreon",
    "cults3d": "Cults3D",
    "myminifactory": "MyMiniFactory",
    "cgtrader": "CGTrader",
    "gumroad": "Gumroad",
    "etsy": "Etsy",
    "other": "Other",
}


def _link_label(kind: CreatorLinkKind, custom_label: str | None) -> str:
    return custom_label if kind == "other" and custom_label else LINK_LABELS[kind]


def _link_read(link: CreatorLink) -> CreatorMetadataLinkRead:
    return CreatorMetadataLinkRead(
        id=link.id,
        kind=link.kind,
        label=link.label,
        url=link.url,
    )


def _canonical_creator_name(session: Session, creator_name: str) -> str | None:
    return session.scalar(
        select(LibraryModel.creator)
        .where(LibraryModel.creator.collate("NOCASE") == creator_name)
        .limit(1)
    )


@router.get("", response_model=list[CreatorRead])
def list_creators(session: SessionDependency) -> list[CreatorRead]:
    model_rows = session.execute(
        select(LibraryModel.creator, func.count(LibraryModel.id))
        .where(
            LibraryModel.creator.is_not(None),
            func.trim(LibraryModel.creator) != "",
        )
        .group_by(LibraryModel.creator.collate("NOCASE"))
        .order_by(LibraryModel.creator.collate("NOCASE"))
    ).all()
    links = list(
        session.scalars(
            select(CreatorLink).order_by(
                CreatorLink.creator_name.collate("NOCASE"),
                CreatorLink.label.collate("NOCASE"),
            )
        )
    )
    links_by_name: dict[str, list[CreatorLink]] = {}
    for link in links:
        links_by_name.setdefault(link.creator_name.casefold(), []).append(link)

    result = [
        CreatorRead(
            name=creator_name,
            model_count=model_count,
            links=[
                _link_read(link)
                for link in links_by_name.get(creator_name.casefold(), [])
            ],
        )
        for creator_name, model_count in model_rows
    ]
    model_names = {item.name.casefold() for item in result}
    result.extend(
        CreatorRead(
            name=creator_links[0].creator_name,
            model_count=0,
            links=[_link_read(link) for link in creator_links],
        )
        for normalized_name, creator_links in links_by_name.items()
        if normalized_name not in model_names
    )
    return sorted(result, key=lambda item: item.name.casefold())


@router.post(
    "",
    response_model=CreatorMetadataLinkRead,
    status_code=status.HTTP_201_CREATED,
)
def create_creator_link(
    payload: CreatorLinkCreate,
    session: SessionDependency,
) -> CreatorMetadataLinkRead:
    canonical_name = _canonical_creator_name(session, payload.creator_name)
    if canonical_name is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Creator not found",
        )
    creator_link = CreatorLink(
        creator_name=canonical_name,
        kind=payload.kind,
        label=_link_label(payload.kind, payload.label),
        url=str(payload.url),
    )
    session.add(creator_link)
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This creator link already exists",
        ) from error
    session.refresh(creator_link)
    return _link_read(creator_link)


@router.put("/{link_id}", response_model=CreatorMetadataLinkRead)
def update_creator_link(
    link_id: int,
    payload: CreatorLinkUpdate,
    session: SessionDependency,
) -> CreatorMetadataLinkRead:
    creator_link = session.get(CreatorLink, link_id)
    if creator_link is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Creator link not found",
        )
    creator_link.kind = payload.kind
    creator_link.label = _link_label(payload.kind, payload.label)
    creator_link.url = str(payload.url)
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This creator link already exists",
        ) from error
    session.refresh(creator_link)
    return _link_read(creator_link)


@router.delete("/{link_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_creator_link(
    link_id: int,
    session: SessionDependency,
) -> Response:
    creator_link = session.get(CreatorLink, link_id)
    if creator_link is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Creator link not found",
        )
    session.delete(creator_link)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
