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
    creator_name: str = Field(min_length=1, max_length=255)

    @field_validator("creator_name")
    @classmethod
    def strip_creator_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Creator name cannot be blank")
        return stripped


class CreatorLinkUpdate(CreatorLinkFields):
    pass
