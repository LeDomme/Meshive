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


class CreatorRead(BaseModel):
    name: str
    model_count: int = Field(ge=0)
    links: list[CreatorMetadataLinkRead]


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
