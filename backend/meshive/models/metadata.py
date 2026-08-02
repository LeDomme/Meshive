from datetime import datetime

from sqlalchemy import DateTime, LargeBinary, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from meshive.database import Base


class MetadataArtwork(Base):
    __tablename__ = "metadata_artwork"
    __table_args__ = (UniqueConstraint("entity_type", "entity_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(20), index=True)
    entity_value: Mapped[str] = mapped_column(String(512))
    entity_key: Mapped[str] = mapped_column(String(600))
    content: Mapped[bytes] = mapped_column(LargeBinary)
    content_type: Mapped[str] = mapped_column(String(40), default="image/webp")
    width: Mapped[int] = mapped_column()
    height: Mapped[int] = mapped_column()
    etag: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
