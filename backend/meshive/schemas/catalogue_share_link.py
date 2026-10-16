from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class CatalogueShareLinkCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    expires_in_seconds: int = Field(default=900, ge=60, le=3600)
    current_password: str = Field(min_length=1, max_length=1024)

    @field_validator("name")
    @classmethod
    def non_blank_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Link name must not be blank")
        return value


class CatalogueShareLinkRead(BaseModel):
    id: int
    name: str
    token_prefix: str
    created_at: datetime
    expires_at: datetime
    last_used_at: datetime | None
    status: str


class CatalogueShareLinkCreated(CatalogueShareLinkRead):
    token: str
