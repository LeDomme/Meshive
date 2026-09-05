from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint, func
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
    is_folder_name_regex: Mapped[bool] = mapped_column(Boolean, default=False)


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


class FolderNameRegexTagRule(Base):
    __tablename__ = "folder_name_regex_tag_rules"
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


class FolderNameRegexTagMatch(Base):
    __tablename__ = "folder_name_regex_tag_matches"
    __table_args__ = (UniqueConstraint("folder_name_regex_tag_rule_id", "model_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    folder_name_regex_tag_rule_id: Mapped[int] = mapped_column(
        ForeignKey("folder_name_regex_tag_rules.id", ondelete="CASCADE"), index=True
    )
    model_id: Mapped[int] = mapped_column(
        ForeignKey("library_models.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
