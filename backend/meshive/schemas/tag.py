from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class TagCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    color: str | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")
    description: str | None = Field(default=None, max_length=1000)


class TagUpdate(TagCreate):
    pass


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


class TagAssignmentRuleTargetWrite(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    target_type: Literal[
        "model_relative_path",
        "archive_filename",
        "archive_entry_path",
        "archive_entry_name",
    ]
    folder_segment: bool = False

    @model_validator(mode="after")
    def validate_folder_segment(self) -> "TagAssignmentRuleTargetWrite":
        if self.folder_segment and self.target_type != "model_relative_path":
            raise ValueError("folder_segment requires model_relative_path")
        return self


class TagAssignmentRuleWrite(BaseModel):
    library_source_id: int | None = Field(default=None, ge=1)
    match_mode: Literal["contains", "regex", "path_relation"]
    pattern: str | None = Field(default=None, min_length=1, max_length=255)
    path_value: str | None = Field(default=None, min_length=1)
    path_relation: Literal["direct_child", "self_or_descendant"] | None = None
    enabled: bool = True
    targets: list[TagAssignmentRuleTargetWrite] = Field(min_length=1, max_length=4)

    @model_validator(mode="after")
    def validate_match_mode(self) -> "TagAssignmentRuleWrite":
        if self.match_mode == "path_relation":
            if self.path_value is None or self.path_relation is None:
                raise ValueError("path_relation requires path_value and path_relation")
            if self.pattern is not None:
                raise ValueError("path_relation does not accept pattern")
            if any(target.target_type != "model_relative_path" for target in self.targets):
                raise ValueError("path_relation supports model_relative_path only")
        elif self.pattern is None:
            raise ValueError("contains and regex rules require pattern")
        return self


class TagAssignmentRuleRead(TagAssignmentRuleWrite):
    id: int
    tag_id: int
    tag_name: str
    match_count: int = Field(ge=0)
    created_at: datetime
    updated_at: datetime


class TagAssignmentRulePreview(TagAssignmentRuleWrite):
    limit: int = Field(default=25, ge=1, le=50)


class TagAssignmentRulePreviewRead(BaseModel):
    model_name: str
    relative_path: str


class TagAssignmentRuleEvaluationRead(BaseModel):
    models_evaluated: int = Field(ge=0)
    matches: int = Field(ge=0)
    assignments_added: int = Field(ge=0)
    assignments_removed: int = Field(ge=0)
