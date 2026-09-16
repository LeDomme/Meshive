from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from meshive.database import Base


class CreatorProfile(Base):
    __tablename__ = "creator_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    display_name: Mapped[str] = mapped_column(String(255))
    normalized_name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    artwork_id: Mapped[int | None] = mapped_column(
        ForeignKey("metadata_artwork.id", ondelete="SET NULL"), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CreatorAlias(Base):
    __tablename__ = "creator_aliases"

    id: Mapped[int] = mapped_column(primary_key=True)
    creator_profile_id: Mapped[int] = mapped_column(
        ForeignKey("creator_profiles.id", ondelete="CASCADE"), index=True
    )
    alias: Mapped[str] = mapped_column(String(255))
    normalized_alias: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class CreatorLink(Base):
    __tablename__ = "creator_metadata_links"
    __table_args__ = (
        UniqueConstraint("creator_name", "kind", "label"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    creator_profile_id: Mapped[int | None] = mapped_column(
        ForeignKey("creator_profiles.id", ondelete="SET NULL"), nullable=True, index=True
    )
    creator_name: Mapped[str] = mapped_column(
        String(255, collation="NOCASE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(40))
    label: Mapped[str] = mapped_column(String(80, collation="NOCASE"))
    url: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
