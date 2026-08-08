from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Meshive"
    environment: Literal["development", "production"] = "development"
    data_dir: Path = Path("./data")
    cache_dir: Path = Path("./cache")
    backup_dir: Path = Path("./backups")
    frontend_dist: Path = Path("../frontend/dist")
    allowed_library_root: Path = Path("/models")
    database_url: str | None = None
    session_cookie_name: str = "meshive_session"
    session_lifetime_days: int = Field(default=7, ge=1, le=365)
    auth_rate_limit_attempts: int = Field(default=5, ge=1, le=100)
    auth_rate_limit_window_seconds: int = Field(default=60, ge=1, le=3600)
    public_url: str | None = None
    smtp_host: str | None = None
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_username: str | None = None
    smtp_password: SecretStr | None = None
    smtp_from: str | None = None
    smtp_security: Literal["ssl", "starttls", "none"] = "starttls"
    smtp_timeout_seconds: int = Field(default=15, ge=1, le=120)
    password_reset_lifetime_minutes: int = Field(default=30, ge=5, le=1440)
    email_verification_lifetime_hours: int = Field(default=24, ge=1, le=168)
    setup_token: SecretStr | None = None
    archive_command: str = "7z"
    archive_timeout_seconds: int = Field(default=120, ge=1, le=3600)
    archive_max_entries: int = Field(default=100_000, ge=1, le=1_000_000)
    archive_max_output_bytes: int = Field(
        default=64 * 1024 * 1024, ge=1024 * 1024, le=1024 * 1024 * 1024
    )
    archive_image_max_candidates: int = Field(default=12, ge=1, le=100)
    archive_image_max_entry_bytes: int = Field(
        default=32 * 1024 * 1024,
        ge=1024 * 1024,
        le=1024 * 1024 * 1024,
    )
    archive_image_max_compressed_bytes: int = Field(
        default=32 * 1024 * 1024,
        ge=1024 * 1024,
        le=1024 * 1024 * 1024,
    )
    archive_image_max_total_bytes: int = Field(
        default=128 * 1024 * 1024,
        ge=1024 * 1024,
        le=4 * 1024 * 1024 * 1024,
    )
    archive_image_max_pixels: int = Field(
        default=40_000_000,
        ge=1_000_000,
        le=250_000_000,
    )
    archive_image_timeout_seconds: int = Field(default=30, ge=1, le=600)
    archive_image_threads: int = Field(default=1, ge=1, le=8)
    backup_max_restore_bytes: int = Field(
        default=5 * 1024 * 1024 * 1024,
        ge=16 * 1024 * 1024,
        le=1024 * 1024 * 1024 * 1024,
    )
    backup_restore_min_free_bytes: int = Field(
        default=64 * 1024 * 1024,
        ge=0,
        le=100 * 1024 * 1024 * 1024,
    )
    max_concurrent_scans: int = Field(default=1, ge=1, le=16)
    max_concurrent_downloads: int = Field(default=4, ge=1, le=64)
    thumbnail_size: int = Field(default=480, ge=64, le=2048)
    thumbnail_quality: int = Field(default=82, ge=1, le=100)
    thumbnail_max_bytes: int = Field(
        default=100 * 1024,
        ge=16 * 1024,
        le=10 * 1024 * 1024,
    )
    archive_image_detail_size: int = Field(default=1600, ge=256, le=4096)
    archive_image_detail_max_bytes: int = Field(
        default=768 * 1024,
        ge=64 * 1024,
        le=10 * 1024 * 1024,
    )
    archive_image_webp_method: int = Field(default=4, ge=0, le=6)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="MESHIVE_",
        extra="ignore",
    )

    @property
    def effective_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        database_path = (self.data_dir / "meshive.db").resolve()
        return f"sqlite:///{database_path.as_posix()}"

    @property
    def secure_cookies(self) -> bool:
        return self.environment == "production"

    @property
    def effective_setup_token(self) -> str | None:
        if self.setup_token is None:
            return None
        value = self.setup_token.get_secret_value().strip()
        return value or None

    @property
    def email_delivery_enabled(self) -> bool:
        values = (
            self.public_url,
            self.smtp_host,
            self.smtp_username,
            self.smtp_from,
        )
        if not all(value and value.strip() for value in values):
            return False
        assert self.public_url is not None
        public_url = self.public_url.strip()
        try:
            parsed_public_url = urlsplit(public_url)
            public_hostname = parsed_public_url.hostname
        except ValueError:
            return False
        if (
            parsed_public_url.scheme not in {"https", "http"}
            or not public_hostname
            or parsed_public_url.username is not None
            or parsed_public_url.password is not None
            or parsed_public_url.query
            or parsed_public_url.fragment
        ):
            return False
        if self.environment == "production":
            if parsed_public_url.scheme != "https" or self.smtp_security == "none":
                return False
        if any("\r" in value or "\n" in value for value in values if value):
            return False
        if self.smtp_password is None:
            return False
        return bool(self.smtp_password.get_secret_value())


@lru_cache
def get_settings() -> Settings:
    return Settings()
