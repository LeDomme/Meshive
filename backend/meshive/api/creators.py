from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from meshive.auth.access import get_access_context, require_access_permission, visible_model_scope
from meshive.auth.dependencies import get_current_user
from meshive.auth.permissions import CATALOGUE_VIEW
from meshive.database import get_session
from meshive.models.catalog import LibraryModel
from meshive.models.creator import CreatorLink, CreatorProfile
from meshive.models.metadata import MetadataArtwork
from meshive.models.user import User
from meshive.schemas.creator import CreatorArtworkRead, CreatorMetadataLinkRead, CreatorPublicRead

router = APIRouter(prefix="/creators", tags=["creators"], dependencies=[Depends(get_current_user)])
SessionDependency = Annotated[Session, Depends(get_session)]
CurrentUser = Annotated[User, Depends(get_current_user)]


@router.get("/{creator_profile_id}", response_model=CreatorPublicRead)
def get_creator(
    creator_profile_id: int,
    current_user: CurrentUser,
    session: SessionDependency,
) -> CreatorPublicRead:
    """Expose a profile only if it owns at least one visible model."""
    access = get_access_context(session, current_user)
    require_access_permission(access, CATALOGUE_VIEW)
    visible_models = select(LibraryModel.id).where(
        LibraryModel.creator_profile_id == creator_profile_id,
    )
    scope = visible_model_scope(access)
    if scope is not None:
        visible_models = visible_models.where(scope)
    model_count = int(session.scalar(select(func.count()).select_from(visible_models.subquery())) or 0)
    if model_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Creator not found")

    profile = session.get(CreatorProfile, creator_profile_id)
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Creator not found")
    links = list(session.scalars(
        select(CreatorLink)
        .where(CreatorLink.creator_profile_id == profile.id)
        .order_by((CreatorLink.kind == "website").desc(), CreatorLink.label.collate("NOCASE"), CreatorLink.id)
    ))
    link_reads = [CreatorMetadataLinkRead(
        id=link.id, creator_profile_id=profile.id, kind=link.kind, label=link.label, url=link.url
    ) for link in links]
    artwork = session.get(MetadataArtwork, profile.artwork_id) if profile.artwork_id else None
    return CreatorPublicRead(
        id=profile.id,
        display_name=profile.display_name,
        description=profile.description,
        artwork=CreatorArtworkRead(
            url=f"/api/metadata/artwork/{artwork.id}?v={artwork.etag[:12]}",
            width=artwork.width,
            height=artwork.height,
        ) if artwork else None,
        links=link_reads,
        primary_link=link_reads[0] if link_reads else None,
        model_count=model_count,
    )
