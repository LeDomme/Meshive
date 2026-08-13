import hashlib
import json
import logging
import os
import threading
import time
from pathlib import Path, PurePosixPath

from sqlalchemy import delete, inspect, or_, select, update
from sqlalchemy.orm import Session

from meshive.archives.sevenzip_cli import ArchiveReadError, ListedArchiveEntry, list_archive
from meshive.auth.sessions import utc_now
from meshive.config import get_settings
from meshive.database import SessionLocal
from meshive.models.catalog import (
    Archive,
    ArchiveEntry,
    LibraryModel,
    ModelImage,
    ScanIssue,
    ScanRun,
)
from meshive.models.library_source import LibrarySource
from meshive.services.archive_images import (
    ArchiveImageError,
    archive_image_candidate_sort_key,
    iter_extracted_archive_image_batches,
    select_archive_image_candidates,
    validate_extracted_archive_image,
)
from meshive.services.library_paths import PathPatternError, parse_library_path
from meshive.services.tags import recompute_automatic_tags, recompute_inherited_tags
from meshive.services.thumbnails import (
    ThumbnailError,
    generate_cached_webp,
    generate_thumbnail,
    remove_cached_file,
    remove_cached_thumbnail,
    safe_cache_path,
)

class ScanCancelled(RuntimeError):
    pass

_active_sources: set[int] = set()
_active_sources_lock = threading.Lock()


def claim_source(source_id: int) -> bool:
    with _active_sources_lock:
        if (
            source_id in _active_sources
            or len(_active_sources) >= get_settings().max_concurrent_scans
        ):
            return False
        _active_sources.add(source_id)
        return True


def release_source(source_id: int) -> None:
    with _active_sources_lock:
        _active_sources.discard(source_id)


def create_scan_run(
    session: Session,
    source_id: int,
    *,
    trigger: str = "manual",
    mode: str = "full",
) -> ScanRun:
    scan = ScanRun(
        library_source_id=source_id,
        status="pending",
        trigger=trigger,
        mode=mode,
        models_found=0,
        models_added=0,
        models_updated=0,
        models_missing=0,
        models_skipped=0,
        archive_images_reused=0,
        archive_images_generated=0,
        archive_images_removed=0,
        automatic_tag_matches=0,
        automatic_tags_added=0,
        automatic_tags_removed=0,
        issues_count=0,
    )
    session.add(scan)
    session.commit()
    session.refresh(scan)
    return scan


def queue_model_rescan(
    session: Session,
    model_id: int,
    *,
    force_image_rebuild: bool = False,
) -> ScanRun:
    """Queue a targeted model scan behind any active source scan."""
    model = session.get(LibraryModel, model_id)
    if model is None:
        raise LookupError("Model not found")
    source = session.get(LibrarySource, model.library_source_id)
    if source is None:
        raise LookupError("Library source not found")

    scan = create_scan_run(
        session,
        source.id,
        trigger="model_image_rebuild" if force_image_rebuild else "model_rescan",
        mode="full",
    )
    scan.target_model_id = model.id
    scan.target_model_name = model.name
    session.commit()
    dispatch_pending_scans()
    return scan


def has_queued_or_running_scan(session: Session, source_id: int) -> bool:
    return (
        session.scalar(
            select(ScanRun.id)
            .where(
                ScanRun.library_source_id == source_id,
                ScanRun.status.in_(("pending", "running")),
            )
            .limit(1)
        )
        is not None
    )


def dispatch_pending_scans() -> None:
    with SessionLocal() as session:
        if not inspect(session.get_bind()).has_table(ScanRun.__tablename__):
            return
        pending = list(
            session.scalars(
                select(ScanRun)
                .where(ScanRun.status == "pending")
                .order_by(ScanRun.created_at, ScanRun.id)
            )
        )
        for scan in pending:
            if not claim_source(scan.library_source_id):
                continue
            threading.Thread(
                target=execute_scan,
                args=(scan.library_source_id, scan.id),
                name=f"meshive-scan-{scan.library_source_id}",
                daemon=True,
            ).start()


def execute_scan(source_id: int, scan_run_id: int) -> None:
    try:
        with SessionLocal() as session:
            _execute_scan(session, source_id, scan_run_id)
    finally:
        release_source(source_id)
        dispatch_pending_scans()


def _raise_if_scan_cancelled(session: Session, scan_run_id: int) -> None:
    if session.scalar(select(ScanRun.cancel_requested).where(ScanRun.id == scan_run_id)):
        raise ScanCancelled()

def _wait_if_scan_paused(session: Session, scan_run_id: int) -> None:
    while session.scalar(select(ScanRun.pause_requested).where(ScanRun.id == scan_run_id)):
        _raise_if_scan_cancelled(session, scan_run_id)
        time.sleep(0.5)
        session.rollback()

