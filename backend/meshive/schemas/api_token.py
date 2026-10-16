from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class ApiTokenCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    expires_in_seconds: int | None = Field(default=3600, ge=60, le=365 * 24 * 60 * 60)
    current_password: str = Field(min_length=1, max_length=1024)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Token name cannot be blank")
        return stripped


class ApiTokenRead(BaseModel):
    id: int
    name: str
    token_prefix: str
    created_at: datetime
    expires_at: datetime | None
    last_used_at: datetime | None
    status: Literal["active", "expired"]


class ApiTokenCreated(ApiTokenRead):
    token: str
