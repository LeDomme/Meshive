from pydantic import AnyHttpUrl, BaseModel, Field, field_validator


class CreatorLinkRead(BaseModel):
    name: str
    url: str | None
    model_count: int = Field(ge=0)


class CreatorLinkUpdate(BaseModel):
    creator_name: str = Field(min_length=1, max_length=255)
    url: AnyHttpUrl | None = None

    @field_validator("creator_name")
    @classmethod
    def strip_creator_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Creator name cannot be blank")
        return stripped
