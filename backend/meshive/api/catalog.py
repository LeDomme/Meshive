from pathlib import Path
import re
from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import and_, column, delete, func, select, table, text, update
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask

from meshive.auth.dependencies import get_current_user, require_admin
from meshive.config import get_settings
from meshive.database import get_session
from meshive.models.catalog import (
    Archive,
    ArchiveEntry,
    LibraryModel,
    ModelImage,
    ScanIssue,
)
from meshive.models.library_source import LibrarySource
from meshive.models.tag import ModelTag, Tag
from meshive.schemas.catalog import (
    CatalogueFilters,
    ArchiveEntryRead,
    ArchiveRead,
    FilterOption,
    ModelDetail,
    ModelImageRead,
    ModelPage,
    ModelSummary,
    SourceFilterOption,
)
from meshive.schemas.tag import TagRead
from meshive.services.archive_bundle import BundleArchive, stream_archive_bundle
from meshive.services.download_limiter import claim_download, release_download
from meshive.services.thumbnails import (
    ThumbnailError,
    remove_cached_thumbnail,
    safe_cache_path,
)

router = APIRouter(
    prefix="/models",
    tags=["catalogue"],
    dependencies=[Depends(get_current_user)],
)
admin_router = APIRouter(
    prefix="/admin/models",
    tags=["catalogue administration"],
    dependencies=[Depends(require_admin)],
)


@router.get("", response_model=ModelPage)
def list_models(
    search: str | None = Query(default=None, max_length=200),
    model_name: str | None = Query(default=None, alias="model", max_length=255),
    creator: str | None = Query(default=None, max_length=255),
    franchise: str | None = Query(default=None, max_length=255),
    series: str | None = Query(default=None, max_length=255),
    collection: str | None = Query(default=None, max_length=255),
    tag_id: int | None = None,
    source_id: int | None = None,
    model_status: str | None = Query(default=None, alias="status", max_length=30),
    sort: Literal[
        "meshive_newest",
        "meshive_oldest",
        "files_newest",
        "files_oldest",
        "name_asc",
        "name_desc",
        "creator_asc",
        "creator_desc",
    ] = "name_asc",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=48, ge=1, le=100),
    session: Session = Depends(get_session),
) -> ModelPage:
    filters = _model_filters(
        search=search,
        model_name=model_name,
        creator=creator,
        franchise=franchise,
        series=series,
        collection=collection,
        tag_id=tag_id,
        source_id=source_id,
        model_status=model_status,
    )
    total = int(
        session.scalar(
            select(func.count()).select_from(LibraryModel).where(*filters)
        )
        or 0
    )

    statement = (
        select(
            LibraryModel,
            LibrarySource.name.label("source_name"),
            select(Archive.format)
            .where(Archive.model_id == LibraryModel.id)
            .order_by(Archive.filename.collate("NOCASE"))
            .limit(1)
            .scalar_subquery()
            .label("archive_format"),
            select(func.sum(Archive.size_bytes))
            .where(Archive.model_id == LibraryModel.id)
            .scalar_subquery()
            .label("archive_size_bytes"),
            select(func.count(Archive.id))
            .where(Archive.model_id == LibraryModel.id)
            .scalar_subquery()
            .label("archive_count"),
            ModelImage.thumbnail_key.label("thumbnail_key"),
        )
        .join(LibrarySource, LibrarySource.id == LibraryModel.library_source_id)
        .outerjoin(
            ModelImage,
            and_(
                ModelImage.model_id == LibraryModel.id,
                ModelImage.is_primary.is_(True),
                ModelImage.is_available.is_(True),
                ModelImage.thumbnail_status == "ready",
            ),
        )
        .where(*filters)
        .order_by(*_model_order(sort))
        .offset((page - 1) * page_size)
        .limit(page_size)
    )

    items = [
        ModelSummary(
            id=model.id,
            name=model.name,
            creator=model.creator,
            franchise=model.franchise,
            series=model.series,
            collection=model.collection,
            status=model.status,
            source_id=model.library_source_id,
            source_name=source_name,
            archive_format=archive_format,
            archive_size_bytes=archive_size_bytes,
            archive_count=archive_count,
            thumbnail_url=(
                f"/api/models/{model.id}/thumbnail" if thumbnail_key else None
            ),
            tags=_model_tags(session, model.id),
        )
        for (
            model,
            source_name,
            archive_format,
            archive_size_bytes,
            archive_count,
            thumbnail_key,
        ) in session.execute(statement)
    ]
    return ModelPage(items=items, total=total, page=page, page_size=page_size)


