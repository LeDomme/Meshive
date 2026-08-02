from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class TagCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    color: str | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")
    description: str | None = None


class TagRead(TagCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int


class FolderRuleCreate(BaseModel):
    library_source_id: int
    relative_path: str
    tag_id: int
    recursive: bool = True


class FolderRuleRead(FolderRuleCreate):
    id: int
    tag_name: str


class AutomaticTagRuleCreate(BaseModel):
    tag_id: int = Field(ge=1)
    pattern: str = Field(min_length=1, max_length=255)
    enabled: bool = True


class AutomaticTagRuleRead(AutomaticTagRuleCreate):
    id: int
    tag_name: str
    match_count: int = Field(ge=0)
    created_at: datetime
    updated_at: datetime


class AutomaticTagEvaluationRead(BaseModel):
    models_evaluated: int = Field(ge=0)
    matches: int = Field(ge=0)
    assignments_added: int = Field(ge=0)
    assignments_removed: int = Field(ge=0)
