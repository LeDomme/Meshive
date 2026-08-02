from typing import Literal

from pydantic import BaseModel, Field

MetadataEntityType = Literal["creator", "franchise", "collection"]


class MetadataEntityRead(BaseModel):
    entity_type: MetadataEntityType
    value: str
    model_count: int = Field(ge=0)
    artwork_url: str | None = None


class MetadataArtworkRead(BaseModel):
    id: int
    entity_type: MetadataEntityType
    value: str
    artwork_url: str
    width: int = Field(gt=0)
    height: int = Field(gt=0)