def _execute_scan(session: Session, source_id: int, scan_run_id: int) -> None:
    scan = session.get(ScanRun, scan_run_id)
    source = session.get(LibrarySource, source_id)
    if scan is None:
        return
    scan.status = "running"
    scan.started_at = utc_now()
    session.commit()

    try:
        if source is None:
            raise RuntimeError("Library source no longer exists")
        if scan.target_model_id is not None:
            rescan_model(
                session,
                scan.target_model_id,
                force_image_rebuild=scan.trigger == "model_image_rebuild",
                scan=scan,
            )
            return
        root = _validated_source_root(source)
        if scan.mode == "reconcile_images":
            _reconcile_source_archive_images(session, scan, source, root)
            scan.status = "completed_with_errors" if scan.issues_count else "completed"
            return

        depths = {
            len(PurePosixPath(pattern).parts)
            for pattern in source.directory_pattern.splitlines()
            if pattern.strip()
        }
        model_directories = {
            directory for depth in depths for directory in _directories_at_depth(root, depth)
        }
        ordered_directories = sorted(
            model_directories, key=lambda path: path.as_posix().casefold()
        )
        scan.models_total = len(ordered_directories)
        session.commit()

        for model_directory in ordered_directories:
            _raise_if_scan_cancelled(session, scan_run_id)
            _wait_if_scan_paused(session, scan_run_id)
            scan.current_model_name = model_directory.name
            session.commit()
            relative_path = model_directory.relative_to(root).as_posix()
            try:
                is_candidate = _is_model_candidate(model_directory, source)
            except OSError as error:
                _add_issue(
                    session,
                    scan,
                    relative_path,
                    "error",
                    "directory_unreadable",
                    str(error),
                )
                session.commit()
                continue
            if not is_candidate:
                _delete_empty_placeholder(session, source.id, relative_path)
                continue
            try:
                normalized_path, values = parse_library_path(
                    directory_pattern=source.directory_pattern,
                    model_pattern=source.model_pattern,
                    relative_path=relative_path,
                )
            except PathPatternError as error:
                _add_issue(
                    session,
                    scan,
                    relative_path,
                    "warning",
                    "path_pattern_mismatch",
                    str(error),
                )
                session.commit()
                continue

            scan.current_model_name = values["model"]
            session.commit()

            if scan.mode == "incremental":
                known_model = session.scalar(
                    select(LibraryModel).where(
                        LibraryModel.library_source_id == source.id,
                        LibraryModel.relative_path == normalized_path,
                    )
                )
                if known_model is not None:
                    known_model.last_seen_at = utc_now()
                    known_model.last_seen_scan_id = scan.id
                    known_model.status = "available"
                    scan.models_found += 1
                    scan.models_skipped += 1
                    session.commit()
                    continue
            try:
                _scan_model(
                    session,
                    scan,
                    source,
                    root,
                    model_directory,
                    normalized_path,
                    values,
                )
                session.commit()
            except Exception as error:
                session.rollback()
                scan = session.get(ScanRun, scan_run_id)
                if scan is None:
                    raise
                _add_issue(
                    session,
                    scan,
                    normalized_path,
                    "error",
                    "model_scan_failed",
                    str(error),
                )
                session.commit()

        missing_result = session.execute(
            update(LibraryModel)
            .where(
                LibraryModel.library_source_id == source.id,
                or_(
                    LibraryModel.last_seen_scan_id.is_(None),
                    LibraryModel.last_seen_scan_id != scan.id,
                ),
            )
            .values(status="missing")
        )
        scan.models_missing = missing_result.rowcount or 0
        recompute_inherited_tags(session, source.id)
        scan.status = "completed_with_errors" if scan.issues_count else "completed"
    except ScanCancelled:
        session.rollback()
        scan = session.get(ScanRun, scan_run_id)
        if scan is not None:
            scan.status = "cancelled"
    except Exception as error:
        session.rollback()
        scan = session.get(ScanRun, scan_run_id)
        if scan is not None:
            scan.status = "failed"
            scan.error_message = str(error)[:4000]
    finally:
        scan = session.get(ScanRun, scan_run_id)
        if scan is not None:
            scan.current_model_name = None
            scan.finished_at = utc_now()
        session.commit()


def _reconcile_source_archive_images(
    session: Session,
    scan: ScanRun,
    source: LibrarySource,
    root: Path,
) -> None:
    """Repair archive-derived image caches without re-parsing library metadata."""
    models = list(
        session.scalars(
            select(LibraryModel)
            .where(
                LibraryModel.library_source_id == source.id,
                LibraryModel.status == "available",
            )
            .order_by(LibraryModel.id)
        )
    )
    scan.models_total = len(models)
    session.commit()
    for model in models:
        scan.current_model_name = model.name
        session.commit()
        _raise_if_scan_cancelled(session, scan.id)
        _wait_if_scan_paused(session, scan.id)
        archives = list(
            session.scalars(
                select(Archive)
                .where(Archive.model_id == model.id, Archive.status == "ready")
                .order_by(Archive.filename.collate("NOCASE"), Archive.id)
            )
        )
        archive_paths = [
            root / PurePosixPath(archive.relative_path)
            for archive in archives
            if _path_stays_inside(root / PurePosixPath(archive.relative_path), root)
            and (root / PurePosixPath(archive.relative_path)).is_file()
        ]
        if not archive_paths:
            continue
        scan.models_found += 1
        try:
            archive_primary = _sync_archive_images(session, scan, model, root, archive_paths)
            if archive_primary is None:
                _restore_source_primary(session, model)
            _apply_primary_override(session, model)
            session.commit()
        except Exception as error:
            session.rollback()
            scan = session.get(ScanRun, scan.id)
            if scan is None:
                raise
            _add_issue(
                session,
                scan,
                model.relative_path,
                "error",
                "archive_image_reconciliation_failed",
                str(error),
                model.id,
            )
            session.commit()

