"""Source-aware management endpoints for stable Creator Profiles."""

import json
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from meshive.auth.access import (
    AccessContext,
    get_visible_source_ids,
    require_permission,
)
from meshive.auth.dependencies import get_current_user
from meshive.auth.permissions import METADATA_MANAGE
from meshive.creators import normalize_creator_name
from meshive.database import get_session
from meshive.models.catalog import LibraryModel
from meshive.models.creator import CreatorAlias, CreatorLink, CreatorMerge, CreatorProfile
from meshive.models.favorite import FavoriteListItem
from meshive.models.user import User
from meshive.schemas.creator import (
    CreatorAliasRead,
    CreatorAliasWrite,
    CreatorMergeApplyRequest,
    CreatorMergeHistoryRead,
    CreatorMergePreviewRead,
    CreatorMergePreviewRequest,
    CreatorProfileRead,
    CreatorProfileWrite,
)
from meshive.services.audit import AuditAction, log_event

router = APIRouter(prefix="/admin/creator-profiles", tags=["creator administration"])
SessionDependency = Annotated[Session, Depends(get_session)]
CurrentUser = Annotated[User, Depends(get_current_user)]
ManageAccess = Annotated[AccessContext, Depends(require_permission(METADATA_MANAGE))]


def _profile_or_404(session: Session, profile_id: int) -> CreatorProfile:
    profile = session.get(CreatorProfile, profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Creator profile not found")
    return profile


def _assert_manageable(
    session: Session, access: AccessContext, profiles: list[CreatorProfile]
) -> None:
    """A restricted curator may only mutate profiles wholly inside their sources."""
    visible = get_visible_source_ids(access)
    if visible is None:
        return
    ids = [profile.id for profile in profiles]
    relevant = set(
        session.scalars(
            select(LibraryModel.library_source_id).where(LibraryModel.creator_profile_id.in_(ids))
        ).all()
    )
    if not relevant or not relevant.issubset(visible):
        raise HTTPException(status_code=403, detail="Creator profile is outside your source scope")


def _identity_conflict(
    session: Session, normalized: str, exclude_profile_id: int | None = None
) -> bool:
    profile_query = select(CreatorProfile.id).where(CreatorProfile.normalized_name == normalized)
    alias_query = select(CreatorAlias.creator_profile_id).where(
        CreatorAlias.normalized_alias == normalized
    )
    if exclude_profile_id is not None:
        profile_query = profile_query.where(CreatorProfile.id != exclude_profile_id)
        alias_query = alias_query.where(CreatorAlias.creator_profile_id != exclude_profile_id)
    return session.scalar(profile_query) is not None or session.scalar(alias_query) is not None


def _read(session: Session, profile: CreatorProfile) -> CreatorProfileRead:
    aliases = list(
        session.scalars(
            select(CreatorAlias)
            .where(CreatorAlias.creator_profile_id == profile.id)
            .order_by(CreatorAlias.alias.collate("NOCASE"), CreatorAlias.id)
        )
    )
    links = list(
        session.scalars(
            select(CreatorLink)
            .where(CreatorLink.creator_profile_id == profile.id)
            .order_by(CreatorLink.label.collate("NOCASE"), CreatorLink.id)
        )
    )
    count = (
        session.scalar(
            select(func.count(LibraryModel.id)).where(LibraryModel.creator_profile_id == profile.id)
        )
        or 0
    )
    return CreatorProfileRead(
        id=profile.id,
        display_name=profile.display_name,
        normalized_name=profile.normalized_name,
        description=profile.description,
        artwork_id=profile.artwork_id,
        model_count=count,
        aliases=[
            CreatorAliasRead(id=a.id, alias=a.alias, normalized_alias=a.normalized_alias)
            for a in aliases
        ],
        links=[
            {
                "id": link.id,
                "creator_profile_id": link.creator_profile_id,
                "kind": link.kind,
                "label": link.label,
                "url": link.url,
            }
            for link in links
        ],
    )


@router.get("", response_model=list[CreatorProfileRead])
def list_profiles(session: SessionDependency, access: ManageAccess) -> list[CreatorProfileRead]:
    profiles = list(
        session.scalars(
            select(CreatorProfile)
            .where(CreatorProfile.is_active.is_(True))
            .order_by(CreatorProfile.display_name.collate("NOCASE"), CreatorProfile.id)
        )
    )
    if get_visible_source_ids(access) is not None:
        profiles = [p for p in profiles if _is_manageable(session, access, p)]
    return [_read(session, profile) for profile in profiles]


def _is_manageable(session: Session, access: AccessContext, profile: CreatorProfile) -> bool:
    try:
        _assert_manageable(session, access, [profile])
    except HTTPException:
        return False
    return True


@router.post("", response_model=CreatorProfileRead, status_code=status.HTTP_201_CREATED)
def create_profile(
    payload: CreatorProfileWrite,
    session: SessionDependency,
    current_user: CurrentUser,
    access: ManageAccess,
) -> CreatorProfileRead:
    if get_visible_source_ids(access) is not None:
        raise HTTPException(
            status_code=403, detail="Creating source-less profiles requires all-source access"
        )
    normalized = normalize_creator_name(payload.display_name)
    if _identity_conflict(session, normalized):
        raise HTTPException(
            status_code=409, detail="Creator name conflicts with an existing profile or alias"
        )
    profile = CreatorProfile(
        display_name=payload.display_name,
        normalized_name=normalized,
        description=payload.description,
    )
    session.add(profile)
    session.flush()
    session.add(
        CreatorAlias(
            creator_profile_id=profile.id, alias=payload.display_name, normalized_alias=normalized
        )
    )
    log_event(
        session,
        current_user,
        AuditAction.CREATOR_PROFILE_CREATED,
        "creator_profile",
        profile.display_name,
        target_id=profile.id,
    )
    session.commit()
    return _read(session, profile)


@router.get("/{profile_id}", response_model=CreatorProfileRead)
def get_profile(
    profile_id: int, session: SessionDependency, access: ManageAccess
) -> CreatorProfileRead:
    profile = _profile_or_404(session, profile_id)
    _assert_manageable(session, access, [profile])
    return _read(session, profile)


@router.put("/{profile_id}", response_model=CreatorProfileRead)
def update_profile(
    profile_id: int,
    payload: CreatorProfileWrite,
    session: SessionDependency,
    current_user: CurrentUser,
    access: ManageAccess,
) -> CreatorProfileRead:
    profile = _profile_or_404(session, profile_id)
    _assert_manageable(session, access, [profile])
    normalized = normalize_creator_name(payload.display_name)
    if normalized != profile.normalized_name and _identity_conflict(
        session, normalized, profile.id
    ):
        raise HTTPException(
            status_code=409, detail="Creator name conflicts with an existing profile or alias"
        )
    # The former canonical spelling remains resolvable even when its normalized key changes.
    old_name, old_normalized = profile.display_name, profile.normalized_name
    if not session.scalar(
        select(CreatorAlias.id).where(
            CreatorAlias.creator_profile_id == profile.id,
            CreatorAlias.normalized_alias == old_normalized,
        )
    ):
        session.add(
            CreatorAlias(
                creator_profile_id=profile.id, alias=old_name, normalized_alias=old_normalized
            )
        )
    if normalized != old_normalized:
        profile.normalized_name = normalized
    profile.display_name = payload.display_name
    profile.description = payload.description
    if not session.scalar(
        select(CreatorAlias.id).where(
            CreatorAlias.creator_profile_id == profile.id,
            CreatorAlias.normalized_alias == normalized,
        )
    ):
        session.add(
            CreatorAlias(
                creator_profile_id=profile.id,
                alias=payload.display_name,
                normalized_alias=normalized,
            )
        )
    log_event(
        session,
        current_user,
        AuditAction.CREATOR_PROFILE_UPDATED,
        "creator_profile",
        profile.display_name,
        target_id=profile.id,
        details={"renamed": old_name != profile.display_name},
    )
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(
            status_code=409, detail="Creator name conflicts with an existing profile or alias"
        )
    return _read(session, profile)


@router.post(
    "/{profile_id}/aliases", response_model=CreatorAliasRead, status_code=status.HTTP_201_CREATED
)
def add_alias(
    profile_id: int,
    payload: CreatorAliasWrite,
    session: SessionDependency,
    current_user: CurrentUser,
    access: ManageAccess,
) -> CreatorAliasRead:
    profile = _profile_or_404(session, profile_id)
    _assert_manageable(session, access, [profile])
    normalized = normalize_creator_name(payload.alias)
    if normalized == profile.normalized_name or _identity_conflict(session, normalized, profile.id):
        raise HTTPException(
            status_code=409, detail="Creator alias conflicts with an existing profile or alias"
        )
    alias = CreatorAlias(
        creator_profile_id=profile.id, alias=payload.alias, normalized_alias=normalized
    )
    session.add(alias)
    session.flush()
    log_event(
        session,
        current_user,
        AuditAction.CREATOR_ALIAS_ADDED,
        "creator_profile",
        profile.display_name,
        target_id=profile.id,
        details={"alias_id": alias.id},
    )
    session.commit()
    return CreatorAliasRead(id=alias.id, alias=alias.alias, normalized_alias=alias.normalized_alias)


@router.delete("/{profile_id}/aliases/{alias_id}", status_code=204)
def remove_alias(
    profile_id: int,
    alias_id: int,
    session: SessionDependency,
    current_user: CurrentUser,
    access: ManageAccess,
) -> Response:
    profile = _profile_or_404(session, profile_id)
    _assert_manageable(session, access, [profile])
    alias = session.scalar(
        select(CreatorAlias).where(
            CreatorAlias.id == alias_id, CreatorAlias.creator_profile_id == profile.id
        )
    )
    if alias is None:
        raise HTTPException(status_code=404, detail="Creator alias not found")
    if alias.normalized_alias == profile.normalized_name:
        raise HTTPException(status_code=409, detail="The canonical alias cannot be removed")
    session.delete(alias)
    log_event(
        session,
        current_user,
        AuditAction.CREATOR_ALIAS_REMOVED,
        "creator_profile",
        profile.display_name,
        target_id=profile.id,
        details={"alias_id": alias_id},
    )
    session.commit()
    return Response(status_code=204)


def _merge_preview(
    session: Session, target: CreatorProfile, sources: list[CreatorProfile]
) -> CreatorMergePreviewRead:
    source_ids = [s.id for s in sources]
    source_links = list(
        session.scalars(select(CreatorLink).where(CreatorLink.creator_profile_id.in_(source_ids)))
    )
    target_links = list(
        session.scalars(select(CreatorLink).where(CreatorLink.creator_profile_id == target.id))
    )
    target_by_key = {(l.kind, l.label.casefold()): l for l in target_links}
    duplicate_ids = []
    conflicts = []
    for link in source_links:
        other = target_by_key.get((link.kind, link.label.casefold()))
        if other:
            if other.url == link.url:
                duplicate_ids.append(link.id)
            else:
                conflicts.append(
                    {
                        "source_link_id": link.id,
                        "target_link_id": other.id,
                        "kind": link.kind,
                        "label": link.label,
                    }
                )
        else:
            target_by_key[(link.kind, link.label.casefold())] = link
    source_counts = session.execute(
        select(LibraryModel.library_source_id, func.count(LibraryModel.id))
        .where(LibraryModel.creator_profile_id.in_(source_ids))
        .group_by(LibraryModel.library_source_id)
    ).all()
    favorite_rows = list(
        session.scalars(
            select(FavoriteListItem).where(
                FavoriteListItem.creator_profile_id.in_([target.id, *source_ids])
            )
        )
    )
    target_lists = {f.favorite_list_id for f in favorite_rows if f.creator_profile_id == target.id}
    duplicate_favorites = sum(
        1
        for f in favorite_rows
        if f.creator_profile_id in source_ids and f.favorite_list_id in target_lists
    )
    return CreatorMergePreviewRead(
        target=_read(session, target),
        sources=[_read(session, s) for s in sources],
        models_by_source={str(k): v for k, v in source_counts},
        favorite_count=sum(1 for f in favorite_rows if f.creator_profile_id in source_ids),
        duplicate_favorite_count=duplicate_favorites,
        duplicate_link_ids=duplicate_ids,
        link_conflicts=conflicts,
        artwork_conflict=bool(target.artwork_id and any(s.artwork_id for s in sources)),
    )


@router.post("/merge/preview", response_model=CreatorMergePreviewRead)
def merge_preview(
    payload: CreatorMergePreviewRequest, session: SessionDependency, access: ManageAccess
) -> CreatorMergePreviewRead:
    target = _profile_or_404(session, payload.target_profile_id)
    sources = [_profile_or_404(session, i) for i in payload.source_profile_ids]
    _assert_manageable(session, access, [target, *sources])
    return _merge_preview(session, target, sources)


@router.post("/merge", response_model=CreatorProfileRead)
def merge_apply(
    payload: CreatorMergeApplyRequest,
    session: SessionDependency,
    current_user: CurrentUser,
    access: ManageAccess,
) -> CreatorProfileRead:
    target = _profile_or_404(session, payload.target_profile_id)
    sources = [_profile_or_404(session, i) for i in payload.source_profile_ids]
    _assert_manageable(session, access, [target, *sources])
    preview = _merge_preview(session, target, sources)
    choices = {item.source_link_id: item.action for item in payload.link_resolutions}
    conflict_ids = {int(item["source_link_id"]) for item in preview.link_conflicts}
    if set(choices) != conflict_ids:
        raise HTTPException(
            status_code=409, detail="Every link conflict needs an explicit resolution"
        )
    source_artworks = [s for s in sources if s.artwork_id]
    if preview.artwork_conflict and payload.artwork_resolution not in {
        "target",
        *(f"source:{s.id}" for s in source_artworks),
    }:
        raise HTTPException(status_code=409, detail="Artwork conflict needs an explicit resolution")
    try:
        source_ids = [s.id for s in sources]
        target_artwork_before = target.artwork_id
        snapshots: dict[int, dict[str, object]] = {}
        for source in sources:
            snapshots[source.id] = {
                "source": {
                    "display_name": source.display_name,
                    "normalized_name": source.normalized_name,
                    "is_active": source.is_active,
                    "merged_into_id": source.merged_into_id,
                    "artwork_id": source.artwork_id,
                },
                "target_artwork_before": target_artwork_before,
                "models": list(
                    session.scalars(
                        select(LibraryModel.id).where(LibraryModel.creator_profile_id == source.id)
                    )
                ),
                "aliases": [],
                "links": [],
                "favorites": [],
            }
        if payload.artwork_resolution and payload.artwork_resolution.startswith("source:"):
            target.artwork_id = next(
                s.artwork_id for s in sources if f"source:{s.id}" == payload.artwork_resolution
            )
        session.query(LibraryModel).filter(LibraryModel.creator_profile_id.in_(source_ids)).update(
            {LibraryModel.creator_profile_id: target.id}, synchronize_session=False
        )
        for source in sources:
            source_aliases = list(
                session.scalars(
                    select(CreatorAlias).where(CreatorAlias.creator_profile_id == source.id)
                )
            )
            snapshot = snapshots[source.id]
            # Free the source canonical identity before moving its canonical alias.
            source_normalized = source.normalized_name
            source.normalized_name = f"merged:{source.id}:{source_normalized}"
            source.is_active = False
            source.merged_into_id = target.id
            for alias in source_aliases:
                existing = session.scalar(
                    select(CreatorAlias.id).where(
                        CreatorAlias.creator_profile_id == target.id,
                        CreatorAlias.normalized_alias == alias.normalized_alias,
                    )
                )
                if existing is None:
                    snapshot["aliases"].append(alias.id)
                    alias.creator_profile_id = target.id
        for link in list(
            session.scalars(
                select(CreatorLink).where(CreatorLink.creator_profile_id.in_(source_ids))
            )
        ):
            if link.id in preview.duplicate_link_ids or choices.get(link.id) == "keep_target":
                session.delete(link)
            else:
                source_id = link.creator_profile_id
                if choices.get(link.id) == "keep_source":
                    other_id = next(
                        int(c["target_link_id"])
                        for c in preview.link_conflicts
                        if int(c["source_link_id"]) == link.id
                    )
                    session.delete(session.get(CreatorLink, other_id))
                link.creator_profile_id = target.id
                link.creator_name = target.display_name
                snapshots[source_id]["links"].append(link.id)
        favorites = list(
            session.scalars(
                select(FavoriteListItem).where(FavoriteListItem.creator_profile_id.in_(source_ids))
            )
        )
        target_lists = set(
            session.scalars(
                select(FavoriteListItem.favorite_list_id).where(
                    FavoriteListItem.creator_profile_id == target.id
                )
            )
        )
        for favorite in favorites:
            if favorite.favorite_list_id in target_lists:
                continue
            else:
                source_id = favorite.creator_profile_id
                snapshots[source_id]["favorites"].append(favorite.id)
                favorite.creator_profile_id = target.id
                favorite.entity_key = f"creator:{target.normalized_name}"
                favorite.label = target.display_name
        for source in sources:
            session.add(
                CreatorMerge(
                    target_profile_id=target.id,
                    source_profile_id=source.id,
                    snapshot=json.dumps(snapshots[source.id]),
                )
            )
        log_event(
            session,
            current_user,
            AuditAction.CREATOR_PROFILES_MERGED,
            "creator_profile",
            target.display_name,
            target_id=target.id,
            details={
                "source_profile_ids": source_ids,
                "link_resolutions": choices,
                "artwork_resolution": payload.artwork_resolution,
            },
        )
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(
            status_code=409, detail="Merge conflicts with existing creator metadata"
        )
    return _read(session, target)


@router.get("/{profile_id}/merge-history", response_model=list[CreatorMergeHistoryRead])
def merge_history(
    profile_id: int, session: SessionDependency, access: ManageAccess
) -> list[CreatorMergeHistoryRead]:
    profile = _profile_or_404(session, profile_id)
    _assert_manageable(session, access, [profile])
    merges = list(
        session.scalars(
            select(CreatorMerge)
            .where(CreatorMerge.target_profile_id == profile.id)
            .order_by(CreatorMerge.created_at.desc(), CreatorMerge.id.desc())
        )
    )
    result = []
    for merge in merges:
        snapshot = json.loads(merge.snapshot)
        result.append(
            CreatorMergeHistoryRead(
                id=merge.id,
                source_profile_id=merge.source_profile_id,
                source_display_name=snapshot["source"]["display_name"],
                target_profile_id=merge.target_profile_id,
                created_at=merge.created_at.isoformat(),
                undone_at=merge.undone_at.isoformat() if merge.undone_at else None,
            )
        )
    return result


@router.post("/merges/{merge_id}/undo", response_model=CreatorProfileRead)
def undo_merge(
    merge_id: int, session: SessionDependency, current_user: CurrentUser, access: ManageAccess
) -> CreatorProfileRead:
    merge = session.get(CreatorMerge, merge_id)
    if merge is None or merge.undone_at is not None:
        raise HTTPException(status_code=404, detail="Active creator merge not found")
    target = _profile_or_404(session, merge.target_profile_id)
    source = _profile_or_404(session, merge.source_profile_id)
    _assert_manageable(session, access, [target, source])
    snapshot = json.loads(merge.snapshot)
    try:
        for model_id in snapshot["models"]:
            model = session.get(LibraryModel, model_id)
            if model and model.creator_profile_id == target.id:
                model.creator_profile_id = source.id
        for alias_id in snapshot["aliases"]:
            alias = session.get(CreatorAlias, alias_id)
            if alias and alias.creator_profile_id == target.id:
                alias.creator_profile_id = source.id
        for link_id in snapshot["links"]:
            link = session.get(CreatorLink, link_id)
            if link and link.creator_profile_id == target.id:
                link.creator_profile_id = source.id
                link.creator_name = snapshot["source"]["display_name"]
        for favorite_id in snapshot["favorites"]:
            favorite = session.get(FavoriteListItem, favorite_id)
            if favorite and favorite.creator_profile_id == target.id:
                favorite.creator_profile_id = source.id
        original = snapshot["source"]
        source.normalized_name = original["normalized_name"]
        source.is_active = original["is_active"]
        source.merged_into_id = original["merged_into_id"]
        if target.artwork_id == source.artwork_id:
            target.artwork_id = snapshot["target_artwork_before"]
        merge.undone_at = datetime.now(UTC)
        log_event(
            session,
            current_user,
            AuditAction.CREATOR_MERGE_UNDONE,
            "creator_merge",
            source.display_name,
            target_id=merge.id,
            details={"target_profile_id": target.id, "source_profile_id": source.id},
        )
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(
            status_code=409, detail="Undo conflicts with creator changes made after the merge"
        )
    return _read(session, target)
