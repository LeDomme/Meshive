from datetime import datetime
from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column
from meshive.database import Base


class BackupSchedule(Base):
    __tablename__ = "backup_schedule"
    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    frequency: Mapped[str] = mapped_column(String(10), default="daily")
    time_of_day: Mapped[str] = mapped_column(String(5), default="03:00")
    weekday: Mapped[int] = mapped_column(Integer, default=0)
    timezone: Mapped[str] = mapped_column(String(64), default="Europe/Berlin")
    destination: Mapped[str] = mapped_column(String(255), default="automatic")
    retention_days: Mapped[int] = mapped_column(Integer, default=30)
    retention_count: Mapped[int] = mapped_column(Integer, default=14)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class BackupRun(Base):
    __tablename__ = "backup_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    status: Mapped[str] = mapped_column(String(20), index=True)
    trigger: Mapped[str] = mapped_column(String(20))
    path: Mapped[str | None] = mapped_column(Text, nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