def rescan_model(
    session: Session,
    model_id: int,
    *,
    force_image_rebuild: bool = False,
    scan: ScanRun | None = None,
) -> ScanRun:
    """Re-scan one model without enumerating its entire library source."""
    model = session.get(LibraryModel, model_id)
    if model is None:
        raise LookupError("Model not found")
    source = session.get(LibrarySource, model.library_source_id)
    if source is None:
        raise LookupError("Library source not found")

    if scan is None:
        scan = create_scan_run(
            session,
            source.id,
            trigger="model_image_rebuild" if force_image_rebuild else "model_rescan",
            mode="full",
        )
    scan.target_model_id = model.id
    scan.target_model_name = model.name
    scan.status = "running"
    scan.started_at = utc_now()
    session.commit()

    cache_backups: list[tuple[Path, Path]] = []
    rebuild_succeeded = False
    try:
        root = _validated_source_root(source)
        model_directory = root / PurePosixPath(model.relative_path)
        if not _path_stays_inside(model_directory, root) or not model_directory.is_dir():
            model.status = "missing"
            scan.models_missing = 1
        else:
            normalized_path, values = parse_library_path(
                directory_pattern=source.directory_pattern,
                model_pattern=source.model_pattern,
                relative_path=model.relative_path,
            )
            if force_image_rebuild:
                archive_images = list(
                    session.scalars(
                        select(ModelImage).where(
                            ModelImage.model_id == model.id,
                            ModelImage.storage_kind == "archive",
                        )
                    )
                )
                cache_keys = {
                    key
                    for image in archive_images
                    for key in (image.thumbnail_key, image.cache_key)
                    if key
                }
                for archive in session.scalars(
                    select(Archive).where(Archive.model_id == model.id)
                ):
                    # Force a fresh manifest while retaining image records as a
                    # rollback-safe target for regenerated cache derivatives.
                    archive.modified_ns = -1
                model.archive_image_policy_key = None
                session.flush()
                for key in cache_keys:
                    cache_path = safe_cache_path(get_settings().cache_dir, key)
                    if not cache_path.is_file():
                        continue
                    backup_path = cache_path.with_name(f"{cache_path.name}.rebuild-{scan.id}")
                    os.replace(cache_path, backup_path)
                    cache_backups.append((cache_path, backup_path))
            _scan_model(
                session,
                scan,
                source,
                root,
                model_directory,
                normalized_path,
                values,
            )
        scan.status = "completed_with_errors" if scan.issues_count else "completed"
        rebuild_succeeded = True
    except Exception as error:
        session.rollback()
        scan = session.get(ScanRun, scan.id)
        if scan is None:
            raise
        scan.status = "failed"
        scan.error_message = str(error)[:4000]
    finally:
        if not rebuild_succeeded:
            for cache_path, backup_path in cache_backups:
                if cache_path.exists():
                    cache_path.unlink()
                if backup_path.exists():
                    os.replace(backup_path, cache_path)
        scan = session.get(ScanRun, scan.id)
        if scan is not None:
            scan.finished_at = utc_now()
        session.commit()
    if rebuild_succeeded:
        for _cache_path, backup_path in cache_backups:
            backup_path.unlink(missing_ok=True)
    return scan

def _validated_source_root(source: LibrarySource) -> Path:
    settings = get_settings()
    allowed = settings.allowed_library_root.resolve(strict=True)
    root = Path(source.root_path).resolve(strict=True)
    if not root.is_dir():
        raise RuntimeError("Library source path is not a directory")
    if root != allowed and allowed not in root.parents:
        raise RuntimeError("Library source resolves outside the allowed root")
    if not os.access(root, os.R_OK | os.X_OK):
        raise RuntimeError("Library source is not readable")
    return root


def _directories_at_depth(root: Path, target_depth: int):
    for current, directories, _files in os.walk(root, followlinks=False):
        current_path = Path(current)
        depth = len(current_path.relative_to(root).parts)
        if depth == target_depth:
            directories.clear()
            yield current_path
        elif depth > target_depth:
            directories.clear()