@router.get("/filters", response_model=CatalogueFilters)
def catalogue_filters(
    search: str | None = Query(default=None, max_length=200),
    model_name: str | None = Query(default=None, alias="model", max_length=255),
    creator: str | None = Query(default=None, max_length=255),
    franchise: str | None = Query(default=None, max_length=255),
    series: str | None = Query(default=None, max_length=255),
    collection: str | None = Query(default=None, max_length=255),
    tag_id: int | None = None,
    source_id: int | None = None,
    model_status: str | None = Query(default=None, alias="status", max_length=30),
    session: Session = Depends(get_session),
) -> CatalogueFilters:
    values = {
        "search": search,
        "model_name": model_name,
        "creator": creator,
        "franchise": franchise,
        "series": series,
        "collection": collection,
        "tag_id": tag_id,
        "source_id": source_id,
        "model_status": model_status,
    }

    def facet_filters(exclude: str) -> list:
        return _model_filters(
            **{key: None if key == exclude else value for key, value in values.items()}
        )

    return CatalogueFilters(
        models=_text_filter_options(
            session, LibraryModel.name, facet_filters("model_name")
        ),
        creators=_text_filter_options(
            session, LibraryModel.creator, facet_filters("creator")
        ),
        franchises=_text_filter_options(
            session, LibraryModel.franchise, facet_filters("franchise")
        ),
        series=_text_filter_options(
            session, LibraryModel.series, facet_filters("series")
        ),
        collections=_text_filter_options(
            session, LibraryModel.collection, facet_filters("collection")
        ),
        statuses=_text_filter_options(
            session, LibraryModel.status, facet_filters("model_status")
        ),
        tags=[
            TagRead(id=tag.id, name=tag.name, color=tag.color, description=tag.description)
            for tag in session.scalars(
                select(Tag)
                .where(
                    Tag.id.in_(
                        select(ModelTag.tag_id)
                        .join(LibraryModel, LibraryModel.id == ModelTag.model_id)
                        .where(*facet_filters("tag_id"))
                    )
                )
                .order_by(Tag.name.collate("NOCASE"))
            )
        ],
        sources=[
            SourceFilterOption(id=source_id, name=name, count=count)
            for source_id, name, count in session.execute(
                select(
                    LibrarySource.id,
                    LibrarySource.name,
                    func.count(LibraryModel.id),
                )
                .join(
                    LibraryModel,
                    LibraryModel.library_source_id == LibrarySource.id,
                )
                .where(*facet_filters("source_id"))
                .group_by(LibrarySource.id, LibrarySource.name)
                .order_by(LibrarySource.name.collate("NOCASE"))
            )
        ],
    )


