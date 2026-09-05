from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from meshive.database import Base


class Tag(Base):
    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    color: Mapped[str | None] = mapped_column(String(7), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ModelTag(Base):
    __tablename__ = "model_tags"
    __table_args__ = (UniqueConstraint("model_id", "tag_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    model_id: Mapped[int] = mapped_column(
        ForeignKey("library_models.id", ondelete="CASCADE"), index=True
    )
    tag_id: Mapped[int] = mapped_column(ForeignKey("tags.id", ondelete="CASCADE"), index=True)
    is_direct: Mapped[bool] = mapped_column(Boolean, default=False)
    is_inherited: Mapped[bool] = mapped_column(Boolean, default=False)
    is_automatic: Mapped[bool] = mapped_column(Boolean, default=False)


class FolderTagRule(Base):
    __tablename__ = "folder_tag_rules"
    __table_args__ = (UniqueConstraint("library_source_id", "relative_path", "tag_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    library_source_id: Mapped[int] = mapped_column(
        ForeignKey("library_sources.id", ondelete="CASCADE"), index=True
    )
    relative_path: Mapped[str] = mapped_column(Text)
    tag_id: Mapped[int] = mapped_column(ForeignKey("tags.id", ondelete="CASCADE"), index=True)
    recursive: Mapped[bool] = mapped_column(Boolean, default=True)


class AutomaticTagRule(Base):
    __tablename__ = "automatic_tag_rules"
    __table_args__ = (UniqueConstraint("tag_id", "pattern_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tag_id: Mapped[int] = mapped_column(ForeignKey("tags.id", ondelete="CASCADE"), index=True)
    pattern: Mapped[str] = mapped_column(String(255))
    pattern_key: Mapped[str] = mapped_column(String(255))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class AutomaticTagMatch(Base):
    __tablename__ = "automatic_tag_matches"
    __table_args__ = (UniqueConstraint("automatic_tag_rule_id", "model_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    automatic_tag_rule_id: Mapped[int] = mapped_column(
        ForeignKey("automatic_tag_rules.id", ondelete="CASCADE"), index=True
    )
    model_id: Mapped[int] = mapped_column(
        ForeignKey("library_models.id", ondelete="CASCADE"), index=True
    )
    matched_path: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TagAssignmentRule(Base):
    """Canonical foundation for future automatic tag-assignment rules.

    Phase 1 deliberately leaves the legacy rule tables authoritative.
    """

    __tablename__ = "tag_assignment_rules"
    __table_args__ = (
        CheckConstraint("match_mode IN ('contains', 'regex', 'path_relation')"),
        CheckConstraint(
            "path_relation IS NULL OR path_relation IN "
            "('direct_child', 'self_or_descendant')"
        ),
        UniqueConstraint("legacy_kind", "legacy_rule_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tag_id: Mapped[int] = mapped_column(ForeignKey("tags.id", ondelete="CASCADE"), index=True)
    library_source_id: Mapped[int | None] = mapped_column(
        ForeignKey("library_sources.id", ondelete="CASCADE"), nullable=True, index=True
    )
    match_mode: Mapped[str] = mapped_column(String(32))
    pattern: Mapped[str | None] = mapped_column(String(255), nullable=True)
    pattern_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    path_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    path_relation: Mapped[str | None] = mapped_column(String(32), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    legacy_kind: Mapped[str | None] = mapped_column(String(32), nullable=True)
    legacy_rule_id: Mapped[int | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class TagAssignmentRuleTarget(Base):
    __tablename__ = "tag_assignment_rule_targets"
    __table_args__ = (
        CheckConstraint(
            "target_type IN ('model_relative_path', 'archive_filename', "
            "'archive_entry_path', 'archive_entry_name')"
        ),
        CheckConstraint("folder_segment = 0 OR target_type = 'model_relative_path'"),
        UniqueConstraint("tag_assignment_rule_id", "target_type", "folder_segment"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tag_assignment_rule_id: Mapped[int] = mapped_column(
        ForeignKey("tag_assignment_rules.id", ondelete="CASCADE"), index=True
    )
    target_type: Mapped[str] = mapped_column(String(32))
    folder_segment: Mapped[bool] = mapped_column(Boolean, default=False)


class TagAssignmentRuleMatch(Base):
    __tablename__ = "tag_assignment_rule_matches"
    __table_args__ = (UniqueConstraint("tag_assignment_rule_id", "model_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tag_assignment_rule_id: Mapped[int] = mapped_column(
        ForeignKey("tag_assignment_rules.id", ondelete="CASCADE"), index=True
    )
    model_id: Mapped[int] = mapped_column(
        ForeignKey("library_models.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
