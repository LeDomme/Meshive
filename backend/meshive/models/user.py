from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from meshive.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(120))
    normalized_username: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    normalized_email: Mapped[str | None] = mapped_column(
        String(320), unique=True, index=True, nullable=True
    )
    email_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    password_hash: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(20), default="user", index=True)
    role_id: Mapped[int | None] = mapped_column(
        ForeignKey("roles.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    all_sources: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False)
    catalogue_filter_order: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    sessions: Mapped[list["UserSession"]] = relationship(  # noqa: F821
        back_populates="user", cascade="all, delete-orphan"
    )
    action_tokens: Mapped[list["UserActionToken"]] = relationship(  # noqa: F821
        back_populates="user", cascade="all, delete-orphan"
    )
    favorite_lists: Mapped[list["FavoriteList"]] = relationship(  # noqa: F821
        back_populates="user", cascade="all, delete-orphan"
    )
    role_definition: Mapped["Role | None"] = relationship(back_populates="users")  # noqa: F821
    library_source_grants: Mapped[list["UserLibrarySource"]] = relationship(  # noqa: F821
        back_populates="user", cascade="all, delete-orphan"
    )

    @property
    def email_verified(self) -> bool:
        return self.email is not None and self.email_verified_at is not None