@router.get("/{model_id}", response_model=ModelDetail)
def model_detail(
    model_id: int, session: Session = Depends(get_session)
) -> ModelDetail:
    row = session.execute(
        select(LibraryModel, LibrarySource.name)
        .join(LibrarySource, LibrarySource.id == LibraryModel.library_source_id)
        .where(LibraryModel.id == model_id)
    ).one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Model not found"
        )
    model, source_name = row
    images = session.scalars(
        select(ModelImage)
        .where(
            ModelImage.model_id == model.id,
            ModelImage.is_available.is_(True),
        )
        .order_by(ModelImage.is_primary.desc(), ModelImage.filename.collate("NOCASE"))
    ).all()
    archives = session.scalars(
        select(Archive)
        .where(Archive.model_id == model.id)
        .order_by(Archive.filename.collate("NOCASE"))
    ).all()
    archive_reads = []
    for archive in archives:
        entries = session.scalars(
            select(ArchiveEntry)
            .where(ArchiveEntry.archive_id == archive.id)
            .order_by(ArchiveEntry.path.collate("NOCASE"))
        ).all()
        archive_reads.append(
            ArchiveRead(
                id=archive.id,
                filename=archive.filename,
                format=archive.format,
                size_bytes=archive.size_bytes,
                status=archive.status,
                entry_count=archive.entry_count,
                uncompressed_size_bytes=archive.uncompressed_size_bytes,
                error_message=archive.error_message,
                download_url=(
                    f"/api/models/{model.id}/archives/{archive.id}/download"
                ),
                entries=[
                    ArchiveEntryRead(
                        path=entry.path,
                        name=entry.name,
                        is_directory=entry.is_directory,
                        size_bytes=entry.size_bytes,
                        compressed_size_bytes=entry.compressed_size_bytes,
                        modified_at=entry.modified_at,
                    )
                    for entry in entries
                ],
            )
        )
    return ModelDetail(
        id=model.id,
        name=model.name,
        creator=model.creator,
        franchise=model.franchise,
        series=model.series,
        collection=model.collection,
        status=model.status,
        source_id=model.library_source_id,
        source_name=source_name,
        relative_path=model.relative_path,
        images=[
            ModelImageRead(
                id=image.id,
                filename=image.filename,
                format=image.format,
                size_bytes=image.size_bytes,
                is_primary=image.is_primary,
                url=f"/api/models/{model.id}/images/{image.id}",
            )
            for image in images
        ],
        archives=archive_reads,
        archive_bundle_download_url=(
            f"/api/models/{model.id}/archives/download-all"
            if len(archive_reads) > 1
            else None
        ),
        tags=_model_tags(session, model.id),
    )


@router.get("/{model_id}/archives/download-all", response_class=StreamingResponse)
def download_all_archives(
    model_id: int,
    session: Session = Depends(get_session),
) -> StreamingResponse:
    model = session.get(LibraryModel, model_id)
    if model is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Model not found"
        )
    rows = session.execute(
        select(Archive, LibrarySource.root_path)
        .join(LibraryModel, LibraryModel.id == Archive.model_id)
        .join(LibrarySource, LibrarySource.id == LibraryModel.library_source_id)
        .where(Archive.model_id == model_id)
        .order_by(Archive.filename.collate("NOCASE"), Archive.id)
    ).all()
    if len(rows) < 2:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Multiple archives were not found",
        )

    bundle_archives: list[BundleArchive] = []
    for archive, root_path in rows:
        path = _safe_source_file(root_path, archive.relative_path)
        if path is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Archive file not found: {archive.filename}",
            )
        file_stat = path.stat()
        bundle_archives.append(
            BundleArchive(
                path=path,
                filename=archive.filename,
                size_bytes=file_stat.st_size,
                modified_at=int(file_stat.st_mtime),
            )
        )

    if not claim_download():
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many archive downloads are currently active",
            headers={"Retry-After": "10"},
        )

    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "-", model.name).strip("-._")
    safe_name = safe_name or f"model-{model.id}"
    filename = f"{safe_name}-archives.tar"
    encoded_filename = quote(filename)
    try:
        return StreamingResponse(
            stream_archive_bundle(bundle_archives),
            media_type="application/x-tar",
            headers={
                "Cache-Control": "private, no-store",
                "Content-Disposition": (
                    f'attachment; filename="{filename}"; '
                    f"filename*=UTF-8''{encoded_filename}"
                ),
            },
            background=BackgroundTask(release_download),
        )
    except Exception:
        release_download()
        raise


@router.get(
    "/{model_id}/archives/{archive_id}/download",
    response_class=FileResponse,
)
def download_archive(
    model_id: int,
    archive_id: int,
    session: Session = Depends(get_session),
) -> FileResponse:
    row = session.execute(
        select(Archive, LibrarySource.root_path)
        .join(LibraryModel, LibraryModel.id == Archive.model_id)
        .join(LibrarySource, LibrarySource.id == LibraryModel.library_source_id)
        .where(Archive.id == archive_id, Archive.model_id == model_id)
    ).one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Archive not found"
        )
    archive, root_path = row
    path = _safe_source_file(root_path, archive.relative_path)
    if path is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Archive file not found"
        )
    if not claim_download():
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many archive downloads are currently active",
            headers={"Retry-After": "10"},
        )
    try:
        return FileResponse(
            path,
            media_type="application/octet-stream",
            filename=archive.filename,
            headers={"Cache-Control": "private, no-store"},
            background=BackgroundTask(release_download),
        )
    except Exception:
        release_download()
        raise


