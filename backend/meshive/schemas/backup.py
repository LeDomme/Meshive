from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class BackupScheduleData(BaseModel):
    enabled: bool = False
    frequency: Literal["daily", "weekly"] = "daily"
    time_of_day: str = Field(pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    weekday: int = Field(default=0, ge=0, le=6)
    timezone: str = Field(default="Europe/Berlin", min_length=1, max_length=64)
    destination: str = Field(default="automatic", min_length=1, max_length=255)
    retention_days: int = Field(default=30, ge=1, le=3650)
    retention_count: int = Field(default=14, ge=1, le=1000)


class BackupScheduleRead(BackupScheduleData):
    model_config = ConfigDict(from_attributes=True)
    id: int


class BackupRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    status: str
    trigger: str
    path: str | None
    size_bytes: int | None
    started_at: datetime
    finished_at: datetime | None
    error_message: str | None


class BackupRestoreRequest(BaseModel):
    confirmation: str
