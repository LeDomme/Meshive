from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from meshive.models.catalog import (
    Archive,
    ArchiveEntry,
    LibraryModel,
    ModelImage,
    ScanIssue,
    ScanRun,
)
from meshive.models.library_source import LibrarySource
from meshive.models.tag import FolderTagRule, ModelTag
from meshive.schemas.library_source import LibrarySourceCreate, LibrarySourceUpdate


def list_sources(session: Session) -> list[LibrarySource]:
    return list(session.scalars(select(LibrarySource).order_by(LibrarySource.name)))


def get_source(session: Session, source_id: int) -> LibrarySource | None:
    return session.get(LibrarySource, source_id)


def create_source(session: Session, data: LibrarySourceCreate) -> LibrarySource:
    source = LibrarySource(**data.model_dump())
    session.add(source)
    session.commit()
    session.refresh(source)
    return source


def update_source(
    session: Session, source: LibrarySource, data: LibrarySourceUpdate
) -> LibrarySource:
    for key, value in data.model_dump().items():
        setattr(source, key, value)
    session.commit()
    session.refresh(source)
    return source


def delete_source(session: Session, source: LibrarySource) -> list[str]:
    model_ids = list(
        session.scalars(
            select(LibraryModel.id).where(
                LibraryModel.library_source_id == source.id
            )
        )
    )
    scan_ids = list(
        session.scalars(
            select(ScanRun.id).where(ScanRun.library_source_id == source.id)
        )
    )
    archive_ids = (
        list(
            session.scalars(
                select(Archive.id).where(Archive.model_id.in_(model_ids))
            )
        )
        if model_ids
        else []
    )
    thumbnail_keys = (
        [
            key
            for key in session.scalars(
                select(ModelImage.thumbnail_key).where(
                    ModelImage.model_id.in_(model_ids),
                    ModelImage.thumbnail_key.is_not(None),
                )
            )
            if key
        ]
        if model_ids
        else []
    )

    if scan_ids or model_ids:
        issue_filters = []
        if scan_ids:
            issue_filters.append(ScanIssue.scan_run_id.in_(scan_ids))
        if model_ids:
            issue_filters.append(ScanIssue.model_id.in_(model_ids))
        session.execute(delete(ScanIssue).where(or_(*issue_filters)))
    if archive_ids:
        session.execute(
            delete(ArchiveEntry).where(ArchiveEntry.archive_id.in_(archive_ids))
        )
    if model_ids:
        session.execute(delete(ModelTag).where(ModelTag.model_id.in_(model_ids)))
        session.execute(delete(ModelImage).where(ModelImage.model_id.in_(model_ids)))
        session.execute(delete(Archive).where(Archive.model_id.in_(model_ids)))
        session.execute(
            delete(LibraryModel).where(LibraryModel.library_source_id == source.id)
        )
    if scan_ids:
        session.execute(delete(ScanRun).where(ScanRun.library_source_id == source.id))
    session.execute(
        delete(FolderTagRule).where(FolderTagRule.library_source_id == source.id)
    )
    session.delete(source)
    session.commit()
    return thumbnail_keys
