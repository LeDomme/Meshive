from typing import Literal

from pydantic import AnyHttpUrl, BaseModel, Field, field_validator, model_validator

CreatorLinkKind = Literal[
    "website",
    "patreon",
    "cults3d",
    "myminifactory",
    "cgtrader",
    "gumroad",
    "etsy",
    "other",
]


class CreatorMetadataLinkRead(BaseModel):
    id: int
    creator_profile_id: int | None = None
    kind: CreatorLinkKind
    label: str
    url: str


class CreatorArtworkRead(BaseModel):
    url: str
    width: int
    height: int


class CreatorPublicRead(BaseModel):
    id: int
    display_name: str
    description: str | None = None
    artwork: CreatorArtworkRead | None = None
    links: list[CreatorMetadataLinkRead]
    primary_link: CreatorMetadataLinkRead | None = None
    model_count: int = Field(ge=0)


class CreatorRead(BaseModel):
    name: str
    model_count: int = Field(ge=0)
    links: list[CreatorMetadataLinkRead]


class CreatorAliasRead(BaseModel):
    id: int
    alias: str
    normalized_alias: str


class CreatorProfileRead(BaseModel):
    id: int
    display_name: str
    normalized_name: str
    description: str | None = None
    artwork_id: int | None = None
    model_count: int = Field(ge=0)
    aliases: list[CreatorAliasRead] = []
    links: list[CreatorMetadataLinkRead] = []


class CreatorProfileWrite(BaseModel):
    display_name: str = Field(min_length=1, max_length=255)
    description: str | None = None

    @field_validator("display_name")
    @classmethod
    def strip_display_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Creator name cannot be blank")
        return value


class CreatorAliasWrite(BaseModel):
    alias: str = Field(min_length=1, max_length=255)

    @field_validator("alias")
    @classmethod
    def strip_alias(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Creator alias cannot be blank")
        return value


class CreatorMergePreviewRequest(BaseModel):
    target_profile_id: int = Field(ge=1)
    source_profile_ids: list[int] = Field(min_length=1)

    @model_validator(mode="after")
    def distinct_profiles(self) -> "CreatorMergePreviewRequest":
        if self.target_profile_id in self.source_profile_ids:
            raise ValueError("Target profile cannot also be a source profile")
        if len(set(self.source_profile_ids)) != len(self.source_profile_ids):
            raise ValueError("Source profiles must be distinct")
        return self


class CreatorMergeLinkResolution(BaseModel):
    source_link_id: int = Field(ge=1)
    action: Literal["keep_target", "keep_source"]


class CreatorMergeApplyRequest(CreatorMergePreviewRequest):
    artwork_resolution: str | None = None
    link_resolutions: list[CreatorMergeLinkResolution] = []


class CreatorMergePreviewRead(BaseModel):
    target: CreatorProfileRead
    sources: list[CreatorProfileRead]
    models_by_source: dict[str, int]
    favorite_count: int
    duplicate_favorite_count: int
    duplicate_link_ids: list[int]
    link_conflicts: list[dict[str, object]]
    artwork_conflict: bool


class CreatorLinkFields(BaseModel):
    kind: CreatorLinkKind
    label: str | None = Field(default=None, max_length=80)
    url: AnyHttpUrl

    @field_validator("label")
    @classmethod
    def strip_label(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @model_validator(mode="after")
    def require_other_label(self) -> "CreatorLinkFields":
        if self.kind == "other" and self.label is None:
            raise ValueError("A label is required for other creator links")
        return self


class CreatorLinkCreate(CreatorLinkFields):
    creator_name: str | None = Field(default=None, min_length=1, max_length=255)
    creator_profile_id: int | None = Field(default=None, ge=1)

    @field_validator("creator_name")
    @classmethod
    def strip_creator_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("Creator name cannot be blank")
        return stripped

    @model_validator(mode="after")
    def require_creator_reference(self) -> "CreatorLinkCreate":
        if self.creator_name is None and self.creator_profile_id is None:
            raise ValueError("creator_name or creator_profile_id is required")
        if self.creator_name is not None and self.creator_profile_id is not None:
            raise ValueError("Only creator_name or creator_profile_id is accepted")
        return self


class CreatorLinkUpdate(CreatorLinkFields):
    pass
