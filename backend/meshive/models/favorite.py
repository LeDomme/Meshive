from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from meshive.database import Base


class FavoriteList(Base):
    __tablename__ = "favorite_lists"
    __table_args__ = (UniqueConstraint("user_id", "normalized_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(120))
    normalized_name: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="favorite_lists")  # noqa: F821
    items: Mapped[list["FavoriteListItem"]] = relationship(
        back_populates="favorite_list", cascade="all, delete-orphan"
    )


class FavoriteListItem(Base):
    __tablename__ = "favorite_list_items"
    __table_args__ = (
        UniqueConstraint("favorite_list_id", "entity_type", "entity_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    favorite_list_id: Mapped[int] = mapped_column(
        ForeignKey("favorite_lists.id", ondelete="CASCADE"), index=True
    )
    entity_type: Mapped[str] = mapped_column(String(20))
    entity_key: Mapped[str] = mapped_column(String(600))
    label: Mapped[str] = mapped_column(String(512))
    model_id: Mapped[int | None] = mapped_column(
        ForeignKey("library_models.id", ondelete="SET NULL"), nullable=True, index=True
    )
    tag_id: Mapped[int | None] = mapped_column(
        ForeignKey("tags.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    favorite_list: Mapped[FavoriteList] = relationship(back_populates="items")