def _scan_model(
    session: Session,
    scan: ScanRun,
    source: LibrarySource,
    root: Path,
    model_directory: Path,
    relative_path: str,
    values: dict[str, str],
) -> None:
    model = session.scalar(
        select(LibraryModel).where(
            LibraryModel.library_source_id == source.id,
            LibraryModel.relative_path == relative_path,
        )
    )
    is_new = model is None
    now = utc_now()
    if model is None:
        model = LibraryModel(
            library_source_id=source.id,
            relative_path=relative_path,
            name=values["model"],
            first_seen_at=now,
        )
        session.add(model)
        session.flush()
        scan.models_added += 1
    else:
        scan.models_updated += 1

    model.name = values["model"]
    model.variant = values.get("variant")
    model.creator = values.get("creator")
    model.franchise = values.get("franchise")
    model.series = values.get("series")
    model.collection = values.get("collection")
    model.last_seen_at = now
    model.last_seen_scan_id = scan.id
    model.status = "available"
    scan.models_found += 1

    files = [path for path in model_directory.iterdir() if path.is_file()]
    safe_files = [path for path in files if _path_stays_inside(path, root)]
    if len(safe_files) != len(files):
        _add_issue(
            session,
            scan,
            relative_path,
            "error",
            "unsafe_symlink",
            "One or more files resolve outside the library source",
            model.id,
        )

    archive_extensions = {f".{item.casefold()}" for item in source.archive_formats}
    image_extensions = {f".{item.casefold()}" for item in source.image_formats}
    archives = sorted(
        (path for path in safe_files if path.suffix.casefold() in archive_extensions),
        key=lambda path: path.name.casefold(),
    )
    images = sorted(
        (path for path in safe_files if path.suffix.casefold() in image_extensions),
        key=lambda path: (_image_priority(path), path.name.casefold()),
    )

    fallback_primary = _sync_images(session, model, root, images)

    if not archives:
        model.status = "incomplete"
        session.execute(delete(Archive).where(Archive.model_id == model.id))
        _add_issue(
            session,
            scan,
            relative_path,
            "error",
            "archive_missing",
            "No supported archive was found",
            model.id,
        )
        _sync_fallback_or_report_missing(
            session, scan, model, relative_path, fallback_primary
        )
        _apply_primary_override(session, model)
        _apply_automatic_tags(session, scan, model)
        return

    archives_ok = _sync_archives(session, scan, model, root, archives)
    has_available_images = session.scalar(
        select(ModelImage.id)
        .where(
            ModelImage.model_id == model.id,
            ModelImage.storage_kind == "archive",
            ModelImage.is_available.is_(True),
        )
        .limit(1)
    ) is not None
    archive_primary = None
    if scan.mode != "missing_images" or not has_available_images:
        archive_primary = _sync_archive_images(
            session,
            scan,
            model,
            root,
            archives,
        )
    elif fallback_primary is not None:
        archive_primary = fallback_primary
    else:
        archive_primary = session.scalar(
            select(ModelImage)
            .where(
            ModelImage.model_id == model.id,
            ModelImage.storage_kind == "archive",
            ModelImage.is_available.is_(True),
        )
            .order_by(ModelImage.is_primary.desc(), ModelImage.id)
            .limit(1)
            )
    if archive_primary is None:
        _sync_fallback_or_report_missing(
            session, scan, model, relative_path, fallback_primary
        )
    else:
        session.execute(
            update(ModelImage)
            .where(
                ModelImage.model_id == model.id,
                ModelImage.storage_kind == "source",
            )
            .values(is_primary=False)
        )
    _apply_primary_override(session, model)
    _apply_automatic_tags(session, scan, model)
    if not archives_ok:
        model.status = "error"
    elif is_new and model.status == "available":
        model.status = "available"


def _apply_automatic_tags(session: Session, scan: ScanRun, model: LibraryModel) -> None:
    try:
        with session.begin_nested():
            result = recompute_automatic_tags(session, [model.id])
    except Exception as error:
        _add_issue(
            session,
            scan,
            model.relative_path,
            "warning",
            "automatic_tag_evaluation_failed",
            str(error),
            model.id,
        )
        return
    scan.automatic_tag_matches += result.matches
    scan.automatic_tags_added += result.assignments_added
    scan.automatic_tags_removed += result.assignments_removed


def _is_model_candidate(directory: Path, source: LibrarySource) -> bool:
    supported_extensions = {
        f".{item.casefold()}" for item in (*source.archive_formats, *source.image_formats)
    }
    return any(
        path.is_file() and path.suffix.casefold() in supported_extensions
        for path in directory.iterdir()
    )


def _delete_empty_placeholder(session: Session, source_id: int, relative_path: str) -> None:
    model = session.scalar(
        select(LibraryModel).where(
            LibraryModel.library_source_id == source_id,
            LibraryModel.relative_path == relative_path,
        )
    )
    if model is None:
        return
    has_archive = session.scalar(select(Archive.id).where(Archive.model_id == model.id).limit(1))
    has_image = session.scalar(
        select(ModelImage.id).where(ModelImage.model_id == model.id).limit(1)
    )
    if has_archive is None and has_image is None:
        session.delete(model)
        session.commit()


ARCHIVE_LISTING_POLICY_KEY = "solid-7z-packed-size-v2"


