from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from meshive.auth.dependencies import require_admin
from meshive.database import get_session
from meshive.models.catalog import LibraryModel
from meshive.models.creator import CreatorLink
from meshive.schemas.creator import CreatorLinkRead, CreatorLinkUpdate

router = APIRouter(
    prefix="/admin/creator-links",
    tags=["creator administration"],
    dependencies=[Depends(require_admin)],
)


@router.get("", response_model=list[CreatorLinkRead])
def list_creator_links(
    session: Session = Depends(get_session),
) -> list[CreatorLinkRead]:
    model_rows = session.execute(
        select(LibraryModel.creator, func.count(LibraryModel.id))
        .where(
            LibraryModel.creator.is_not(None),
            func.trim(LibraryModel.creator) != "",
        )
        .group_by(LibraryModel.creator.collate("NOCASE"))
        .order_by(LibraryModel.creator.collate("NOCASE"))
    ).all()
    links = list(session.scalars(select(CreatorLink)))
    links_by_name = {link.creator_name.casefold(): link for link in links}
    result = [
        CreatorLinkRead(
            name=creator_name,
            url=(
                links_by_name[creator_name.casefold()].url
                if creator_name.casefold() in links_by_name
                else None
            ),
            model_count=model_count,
        )
        for creator_name, model_count in model_rows
    ]
    model_names = {item.name.casefold() for item in result}
    result.extend(
        CreatorLinkRead(name=link.creator_name, url=link.url, model_count=0)
        for link in links
        if link.creator_name.casefold() not in model_names
    )
    return sorted(result, key=lambda item: item.name.casefold())


@router.put("", status_code=status.HTTP_204_NO_CONTENT)
def update_creator_link(
    payload: CreatorLinkUpdate,
    session: Session = Depends(get_session),
) -> Response:
    canonical_name = session.scalar(
        select(LibraryModel.creator)
        .where(LibraryModel.creator.collate("NOCASE") == payload.creator_name)
        .limit(1)
    )
    creator_link = session.scalar(
        select(CreatorLink).where(
            CreatorLink.creator_name == payload.creator_name
        )
    )
    if canonical_name is None and creator_link is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Creator not found",
        )

    if payload.url is None:
        if creator_link is not None:
            session.delete(creator_link)
            session.commit()
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    if creator_link is None:
        creator_link = CreatorLink(
            creator_name=canonical_name or payload.creator_name,
            url=str(payload.url),
        )
        session.add(creator_link)
    else:
        creator_link.url = str(payload.url)

    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A link for this creator already exists",
        ) from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)
