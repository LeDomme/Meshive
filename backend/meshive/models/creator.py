from datetime import datetime

from sqlalchemy import DateTime, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from meshive.database import Base


class CreatorLink(Base):
    __tablename__ = "creator_metadata_links"
    __table_args__ = (
        UniqueConstraint("creator_name", "kind", "label"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    creator_name: Mapped[str] = mapped_column(
        String(255, collation="NOCASE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(40))
    label: Mapped[str] = mapped_column(String(80, collation="NOCASE"))
    url: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
