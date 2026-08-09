from pydantic import BaseModel, Field

from meshive.schemas.creator import CreatorMetadataLinkRead
from meshive.schemas.tag import TagRead


class ModelSummary(BaseModel):
    id: int
    name: str
    variant: str | None
    creator: str | None
    franchise: str | None
    series: str | None
    collection: str | None
    status: str
    source_id: int
    source_name: str
    archive_format: str | None
    archive_size_bytes: int | None
    archive_count: int
    thumbnail_url: str | None
    tags: list[TagRead]


class ModelPage(BaseModel):
    items: list[ModelSummary]
    total: int
    page: int
    page_size: int


class ModelNavigationItem(BaseModel):
    id: int
    name: str
    variant: str | None


class ModelNavigation(BaseModel):
    previous: ModelNavigationItem | None
    next: ModelNavigationItem | None


class ModelImageRead(BaseModel):
    id: int
    filename: str
    format: str
    size_bytes: int
    is_primary: bool
    url: str


class ArchiveEntryRead(BaseModel):
    path: str
    name: str
    is_directory: bool
    size_bytes: int | None
    compressed_size_bytes: int | None
    modified_at: str | None


class ArchiveRead(BaseModel):
    id: int
    filename: str
    format: str
    size_bytes: int
    status: str
    entry_count: int
    uncompressed_size_bytes: int
    error_message: str | None
    download_url: str
    entries: list[ArchiveEntryRead]


class ModelDetail(BaseModel):
    id: int
    name: str
    variant: str | None
    creator: str | None
    creator_url: str | None
    creator_links: list[CreatorMetadataLinkRead]
    franchise: str | None
    series: str | None
    collection: str | None
    status: str
    source_id: int
    source_name: str
    relative_path: str
    images: list[ModelImageRead]
    archives: list[ArchiveRead]
    archive_bundle_download_url: str | None
    tags: list[TagRead]


class FilterOption(BaseModel):
    value: str
    count: int = Field(ge=0)


class SourceFilterOption(BaseModel):
    id: int
    name: str
    count: int = Field(ge=0)


class CatalogueFilters(BaseModel):
    models: list[FilterOption]
    creators: list[FilterOption]
    franchises: list[FilterOption]
    series: list[FilterOption]
    collections: list[FilterOption]
    sources: list[SourceFilterOption]
    statuses: list[FilterOption]
    tags: list[TagRead]