@router.get("/{model_id}/images/{image_id}", response_class=FileResponse)
def model_image(
    model_id: int,
    image_id: int,
    session: Session = Depends(get_session),
) -> FileResponse:
    row = session.execute(
        select(ModelImage, LibrarySource.root_path)
        .join(LibraryModel, LibraryModel.id == ModelImage.model_id)
        .join(LibrarySource, LibrarySource.id == LibraryModel.library_source_id)
        .where(
            ModelImage.id == image_id,
            ModelImage.model_id == model_id,
            ModelImage.is_available.is_(True),
        )
    ).one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Image not found"
        )
    image, root_path = row
    path = _safe_source_file(root_path, image.relative_path)
    if path is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Image not found"
        )
    media_types = {
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "png": "image/png",
        "webp": "image/webp",
    }
    return FileResponse(
        path,
        media_type=media_types.get(image.format, "application/octet-stream"),
        headers={"Cache-Control": "private, max-age=3600"},
    )


@router.get("/{model_id}/thumbnail", response_class=FileResponse)
def model_thumbnail(
    model_id: int, session: Session = Depends(get_session)
) -> FileResponse:
    key = session.scalar(
        select(ModelImage.thumbnail_key).where(
            ModelImage.model_id == model_id,
            ModelImage.is_primary.is_(True),
            ModelImage.is_available.is_(True),
            ModelImage.thumbnail_status == "ready",
        )
    )
    if not key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Thumbnail not found"
        )
    try:
        path = safe_cache_path(get_settings().cache_dir, key)
    except ThumbnailError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Thumbnail not found"
        ) from error
    if not path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Thumbnail not found"
        )
    return FileResponse(
        Path(path),
        media_type="image/webp",
        headers={"Cache-Control": "private, max-age=86400"},
    )


@admin_router.delete("/missing")
def delete_all_missing_models(
    session: Session = Depends(get_session),
) -> dict[str, int]:
    model_ids = list(
        session.scalars(
            select(LibraryModel.id).where(LibraryModel.status == "missing")
        )
    )
    thumbnail_keys = _delete_model_records(session, model_ids)
    for key in thumbnail_keys:
        remove_cached_thumbnail(get_settings().cache_dir, key)
    return {"deleted": len(model_ids)}


@admin_router.delete("/{model_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_missing_model(
    model_id: int, session: Session = Depends(get_session)
) -> None:
    model = session.get(LibraryModel, model_id)
    if model is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Model not found"
        )
    if model.status != "missing":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only missing models can be deleted from the database",
        )

    thumbnail_keys = _delete_model_records(session, [model.id])
    for key in thumbnail_keys:
        remove_cached_thumbnail(get_settings().cache_dir, key)


def _delete_model_records(session: Session, model_ids: list[int]) -> list[str]:
    if not model_ids:
        return []
    thumbnail_keys = [
        key
        for key in session.scalars(
            select(ModelImage.thumbnail_key).where(
                ModelImage.model_id.in_(model_ids),
                ModelImage.thumbnail_key.is_not(None),
            )
        )
        if key
    ]
    archive_ids = list(
        session.scalars(
            select(Archive.id).where(Archive.model_id.in_(model_ids))
        )
    )
    session.execute(
        update(ScanIssue)
        .where(ScanIssue.model_id.in_(model_ids))
        .values(model_id=None)
    )
    if archive_ids:
        session.execute(
            delete(ArchiveEntry).where(ArchiveEntry.archive_id.in_(archive_ids))
        )
    session.execute(delete(ModelImage).where(ModelImage.model_id.in_(model_ids)))
    session.execute(delete(ModelTag).where(ModelTag.model_id.in_(model_ids)))
    session.execute(delete(Archive).where(Archive.model_id.in_(model_ids)))
    session.execute(delete(LibraryModel).where(LibraryModel.id.in_(model_ids)))
    session.commit()
    return thumbnail_keys


