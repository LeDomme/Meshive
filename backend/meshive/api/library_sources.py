from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from meshive.auth.dependencies import require_admin
from meshive.config import get_settings
from meshive.database import get_session
from meshive.repositories import library_sources as repository
from meshive.schemas.library_source import (
    LibrarySourceCreate,
    LibrarySourceRead,
    LibrarySourceUpdate,
    PathPreviewRequest,
    PathPreviewResponse,
)
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
    dependencies=[Depends(require_admin)],
)


@router.get("", response_model=list[LibrarySourceRead])
def list_library_sources(session: Session = Depends(get_session)) -> list:
    return repository.list_sources(session)


@router.post("", response_model=LibrarySourceRead, status_code=status.HTTP_201_CREATED)
def create_library_source(
    payload: LibrarySourceCreate, session: Session = Depends(get_session)
):
    payload.root_path = validate_library_root(
        payload.root_path, get_settings().allowed_library_root.as_posix()
    )
    try:
        return repository.create_source(session, payload)
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
    session: Session = Depends(get_session),
):
    source = _get_source_or_404(session, source_id)
    payload.root_path = validate_library_root(
        payload.root_path, get_settings().allowed_library_root.as_posix()
    )
    try:
        return repository.update_source(session, source, payload)
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A source with this name or root path already exists",
        ) from error


@router.delete("/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_library_source(
    source_id: int, session: Session = Depends(get_session)
) -> Response:
    cache_keys = repository.delete_source(
        session, _get_source_or_404(session, source_id)
    )
    for key in cache_keys:
        remove_cached_file(get_settings().cache_dir, key)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/preview", response_model=PathPreviewResponse)
def preview_library_path(payload: PathPreviewRequest) -> PathPreviewResponse:
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
