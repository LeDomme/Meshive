from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from meshive.database import Base


class LibraryModel(Base):
    __tablename__ = "library_models"
    __table_args__ = (UniqueConstraint("library_source_id", "relative_path"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    library_source_id: Mapped[int] = mapped_column(
        ForeignKey("library_sources.id", ondelete="CASCADE"), index=True
    )
    relative_path: Mapped[str] = mapped_column(Text)
    name: Mapped[str] = mapped_column(String(512), index=True)
    variant: Mapped[str | None] = mapped_column(String(255), nullable=True)
    creator: Mapped[str | None] = mapped_column(String(255), index=True)
    franchise: Mapped[str | None] = mapped_column(String(255), index=True)
    series: Mapped[str | None] = mapped_column(String(255), index=True)
    collection: Mapped[str | None] = mapped_column(String(255), index=True)
    status: Mapped[str] = mapped_column(String(30), default="available", index=True)
    last_seen_scan_id: Mapped[int | None] = mapped_column(
        ForeignKey("scan_runs.id", ondelete="SET NULL"), nullable=True
    )
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    archive_image_policy_key: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )


class Archive(Base):
    __tablename__ = "archives"

    id: Mapped[int] = mapped_column(primary_key=True)
    model_id: Mapped[int] = mapped_column(
        ForeignKey("library_models.id", ondelete="CASCADE"), index=True
    )
    filename: Mapped[str] = mapped_column(String(1024))
    relative_path: Mapped[str] = mapped_column(Text)
    format: Mapped[str] = mapped_column(String(10))
    size_bytes: Mapped[int] = mapped_column(Integer)
    modified_ns: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(30), default="pending", index=True)
    entry_count: Mapped[int] = mapped_column(Integer, default=0)
    uncompressed_size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    content_scanned_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class ArchiveEntry(Base):
    __tablename__ = "archive_entries"
    __table_args__ = (UniqueConstraint("archive_id", "path"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    archive_id: Mapped[int] = mapped_column(
        ForeignKey("archives.id", ondelete="CASCADE"), index=True
    )
    path: Mapped[str] = mapped_column(Text)
    name: Mapped[str] = mapped_column(String(1024))
    is_directory: Mapped[bool] = mapped_column(Boolean, default=False)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    compressed_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    crc: Mapped[str | None] = mapped_column(String(64), nullable=True)
    modified_at: Mapped[str | None] = mapped_column(String(64), nullable=True)


class ModelImage(Base):
    __tablename__ = "model_images"
    __table_args__ = (UniqueConstraint("model_id", "relative_path"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    model_id: Mapped[int] = mapped_column(
        ForeignKey("library_models.id", ondelete="CASCADE"), index=True
    )
    filename: Mapped[str] = mapped_column(String(1024))
    relative_path: Mapped[str] = mapped_column(Text)
    format: Mapped[str] = mapped_column(String(10))
    size_bytes: Mapped[int] = mapped_column(Integer)
    modified_ns: Mapped[int] = mapped_column(Integer)
    storage_kind: Mapped[str] = mapped_column(String(20), default="source", index=True)
    archive_id: Mapped[int | None] = mapped_column(
        ForeignKey("archives.id", ondelete="CASCADE"), nullable=True, index=True
    )
    archive_entry_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    archive_entry_fingerprint: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    cache_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    is_primary_override: Mapped[bool] = mapped_column(Boolean, default=False)
    is_available: Mapped[bool] = mapped_column(Boolean, default=True)
    thumbnail_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    thumbnail_status: Mapped[str] = mapped_column(String(30), default="pending", index=True)
    thumbnail_error: Mapped[str | None] = mapped_column(Text, nullable=True)


class ScanRun(Base):
    __tablename__ = "scan_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    library_source_id: Mapped[int] = mapped_column(
        ForeignKey("library_sources.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(String(30), default="pending", index=True)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    pause_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    trigger: Mapped[str] = mapped_column(String(20), default="manual")
    mode: Mapped[str] = mapped_column(String(32), default="full", index=True)
    target_model_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)

    target_model_name: Mapped[str | None] = mapped_column(String(512), nullable=True)
    current_model_name: Mapped[str | None] = mapped_column(String(512), nullable=True)
    models_total: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    models_found: Mapped[int] = mapped_column(Integer, default=0)
    models_added: Mapped[int] = mapped_column(Integer, default=0)
    models_updated: Mapped[int] = mapped_column(Integer, default=0)
    models_missing: Mapped[int] = mapped_column(Integer, default=0)
    models_skipped: Mapped[int] = mapped_column(Integer, default=0)
    archive_images_reused: Mapped[int] = mapped_column(Integer, default=0)
    archive_images_generated: Mapped[int] = mapped_column(Integer, default=0)
    archive_images_removed: Mapped[int] = mapped_column(Integer, default=0)
    automatic_tag_matches: Mapped[int] = mapped_column(Integer, default=0)
    automatic_tags_added: Mapped[int] = mapped_column(Integer, default=0)
    automatic_tags_removed: Mapped[int] = mapped_column(Integer, default=0)
    issues_count: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ScanIssue(Base):
    __tablename__ = "scan_issues"

    id: Mapped[int] = mapped_column(primary_key=True)
    scan_run_id: Mapped[int] = mapped_column(
        ForeignKey("scan_runs.id", ondelete="CASCADE"), index=True
    )
    model_id: Mapped[int | None] = mapped_column(
        ForeignKey("library_models.id", ondelete="SET NULL"), nullable=True
    )
    relative_path: Mapped[str] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(String(20))
    code: Mapped[str] = mapped_column(String(60), index=True)
    message: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
