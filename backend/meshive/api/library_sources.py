from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from meshive.auth.access import (
    get_access_context,
    get_operable_source_or_404,
    require_access_permission,
)
from meshive.auth.dependencies import get_current_user
from meshive.auth.permissions import SOURCES_MANAGE
from meshive.config import get_settings
from meshive.database import get_session
from meshive.models.user import User
from meshive.repositories import library_sources as repository
from meshive.schemas.library_source import (
    LibrarySourceCreate,
    LibrarySourceRead,
    LibrarySourceUpdate,
    PathPreviewRequest,
    PathPreviewResponse,
)
from meshive.services.audit import AuditAction, log_event
from meshive.services.library_paths import (
    PathPatternError,
    model_pattern_warnings,
    parse_library_path,
    validate_library_root,
)
from meshive.services.thumbnails import remove_cached_file

router = APIRouter(
    prefix="/admin/library-sources",
    tags=["library sources"],
)
CurrentUser = Annotated[User, Depends(get_current_user)]
SessionDependency = Annotated[Session, Depends(get_session)]


@router.get("", response_model=list[LibrarySourceRead])
def list_library_sources(current_user: CurrentUser, session: SessionDependency) -> list:
    access = get_access_context(session, current_user)
    require_access_permission(access, SOURCES_MANAGE)
    sources = repository.list_sources(session)
    return sources if access.all_sources or access.is_superuser else [source for source in sources if source.id in access.source_ids]


@router.post("", response_model=LibrarySourceRead, status_code=status.HTTP_201_CREATED)
def create_library_source(
    payload: LibrarySourceCreate,
    current_user: CurrentUser,
    session: SessionDependency,
):
    access = get_access_context(session, current_user)
    require_access_permission(access, SOURCES_MANAGE)
    if not (access.all_sources or access.is_superuser):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="All sources access required")
    payload.root_path = validate_library_root(
        payload.root_path, get_settings().allowed_library_root.as_posix()
    )
    try:
        source = repository.create_source(session, payload)
        log_event(
            session,
            current_user,
            AuditAction.SOURCE_CREATED,
            "library_source",
            source.name,
            target_id=source.id,
            library_source_id=source.id,
        )
        session.commit()
        session.refresh(source)
        return source
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A source with this name or root path already exists",
        ) from error


@router.put("/{source_id}", response_model=LibrarySourceRead)
def update_library_source(
    source_id: int,
    payload: LibrarySourceUpdate,
    current_user: CurrentUser,
    session: SessionDependency,
):
    access = get_access_context(session, current_user)
    source = get_operable_source_or_404(session, access, source_id)
    require_access_permission(access, SOURCES_MANAGE)
    if not (access.all_sources or access.is_superuser):
        if payload.root_path != source.root_path:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Root path cannot be changed")
        for field in ("directory_pattern", "model_pattern", "archive_formats", "image_formats", "is_active", "scan_enabled"):
            if getattr(payload, field) != getattr(source, field):
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Global source configuration requires all sources access")
    payload.root_path = validate_library_root(
        payload.root_path, get_settings().allowed_library_root.as_posix()
    )
    try:
        changed_categories = _source_update_categories(source, payload)
        source = repository.update_source(session, source, payload)
        log_event(
            session,
            current_user,
            AuditAction.SOURCE_UPDATED,
            "library_source",
            source.name,
            target_id=source.id,
            library_source_id=source.id,
            details={"changed_categories": changed_categories},
        )
        session.commit()
        session.refresh(source)
        return source
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A source with this name or root path already exists",
        ) from error


@router.delete("/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_library_source(
    source_id: int, current_user: CurrentUser, session: SessionDependency
) -> Response:
    access = get_access_context(session, current_user)
    source = get_operable_source_or_404(session, access, source_id)
    require_access_permission(access, SOURCES_MANAGE)
    if not (access.all_sources or access.is_superuser):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="All sources access required")
    source_id = source.id
    source_name = source.name
    try:
        event = log_event(
            session,
            current_user,
            AuditAction.SOURCE_DELETED,
            "library_source",
            source_name,
            target_id=source_id,
            library_source_id=source_id,
        )
        cache_keys = repository.delete_source(session, source)
        # Preserve the deletion snapshot without keeping a dangling source reference
        # on database engines where foreign-key enforcement is disabled in tests.
        event.library_source_id = None
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Source could not be deleted",
        ) from error
    for key in cache_keys:
        remove_cached_file(get_settings().cache_dir, key)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/preview", response_model=PathPreviewResponse)
def preview_library_path(
    payload: PathPreviewRequest,
    current_user: CurrentUser,
    session: SessionDependency,
) -> PathPreviewResponse:
    access = get_access_context(session, current_user)
    require_access_permission(access, SOURCES_MANAGE)
    if not (access.all_sources or access.is_superuser):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="All sources access required")
    try:
        normalized_path, values = parse_library_path(
            directory_pattern=payload.directory_pattern,
            model_pattern=payload.model_pattern,
            relative_path=payload.relative_path,
        )
    except PathPatternError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)
        ) from error
    return PathPreviewResponse(
        normalized_path=normalized_path,
        values=values,
        warnings=model_pattern_warnings(payload.model_pattern),
    )


def _get_source_or_404(session: Session, source_id: int):
    source = repository.get_source(session, source_id)
    if source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source not found")
    return source


def _source_update_categories(
    source, payload: LibrarySourceUpdate
) -> list[str]:
    fields_by_category = {
        "name": ("name",),
        "scan_schedule": (
            "auto_scan_enabled",
            "auto_scan_frequency",
            "auto_scan_time",
            "auto_scan_weekday",
            "auto_scan_timezone",
        ),
        "formats": ("archive_formats", "image_formats"),
        "active_state": ("is_active",),
        "scan_enabled": ("scan_enabled",),
        "path_rules": ("root_path", "directory_pattern", "model_pattern"),
    }
    return [
        category
        for category, fields in fields_by_category.items()
        if any(getattr(source, field) != getattr(payload, field) for field in fields)
    ]
