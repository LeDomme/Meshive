from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class ScanStartRequest(BaseModel):
    """Choose how deeply a library source is inspected."""

    mode: Literal["full", "missing_images", "incremental", "reconcile_images"] = "full"

class ScanRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    library_source_id: int
    mode: str
    status: str
    trigger: str
    started_at: datetime | None
    finished_at: datetime | None
    models_found: int
    models_added: int
    models_updated: int
    models_missing: int
    automatic_tag_matches: int
    automatic_tags_added: int
    automatic_tags_removed: int
    issues_count: int
    error_message: str | None
    created_at: datetime


class ScanIssueRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    scan_run_id: int
    model_id: int | None
    relative_path: str
    severity: str
    code: str
    message: str
    created_at: datetime


class ScanQueueItem(BaseModel):
    id: int
    library_source_id: int
    source_name: str
    status: str
    trigger: str
    position: int | None
    created_at: datetime
    started_at: datetime | None


class ScanDetail(ScanRunRead):
    issues: list[ScanIssueRead]
