from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

FavoriteEntityType = Literal[
    "model", "creator", "franchise", "series", "collection", "tag"
]


class FavoriteListWrite(BaseModel):
    name: str = Field(min_length=1, max_length=120)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Favorite list name cannot be empty")
        return stripped


class FavoriteListSummary(BaseModel):
    id: int
    name: str
    item_count: int = Field(ge=0)
    created_at: datetime
    updated_at: datetime


class FavoriteListItemCreate(BaseModel):
    entity_type: FavoriteEntityType
    model_id: int | None = Field(default=None, ge=1)
    tag_id: int | None = Field(default=None, ge=1)
    value: str | None = Field(default=None, min_length=1, max_length=512)

    @field_validator("value")
    @classmethod
    def strip_value(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None

    @model_validator(mode="after")
    def validate_reference(self):
        if self.entity_type == "model":
            if self.model_id is None:
                raise ValueError("model_id is required for model favorites")
            if self.tag_id is not None or self.value is not None:
                raise ValueError("Only model_id is accepted for model favorites")
        elif self.entity_type == "tag":
            if self.tag_id is None:
                raise ValueError("tag_id is required for tag favorites")
            if self.model_id is not None or self.value is not None:
                raise ValueError("Only tag_id is accepted for tag favorites")
        else:
            if not self.value:
                raise ValueError("value is required for catalogue metadata favorites")
            if self.model_id is not None or self.tag_id is not None:
                raise ValueError("Only value is accepted for catalogue metadata favorites")
        return self


class FavoriteListItemRead(BaseModel):
    id: int
    entity_type: FavoriteEntityType
    label: str
    url: str | None
    is_available: bool
    created_at: datetime


class FavoriteListDetail(FavoriteListSummary):
    items: list[FavoriteListItemRead]