def _model_filters(
    *,
    search: str | None,
    model_name: str | None,
    creator: str | None,
    franchise: str | None,
    series: str | None,
    collection: str | None,
    tag_id: int | None,
    source_id: int | None,
    model_status: str | None,
) -> list:
    filters = []
    if search and search.strip():
        fts_query = _fts_query(search)
        if fts_query:
            search_index = table("model_search", column("model_id"))
            matching_ids = (
                select(search_index.c.model_id)
                .where(text("model_search MATCH :fts_query"))
                .params(fts_query=fts_query)
            )
            filters.append(LibraryModel.id.in_(matching_ids))
    if model_name:
        filters.append(LibraryModel.name == model_name)
    if creator:
        filters.append(LibraryModel.creator == creator)
    if franchise:
        filters.append(LibraryModel.franchise == franchise)
    if series:
        filters.append(LibraryModel.series == series)
    if collection:
        filters.append(LibraryModel.collection == collection)
    if tag_id is not None:
        filters.append(
            LibraryModel.id.in_(
                select(ModelTag.model_id).where(ModelTag.tag_id == tag_id)
            )
        )
    if source_id is not None:
        filters.append(LibraryModel.library_source_id == source_id)
    if model_status:
        filters.append(LibraryModel.status == model_status)
    return filters


def _model_order(sort: str) -> tuple:
    name = LibraryModel.name.collate("NOCASE")
    creator = LibraryModel.creator.collate("NOCASE")
    if sort == "meshive_newest":
        return (LibraryModel.first_seen_at.desc(), LibraryModel.id.desc())
    if sort == "meshive_oldest":
        return (LibraryModel.first_seen_at, LibraryModel.id)
    archive_modified = (
        select(func.max(Archive.modified_ns))
        .where(Archive.model_id == LibraryModel.id)
        .correlate(LibraryModel)
        .scalar_subquery()
    )
    image_modified = (
        select(func.max(ModelImage.modified_ns))
        .where(ModelImage.model_id == LibraryModel.id)
        .correlate(LibraryModel)
        .scalar_subquery()
    )
    files_modified = func.max(
        func.coalesce(archive_modified, 0),
        func.coalesce(image_modified, 0),
    )
    if sort == "files_newest":
        return (files_modified.desc(), LibraryModel.id.desc())
    if sort == "files_oldest":
        return (files_modified == 0, files_modified, LibraryModel.id)
    if sort == "name_desc":
        return (name.desc(), LibraryModel.id.desc())
    if sort == "creator_asc":
        return (LibraryModel.creator.is_(None), creator, name, LibraryModel.id)
    if sort == "creator_desc":
        return (
            LibraryModel.creator.is_(None),
            creator.desc(),
            name,
            LibraryModel.id,
        )
    return (name, LibraryModel.id)


def _text_filter_options(
    session: Session, column, filters: list | None = None
) -> list[FilterOption]:
    return [
        FilterOption(value=value, count=count)
        for value, count in session.execute(
            select(column, func.count(LibraryModel.id))
            .where(*(filters or []), column.is_not(None), column != "")
            .group_by(column)
            .order_by(column.collate("NOCASE"))
        )
    ]


def _fts_query(value: str) -> str:
    tokens = re.findall(r"[\w]+", value, flags=re.UNICODE)
    return " AND ".join(f'"{token.replace(chr(34), chr(34) * 2)}"*' for token in tokens)


def _model_tags(session: Session, model_id: int) -> list[TagRead]:
    return [
        TagRead(id=tag.id, name=tag.name, color=tag.color, description=tag.description)
        for tag in session.scalars(
            select(Tag)
            .join(ModelTag, ModelTag.tag_id == Tag.id)
            .where(ModelTag.model_id == model_id)
            .order_by(Tag.name.collate("NOCASE"))
        )
    ]


def _safe_source_file(root_path: str, relative_path: str) -> Path | None:
    root = Path(root_path).resolve()
    path = root.joinpath(*Path(relative_path).parts).resolve()
    if (path != root and root not in path.parents) or not path.is_file():
        return None
    return path