def _sync_archive(
    session: Session,
    scan: ScanRun,
    model: LibraryModel,
    root: Path,
    archive_path: Path,
) -> bool:
    stat = archive_path.stat()
    relative_path = archive_path.relative_to(root).as_posix()
    archive = session.scalar(
        select(Archive).where(
            Archive.model_id == model.id,
            Archive.relative_path == relative_path,
        )
    )
    unchanged = (
        archive is not None
        and archive.relative_path == relative_path
        and archive.size_bytes == stat.st_size
        and archive.modified_ns == stat.st_mtime_ns
        and archive.status == "ready"
    )
    requires_listing_refresh = (
        archive is not None
        and archive.format == "7z"
        and archive.listing_policy_key != ARCHIVE_LISTING_POLICY_KEY
    )
    if unchanged and not requires_listing_refresh:
        return True

    if archive is not None:
        session.execute(delete(ArchiveEntry).where(ArchiveEntry.archive_id == archive.id))
    else:
        archive = Archive(
            model_id=model.id,
            filename=archive_path.name,
            relative_path=relative_path,
            format=archive_path.suffix.casefold().lstrip("."),
            size_bytes=stat.st_size,
            modified_ns=stat.st_mtime_ns,
            status="pending",
            error_message=None,
            entry_count=0,
            uncompressed_size_bytes=0,
            listing_policy_key=None,
        )
        session.add(archive)

    archive.filename = archive_path.name
    archive.relative_path = relative_path
    archive.format = archive_path.suffix.casefold().lstrip(".")
    archive.size_bytes = stat.st_size
    archive.modified_ns = stat.st_mtime_ns
    archive.status = "pending"
    archive.error_message = None
    archive.entry_count = 0
    archive.uncompressed_size_bytes = 0
    archive.listing_policy_key = None
    session.flush()

    # 7-Zip can take a long time on very large archives. Persist the pending
    # state first so SQLite does not retain its single writer lock while the
    # external process is running.
    session.commit()

    settings = get_settings()
    try:
        entries = list_archive(
            str(archive_path),
            command=settings.archive_command,
            timeout_seconds=settings.archive_timeout_seconds,
            max_entries=settings.archive_max_entries,
            max_output_bytes=settings.archive_max_output_bytes,
        )
    except ArchiveReadError as error:
        archive.status = "error"
        archive.error_message = str(error)[:4000]
        _add_issue(
            session,
            scan,
            model.relative_path,
            "error",
            "archive_unreadable",
            archive.error_message,
            model.id,
        )
        return False

    session.add_all(
        ArchiveEntry(
            archive_id=archive.id,
            path=entry.path,
            name=entry.name,
            is_directory=entry.is_directory,
            size_bytes=entry.size_bytes,
            compressed_size_bytes=entry.compressed_size_bytes,
            crc=entry.crc,
            modified_at=entry.modified_at,
        )
        for entry in entries
    )
    archive.entry_count = len(entries)
    archive.uncompressed_size_bytes = sum(
        entry.size_bytes or 0 for entry in entries if not entry.is_directory
    )
    archive.content_scanned_at = utc_now()
    archive.listing_policy_key = ARCHIVE_LISTING_POLICY_KEY
    archive.status = "ready"
    return True


def _sync_archives(
    session: Session,
    scan: ScanRun,
    model: LibraryModel,
    root: Path,
    archive_paths: list[Path],
) -> bool:
    expected_paths = {archive_path.relative_to(root).as_posix() for archive_path in archive_paths}
    stale_archives = session.scalars(
        select(Archive).where(
            Archive.model_id == model.id,
            Archive.relative_path.not_in(expected_paths),
        )
    ).all()
    for archive in stale_archives:
        for key in session.execute(
            select(ModelImage.thumbnail_key, ModelImage.cache_key).where(
                ModelImage.archive_id == archive.id
            )
        ):
            remove_cached_file(get_settings().cache_dir, key.thumbnail_key)
            remove_cached_file(get_settings().cache_dir, key.cache_key)
        session.execute(delete(ArchiveEntry).where(ArchiveEntry.archive_id == archive.id))
        session.delete(archive)

    all_ready = True
    for archive_path in archive_paths:
        if not _sync_archive(session, scan, model, root, archive_path):
            all_ready = False
    return all_ready


def _sync_images(
    session: Session,
    model: LibraryModel,
    root: Path,
    image_paths: list[Path],
) -> tuple[ModelImage, Path] | None:
    existing = {
        image.relative_path: image
        for image in session.scalars(
            select(ModelImage).where(
                ModelImage.model_id == model.id,
                ModelImage.storage_kind == "source",
            )
        )
    }
    seen: set[str] = set()
    primary: tuple[ModelImage, Path] | None = None
    for index, image_path in enumerate(image_paths):
        stat = image_path.stat()
        relative_path = image_path.relative_to(root).as_posix()
        image = existing.get(relative_path)
        if image is None:
            image = ModelImage(
                model_id=model.id,
                relative_path=relative_path,
                storage_kind="source",
            )
            session.add(image)
        image.filename = image_path.name
        image.format = image_path.suffix.casefold().lstrip(".")
        image.size_bytes = stat.st_size
        image.modified_ns = stat.st_mtime_ns
        image.is_primary = index == 0
        image.is_available = True
        if index == 0:
            primary = (image, image_path)
        seen.add(relative_path)

    for relative_path, image in existing.items():
        if relative_path not in seen:
            image.is_available = False
            image.is_primary = False
    session.flush()
    return primary


