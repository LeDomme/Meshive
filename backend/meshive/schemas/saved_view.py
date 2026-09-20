from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

CatalogueSort = Literal[
    "meshive_newest",
    "meshive_oldest",
    "files_newest",
    "files_oldest",
    "name_asc",
    "name_desc",
    "creator_asc",
    "creator_desc",
]


class SavedViewState(BaseModel):
    search: str = Field(default="", max_length=200)
    model: str = Field(default="", max_length=255)
    creator: str = Field(default="", max_length=255)
    creator_profile_id: str = Field(default="")
    franchise: str = Field(default="", max_length=255)
    series: str = Field(default="", max_length=255)
    collection: str = Field(default="", max_length=255)
    variant: str = Field(default="", max_length=255)
    source_id: str = Field(default="")
    tag_id: str = Field(default="")
    status: str = Field(default="", max_length=30)
    sort: CatalogueSort = "name_asc"

    @field_validator("creator_profile_id", "source_id", "tag_id")
    @classmethod
    def validate_optional_positive_id(cls, value: str) -> str:
        if not value:
            return ""
        if not value.isdigit() or int(value) < 1:
            raise ValueError("Must be a positive identifier")
        return value


class SavedViewWrite(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    state: SavedViewState

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Saved view name cannot be empty")
        return stripped


class SavedViewRename(BaseModel):
    name: str = Field(min_length=1, max_length=120)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Saved view name cannot be empty")
        return stripped


class SavedViewRead(BaseModel):
    id: int
    name: str
    state: SavedViewState
    created_at: datetime
    updated_at: datetime
