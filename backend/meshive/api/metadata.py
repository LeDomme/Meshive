import unicodedata
from hashlib import sha256
from io import BytesIO

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Response,
    UploadFile,
    status,
)
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from meshive.auth.access import get_access_context, visible_model_scope
from meshive.auth.dependencies import get_current_user, require_admin
from meshive.database import get_session
from meshive.models.catalog import LibraryModel
from meshive.models.metadata import MetadataArtwork
from meshive.models.user import User
from meshive.schemas.metadata import (
    MetadataArtworkRead,
    MetadataEntityRead,
    MetadataEntityType,
)

router = APIRouter(prefix="/metadata", tags=["metadata"])
admin_router = APIRouter(
    prefix="/admin/metadata",
    tags=["metadata administration"],
    dependencies=[Depends(require_admin)],
)

_MAX_UPLOAD_BYTES = 12 * 1024 * 1024
_MAX_IMAGE_PIXELS = 40_000_000
_MAX_OUTPUT_EDGE = 1600
_ENTITY_COLUMNS = {
    "creator": LibraryModel.creator,
    "franchise": LibraryModel.franchise,
    "collection": LibraryModel.collection,
}


@admin_router.get("", response_model=list[MetadataEntityRead])
def list_metadata_entities(
    session: Session = Depends(get_session),
) -> list[MetadataEntityRead]:
    artwork = {
        (entity_type, entity_key): (artwork_id, etag, entity_value)
        for artwork_id, entity_type, entity_key, etag, entity_value in session.execute(
            select(
                MetadataArtwork.id,
                MetadataArtwork.entity_type,
                MetadataArtwork.entity_key,
                MetadataArtwork.etag,
                MetadataArtwork.entity_value,
            )
        )
    }
    result: list[MetadataEntityRead] = []
    active_keys: set[tuple[str, str]] = set()
    for entity_type, column in _ENTITY_COLUMNS.items():
        rows = session.execute(
            select(column, func.count(LibraryModel.id))
            .where(column.is_not(None), func.trim(column) != "")
            .group_by(column.collate("NOCASE"))
            .order_by(column.collate("NOCASE"))
        )
        for value, model_count in rows:
            entity_key = _normalize(value)
            active_keys.add((entity_type, entity_key))
            stored = artwork.get((entity_type, entity_key))
            result.append(
                MetadataEntityRead(
                    entity_type=entity_type,
                    value=value,
                    model_count=model_count,
                    artwork_url=(
                        _artwork_url(stored[0], stored[1]) if stored else None
                    ),
                )
            )
    for (entity_type, entity_key), stored in artwork.items():
        if (entity_type, entity_key) in active_keys:
            continue
        result.append(
            MetadataEntityRead(
                entity_type=entity_type,
                value=stored[2],
                model_count=0,
                artwork_url=_artwork_url(stored[0], stored[1]),
            )
        )
    type_order = {"creator": 0, "franchise": 1, "collection": 2}
    return sorted(
        result,
        key=lambda item: (type_order[item.entity_type], item.value.casefold()),
    )


@admin_router.put("/artwork", response_model=MetadataArtworkRead)
async def upload_metadata_artwork(
    entity_type: MetadataEntityType = Form(),
    value: str = Form(min_length=1, max_length=512),
    image: UploadFile = File(),
    session: Session = Depends(get_session),
) -> MetadataArtworkRead:
    canonical_value = _canonical_value(session, entity_type, value)
    if canonical_value is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Catalogue value not found",
        )
    raw = await image.read(_MAX_UPLOAD_BYTES + 1)
    if len(raw) > _MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="The image may not exceed 12 MB",
        )
    content, width, height = _prepare_artwork(raw)
    entity_key = _normalize(canonical_value)
    artwork = session.scalar(
        select(MetadataArtwork).where(
            MetadataArtwork.entity_type == entity_type,
            MetadataArtwork.entity_key == entity_key,
        )
    )
    if artwork is None:
        artwork = MetadataArtwork(
            entity_type=entity_type,
            entity_value=canonical_value,
            entity_key=entity_key,
            content=content,
            content_type="image/webp",
            width=width,
            height=height,
            etag=sha256(content).hexdigest(),
        )
        session.add(artwork)
    else:
        artwork.entity_value = canonical_value
        artwork.content = content
        artwork.content_type = "image/webp"
        artwork.width = width
        artwork.height = height
        artwork.etag = sha256(content).hexdigest()
    session.commit()
    session.refresh(artwork)
    return _artwork_read(artwork)


@admin_router.delete("/artwork", status_code=status.HTTP_204_NO_CONTENT)
def delete_metadata_artwork(
    entity_type: MetadataEntityType,
    value: str,
    session: Session = Depends(get_session),
) -> Response:
    artwork = session.scalar(
        select(MetadataArtwork).where(
            MetadataArtwork.entity_type == entity_type,
            MetadataArtwork.entity_key == _normalize(value),
        )
    )
    if artwork is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Custom artwork not found",
        )
    session.delete(artwork)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/artwork/{artwork_id}")
def metadata_artwork(
    artwork_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> Response:
    artwork = session.get(MetadataArtwork, artwork_id)
    if artwork is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Custom artwork not found",
        )
    access = get_access_context(session, current_user)
    column = _ENTITY_COLUMNS[artwork.entity_type]
    scope = visible_model_scope(access)
    statement = select(column).where(column.is_not(None), column != "")
    if scope is not None:
        statement = statement.where(scope)
    if not any(_normalize(value) == artwork.entity_key for value in session.scalars(statement)):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Custom artwork not found",
        )
    return Response(
        content=artwork.content,
        media_type=artwork.content_type,
        headers={
            "Cache-Control": "private, max-age=86400",
            "ETag": f'"{artwork.etag}"',
        },
    )


def _canonical_value(
    session: Session, entity_type: MetadataEntityType, requested: str
) -> str | None:
    column = _ENTITY_COLUMNS[entity_type]
    requested_key = _normalize(requested)
    return next(
        (
            value
            for value in session.scalars(
                select(column).where(column.is_not(None), column != "").distinct()
            )
            if _normalize(value) == requested_key
        ),
        None,
    )


def _prepare_artwork(raw: bytes) -> tuple[bytes, int, int]:
    if not raw:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="The uploaded image is empty",
        )
    try:
        with Image.open(BytesIO(raw)) as source:
            if source.width * source.height > _MAX_IMAGE_PIXELS:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail="The image dimensions are too large",
                )
            prepared = ImageOps.exif_transpose(source)
            prepared.load()
            prepared.thumbnail(
                (_MAX_OUTPUT_EDGE, _MAX_OUTPUT_EDGE), Image.Resampling.LANCZOS
            )
            prepared = prepared.convert(
                "RGBA" if "A" in prepared.getbands() else "RGB"
            )
            output = BytesIO()
            prepared.save(output, format="WEBP", quality=86, method=6)
            return output.getvalue(), prepared.width, prepared.height
    except (UnidentifiedImageError, OSError) as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="The uploaded file is not a supported image",
        ) from error


def _artwork_read(artwork: MetadataArtwork) -> MetadataArtworkRead:
    return MetadataArtworkRead(
        id=artwork.id,
        entity_type=artwork.entity_type,
        value=artwork.entity_value,
        artwork_url=_artwork_url(artwork.id, artwork.etag),
        width=artwork.width,
        height=artwork.height,
    )


def _artwork_url(artwork_id: int, etag: str) -> str:
    return f"/api/metadata/artwork/{artwork_id}?v={etag[:12]}"


def _normalize(value: str) -> str:
    return unicodedata.normalize("NFKC", value.strip()).casefold()