def _sync_fallback_or_report_missing(
    session: Session,
    scan: ScanRun,
    model: LibraryModel,
    relative_path: str,
    fallback_primary: tuple[ModelImage, Path] | None,
) -> None:
    if fallback_primary is None:
        model.status = "incomplete"
        _add_issue(
            session,
            scan,
            relative_path,
            "error",
            "image_missing",
            "No supported image was found in the folder or its archives",
            model.id,
        )
        return
    image_record, image_path = fallback_primary
    image_record.is_primary = True
    # Thumbnail generation is file I/O and can be slow for large source images.
    # Release pending scanner writes before doing that work.
    session.commit()
    _sync_primary_thumbnail(session, scan, model, image_record, image_path)


ARCHIVE_IMAGE_SELECTION_VERSION = 1


def _archive_image_selection_policy_key(settings) -> str:
    """Return a stable key for settings that change desired archive images."""
    policy = {
        "version": ARCHIVE_IMAGE_SELECTION_VERSION,
        "max_candidates": settings.archive_image_max_candidates,
        "max_entry_bytes": settings.archive_image_max_entry_bytes,
        "max_compressed_bytes": settings.archive_image_max_compressed_bytes,
        "max_total_bytes": settings.archive_image_max_total_bytes,
        "max_pixels": settings.archive_image_max_pixels,
    }
    encoded = json.dumps(policy, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _archive_entry_fingerprint(entry: ArchiveEntry) -> str:
    """Identify an archive entry without extracting its image payload."""
    identity = {
        "path": entry.path,
        "size_bytes": entry.size_bytes,
        "compressed_size_bytes": entry.compressed_size_bytes,
        "crc": entry.crc,
        "modified_at": entry.modified_at,
    }
    encoded = json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _sync_archive_images(
    session: Session,
    scan: ScanRun,
    model: LibraryModel,
    root: Path,
    archive_paths: list[Path],
) -> ModelImage | None:
    settings = get_settings()
    policy_key = _archive_image_selection_policy_key(settings)
    records = list(
        session.scalars(
            select(Archive)
            .where(Archive.model_id == model.id, Archive.status == "ready")
            .order_by(Archive.filename.collate("NOCASE"), Archive.id)
        )
    )
    path_by_relative = {
        path.relative_to(root).as_posix(): path for path in archive_paths
    }
    selected: list[tuple[Archive, ArchiveEntry]] = []
    selected_bytes = 0
    # Allow later candidates to replace files that fail validation or conversion,
    # while retaining a strict, bounded amount of archive work per model.
    max_attempts = max(
        settings.archive_image_max_candidates * 4,
        settings.archive_image_max_candidates,
    )
    candidate_pool: list[tuple[Archive, ArchiveEntry, ListedArchiveEntry]] = []
    for archive in records:
        entries = list(
            session.scalars(
                select(ArchiveEntry)
                .where(ArchiveEntry.archive_id == archive.id)
                .order_by(ArchiveEntry.path.collate("NOCASE"))
            )
        )
        listed_entries = [
            ListedArchiveEntry(
                path=entry.path,
                name=entry.name,
                is_directory=entry.is_directory,
                size_bytes=entry.size_bytes,
                compressed_size_bytes=entry.compressed_size_bytes,
                crc=entry.crc,
                modified_at=entry.modified_at,
            )
            for entry in entries
        ]
        entry_by_path = {entry.path: entry for entry in entries}
        candidates = select_archive_image_candidates(
            listed_entries,
            max_candidates=max_attempts,
            max_entry_bytes=settings.archive_image_max_entry_bytes,
            max_compressed_bytes=settings.archive_image_max_compressed_bytes,
            max_total_bytes=settings.archive_image_max_total_bytes,
        )
        candidate_pool.extend(
            (archive, entry_by_path[candidate.path], candidate)
            for candidate in candidates
        )

    candidate_pool.sort(
        key=lambda item: (
            archive_image_candidate_sort_key(item[2]),
            item[0].filename.casefold(),
            item[0].relative_path.casefold(),
        )
    )
    for archive, entry, _candidate in candidate_pool:
        if len(selected) >= max_attempts:
            break
        if entry.size_bytes is None:
            continue
        if selected_bytes + entry.size_bytes > settings.archive_image_max_total_bytes:
            continue
        selected.append((archive, entry))
        selected_bytes += entry.size_bytes
    existing = {
        image.relative_path: image
        for image in session.scalars(
            select(ModelImage).where(
                ModelImage.model_id == model.id,
                ModelImage.storage_kind == "archive",
            )
        )
    }
    desired_paths = {
        f"archive/{archive.id}/{entry.path}" for archive, entry in selected
    }
    for relative_path, image in existing.items():
        if relative_path not in desired_paths:
            remove_cached_file(settings.cache_dir, image.thumbnail_key)
            remove_cached_file(settings.cache_dir, image.cache_key)
            session.delete(image)
            scan.archive_images_removed += 1

    policy_changed = model.archive_image_policy_key != policy_key

    selected_by_archive: dict[int, list[ArchiveEntry]] = {}
    for archive, entry in selected:
        selected_by_archive.setdefault(archive.id, []).append(entry)
    primary: ModelImage | None = None
    for archive in records:
        archive_entries = selected_by_archive.get(archive.id)
        if not archive_entries:
            continue
        source_path = path_by_relative.get(archive.relative_path)
        if source_path is None:
            continue

        pending_entries = [
            entry
            for entry in archive_entries
            if (
                policy_changed
                or existing.get(f"archive/{archive.id}/{entry.path}") is None
                or not _archive_image_cache_is_current(
                    existing[f"archive/{archive.id}/{entry.path}"],
                    archive,
                    entry,
                    settings.cache_dir,
                )
            )
        ]
        scan.archive_images_reused += len(archive_entries) - len(pending_entries)

        if pending_entries:
            candidates = [
                ListedArchiveEntry(
                    path=entry.path,
                    name=entry.name,
                    is_directory=entry.is_directory,
                    size_bytes=entry.size_bytes,
                    compressed_size_bytes=entry.compressed_size_bytes,
                    crc=entry.crc,
                    modified_at=entry.modified_at,
                )
                for entry in pending_entries
            ]
            # The image batch is external 7-Zip and image-processing work. Keep
            # the database transaction short so catalogue and auth requests can
            # continue while the batch is running.
            session.commit()
            failed_images = 0
            failure_messages: set[str] = set()
            for batch_entries, extracted_paths, batch_error in iter_extracted_archive_image_batches(
                source_path,
                candidates,
                command=settings.archive_command,
                data_dir=settings.data_dir,
                timeout_seconds=settings.archive_image_timeout_seconds,
                max_entry_bytes=settings.archive_image_max_entry_bytes,
                max_compressed_bytes=settings.archive_image_max_compressed_bytes,
                threads=settings.archive_image_threads,
            ):
                if batch_error is not None:
                    failed_images += len(batch_entries)
                    error_msg = str(batch_error)
                    failure_messages.add(error_msg)
                    # Log the error for better debugging
                    logger = logging.getLogger(__name__)
                    logger.warning(f"Archive image processing failed for {len(batch_entries)} entries in {source_path}: {error_msg}")
                    for entry in batch_entries:
                        relative_path = f"archive/{archive.id}/{entry.path}"
                        image = existing.pop(relative_path, None)
                        if image is not None:
                            _discard_archive_image(session, image)
                    continue

                for entry in batch_entries:
                    relative_path = f"archive/{archive.id}/{entry.path}"
                    image = existing.get(relative_path)
                    if image is None:
                        image = ModelImage(
                            model_id=model.id,
                            relative_path=relative_path,
                            storage_kind="archive",
                            archive_id=archive.id,
                            archive_entry_path=entry.path,
                            archive_entry_fingerprint=_archive_entry_fingerprint(entry),
                        )
                        session.add(image)
                        existing[relative_path] = image
                    try:
                        validated = validate_extracted_archive_image(
                            extracted_paths[entry.path],
                            max_pixels=settings.archive_image_max_pixels,
                        )
                        signature = (
                            f"archive/{model.library_source_id}/{archive.relative_path}/"
                            f"{archive.size_bytes}/{archive.modified_ns}/{entry.path}/{entry.crc or ''}"
                        )
                        image.cache_key = generate_cached_webp(
                            validated.path,
                            relative_source_path=signature,
                            source_size=validated.size_bytes,
                            source_modified_ns=archive.modified_ns,
                            cache_root=settings.cache_dir,
                            cache_namespace="archive-images",
                            max_size=settings.archive_image_detail_size,
                            quality=settings.thumbnail_quality,
                            max_output_bytes=settings.archive_image_detail_max_bytes,
                            webp_method=settings.archive_image_webp_method,
                        )
                        image.thumbnail_key = generate_thumbnail(
                            validated.path,
                            relative_source_path=signature,
                            source_size=validated.size_bytes,
                            source_modified_ns=archive.modified_ns,
                            cache_root=settings.cache_dir,
                            max_size=settings.thumbnail_size,
                            quality=settings.thumbnail_quality,
                            max_output_bytes=settings.thumbnail_max_bytes,
                        )
                        image.format = validated.format
                        image.filename = PurePosixPath(entry.path).name
                        image.size_bytes = validated.size_bytes
                        image.modified_ns = archive.modified_ns
                        image.archive_id = archive.id
                        image.archive_entry_path = entry.path
                        image.archive_entry_fingerprint = _archive_entry_fingerprint(entry)
                        image.thumbnail_status = "ready"
                        image.thumbnail_error = None
                        scan.archive_images_generated += 1
                    except (ArchiveImageError, ThumbnailError) as error:
                        _discard_archive_image(session, image)
                        existing.pop(relative_path, None)
                        _add_issue(
                            session,
                            scan,
                            model.relative_path,
                            "warning",
                            "archive_image_failed",
                            str(error),
                            model.id,
                        )
            if failed_images:
                detail = "; ".join(sorted(failure_messages))
                _add_issue(
                    session,
                    scan,
                    model.relative_path,
                    "warning",
                    "archive_image_batch_failed",
                    f"{failed_images} archive image(s) could not be extracted: {detail}",
                    model.id,
                )

        for entry in archive_entries:
            image = existing.get(f"archive/{archive.id}/{entry.path}")
            if image is None:
                continue
            image.is_available = True
            image.is_primary = primary is None
            if primary is None:
                primary = image

    successful_images = [
        existing[f"archive/{archive.id}/{entry.path}"]
        for archive, entry in selected
        if (
            existing.get(f"archive/{archive.id}/{entry.path}") is not None
            and existing[f"archive/{archive.id}/{entry.path}"].is_available
        )
    ]
    kept_images = successful_images[: settings.archive_image_max_candidates]
    for image in successful_images[settings.archive_image_max_candidates :]:
        existing.pop(image.relative_path, None)
        _discard_archive_image(session, image)
        scan.archive_images_removed += 1
    for image in kept_images:
        image.is_primary = image is kept_images[0]
    primary = kept_images[0] if kept_images else None
    model.archive_image_policy_key = policy_key
    return primary

def _discard_archive_image(session: Session, image: ModelImage) -> None:
    if image.id is None:
        session.expunge(image)
        return
    session.delete(image)


def _archive_image_cache_is_current(
    image: ModelImage,
    archive: Archive,
    entry: ArchiveEntry,
    cache_root: Path,
) -> bool:
    if (
        image.size_bytes != entry.size_bytes
        or image.modified_ns != archive.modified_ns
        or image.archive_entry_fingerprint != _archive_entry_fingerprint(entry)
        or not image.cache_key
        or not image.thumbnail_key
    ):
        return False
    try:
        return (
            safe_cache_path(cache_root, image.cache_key).is_file()
            and safe_cache_path(cache_root, image.thumbnail_key).is_file()
        )
    except ThumbnailError:
        return False


def _restore_source_primary(session: Session, model: LibraryModel) -> None:
    """Keep a folder image visible when an archive has no usable images."""
    source_image = session.scalar(
        select(ModelImage)
        .where(
            ModelImage.model_id == model.id,
            ModelImage.storage_kind == "source",
            ModelImage.is_available.is_(True),
        )
        .order_by(ModelImage.is_primary.desc(), ModelImage.filename.collate("NOCASE"))
        .limit(1)
    )
    if source_image is None:
        return
    session.execute(
        update(ModelImage)
        .where(ModelImage.model_id == model.id)
        .values(is_primary=False)
    )
    source_image.is_primary = True

def _apply_primary_override(session: Session, model: LibraryModel) -> None:
    override = session.scalar(
        select(ModelImage)
        .where(
            ModelImage.model_id == model.id,
            ModelImage.is_available.is_(True),
            ModelImage.is_primary_override.is_(True),
        )
        .order_by(ModelImage.id)
    )
    if override is None:
        return
    session.execute(
        update(ModelImage)
        .where(ModelImage.model_id == model.id)
        .values(is_primary=False)
    )
    override.is_primary = True


def _sync_primary_thumbnail(
    session: Session,
    scan: ScanRun,
    model: LibraryModel,
    image: ModelImage,
    source_path: Path,
) -> None:
    settings = get_settings()
    old_key = image.thumbnail_key
    try:
        key = generate_thumbnail(
            source_path,
            relative_source_path=f"{model.library_source_id}/{image.relative_path}",
            source_size=image.size_bytes,
            source_modified_ns=image.modified_ns,
            cache_root=settings.cache_dir,
            max_size=settings.thumbnail_size,
            quality=settings.thumbnail_quality,
            max_output_bytes=settings.thumbnail_max_bytes,
        )
    except ThumbnailError as error:
        image.thumbnail_status = "error"
        image.thumbnail_error = str(error)[:4000]
        _add_issue(
            session,
            scan,
            model.relative_path,
            "warning",
            "thumbnail_failed",
            image.thumbnail_error,
            model.id,
        )
        return

    image.thumbnail_key = key
    image.thumbnail_status = "ready"
    image.thumbnail_error = None
    if old_key != key:
        remove_cached_thumbnail(settings.cache_dir, old_key)


def _image_priority(path: Path) -> int:
    stem = path.stem.casefold()
    preferred = ("cover", "preview", "thumbnail", "render")
    for index, word in enumerate(preferred):
        if word in stem:
            return index
    return len(preferred)


def _path_stays_inside(path: Path, root: Path) -> bool:
    try:
        resolved = path.resolve(strict=True)
    except OSError:
        return False
    return resolved == root or root in resolved.parents


def _add_issue(
    session: Session,
    scan: ScanRun,
    relative_path: str,
    severity: str,
    code: str,
    message: str,
    model_id: int | None = None,
) -> None:
    session.add(
        ScanIssue(
            scan_run_id=scan.id,
            model_id=model_id,
            relative_path=relative_path,
            severity=severity,
            code=code,
            message=message[:4000],
        )
    )
    scan.issues_count += 1
