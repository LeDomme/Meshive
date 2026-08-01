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
