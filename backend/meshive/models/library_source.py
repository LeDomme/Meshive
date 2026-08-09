from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from meshive.database import Base


class LibrarySource(Base):
    __tablename__ = "library_sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    root_path: Mapped[str] = mapped_column(Text, unique=True)
    directory_pattern: Mapped[str] = mapped_column(Text)
    model_pattern: Mapped[str | None] = mapped_column(Text, nullable=True)
    archive_formats: Mapped[list[str]] = mapped_column(
        JSON, default=lambda: ["7z", "zip", "rar"]
    )
    image_formats: Mapped[list[str]] = mapped_column(
        JSON, default=lambda: ["jpg", "jpeg", "png", "webp"]
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    scan_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    auto_scan_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    auto_scan_frequency: Mapped[str] = mapped_column(String(10), default="daily")
    auto_scan_time: Mapped[str] = mapped_column(String(5), default="02:00")
    auto_scan_weekday: Mapped[int] = mapped_column(default=0)
    auto_scan_timezone: Mapped[str] = mapped_column(
        String(64), default="Europe/Berlin"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
