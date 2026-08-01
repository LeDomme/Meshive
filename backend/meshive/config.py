from functools import lru_cache
from pathlib import Path
from typing import Literal

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
    setup_token: SecretStr | None = None
    archive_command: str = "7z"
    archive_timeout_seconds: int = Field(default=120, ge=1, le=3600)
    archive_max_entries: int = Field(default=100_000, ge=1, le=1_000_000)
    archive_max_output_bytes: int = Field(
        default=64 * 1024 * 1024, ge=1024 * 1024, le=1024 * 1024 * 1024
    )
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


@lru_cache
def get_settings() -> Settings:
    return Settings()
