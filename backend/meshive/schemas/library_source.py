from datetime import datetime
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator

from meshive.services.library_paths import (
    normalize_library_root,
    validate_directory_pattern,
    validate_model_pattern,
)

SUPPORTED_ARCHIVE_FORMATS = frozenset({"7z", "zip", "rar"})
SUPPORTED_IMAGE_FORMATS = frozenset({"jpg", "jpeg", "png", "webp"})


class LibrarySourceFields(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    root_path: str
    directory_pattern: str
    model_pattern: str | None = None
    archive_formats: list[str] = Field(default_factory=lambda: ["7z", "zip", "rar"])
    image_formats: list[str] = Field(
        default_factory=lambda: ["jpg", "jpeg", "png", "webp"]
    )
    is_active: bool = True
    scan_enabled: bool = True
    auto_scan_enabled: bool = False
    auto_scan_frequency: Literal["hourly", "daily", "weekly"] = "daily"
    auto_scan_time: str = Field(
        default="02:00", pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$"
    )
    auto_scan_weekday: int = Field(default=0, ge=0, le=6)
    auto_scan_timezone: str = Field(
        default="Europe/Berlin", min_length=1, max_length=64
    )

    @field_validator("name")
    @classmethod
    def strip_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @field_validator("root_path")
    @classmethod
    def normalize_root(cls, value: str) -> str:
        return normalize_library_root(value)

    @field_validator("directory_pattern")
    @classmethod
    def check_directory_pattern(cls, value: str) -> str:
        return validate_directory_pattern(value)

    @field_validator("model_pattern")
    @classmethod
    def check_model_pattern(cls, value: str | None) -> str | None:
        return validate_model_pattern(value)

    @field_validator("archive_formats")
    @classmethod
    def check_archive_formats(cls, values: list[str]) -> list[str]:
        return _normalize_formats(values, SUPPORTED_ARCHIVE_FORMATS, "archive")

    @field_validator("image_formats")
    @classmethod
    def check_image_formats(cls, values: list[str]) -> list[str]:
        return _normalize_formats(values, SUPPORTED_IMAGE_FORMATS, "image")

    @field_validator("auto_scan_timezone")
    @classmethod
    def check_auto_scan_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as error:
            raise ValueError("Unknown automatic scan timezone") from error
        return value


class LibrarySourceCreate(LibrarySourceFields):
    pass


class LibrarySourceUpdate(LibrarySourceFields):
    pass


class LibrarySourceRead(LibrarySourceFields):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime


class PathPreviewRequest(BaseModel):
    directory_pattern: str
    model_pattern: str | None = None
    relative_path: str


class PathPreviewResponse(BaseModel):
    normalized_path: str
    values: dict[str, str]
    warnings: list[str] = Field(default_factory=list)


def _normalize_formats(
    values: list[str], supported: frozenset[str], label: str
) -> list[str]:
    normalized = list(dict.fromkeys(item.lower().lstrip(".").strip() for item in values))
    unsupported = sorted(set(normalized) - supported)
    if unsupported:
        raise ValueError(f"Unsupported {label} formats: {', '.join(unsupported)}")
    if not normalized:
        raise ValueError(f"At least one {label} format is required")
    return normalized
