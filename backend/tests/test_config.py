import pytest
from pydantic import ValidationError

from meshive.config import Settings


@pytest.mark.parametrize(
    "override",
    [
        {"environment": "staging"},
        {"session_lifetime_days": 0},
        {"archive_timeout_seconds": 0},
        {"archive_max_entries": 0},
        {"archive_image_max_candidates": 0},
        {"archive_image_max_entry_bytes": 1024},
        {"archive_image_max_compressed_bytes": 1024},
        {"archive_image_max_total_bytes": 1024},
        {"archive_image_max_pixels": 1000},
        {"archive_image_timeout_seconds": 0},
        {"archive_image_threads": 0},
        {"thumbnail_size": 32},
        {"thumbnail_quality": 101},
        {"thumbnail_max_bytes": 1024},
        {"archive_image_detail_size": 32},
        {"archive_image_detail_max_bytes": 1024},
        {"archive_image_webp_method": 7},
        {"smtp_port": 0},
        {"smtp_security": "tls"},
        {"password_reset_lifetime_minutes": 1},
        {"email_verification_lifetime_hours": 0},
    ],
)
def test_invalid_runtime_limits_are_rejected(override: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **override)


def test_archive_image_limits_have_conservative_defaults() -> None:
    settings = Settings(_env_file=None)

    assert settings.archive_image_max_candidates == 12
    assert settings.archive_image_max_entry_bytes == 64 * 1024 * 1024
    assert settings.archive_image_max_compressed_bytes == 64 * 1024 * 1024
    assert settings.archive_image_max_total_bytes == 256 * 1024 * 1024
    assert settings.archive_image_max_pixels == 100_000_000
    assert settings.archive_image_timeout_seconds == 90
    assert settings.archive_image_threads == 1
    assert settings.thumbnail_max_bytes == 64 * 1024
    assert settings.archive_image_detail_size == 1600
    assert settings.archive_image_detail_max_bytes == 384 * 1024
    assert settings.archive_image_webp_method == 4


def test_complete_smtp_configuration_enables_email_delivery() -> None:
    settings = Settings(
        _env_file=None,
        public_url="https://meshive.example",
        smtp_host="smtp.example",
        smtp_port=465,
        smtp_username="meshive@example.com",
        smtp_password="mailbox-password",
        smtp_from="meshive@example.com",
        smtp_security="ssl",
    )

    assert settings.email_delivery_enabled is True
    assert Settings(_env_file=None, smtp_host="smtp.example").email_delivery_enabled is False
    assert Settings(
        _env_file=None,
        public_url="meshive.example",
        smtp_host="smtp.example",
        smtp_username="meshive@example.com",
        smtp_password="mailbox-password",
        smtp_from="meshive@example.com",
    ).email_delivery_enabled is False
    assert Settings(
        _env_file=None,
        public_url="https://user:password@meshive.example",
        smtp_host="smtp.example",
        smtp_username="meshive@example.com",
        smtp_password="mailbox-password",
        smtp_from="meshive@example.com",
    ).email_delivery_enabled is False


@pytest.mark.parametrize(
    ("public_url", "smtp_security"),
    [
        ("http://meshive.example", "ssl"),
        ("https://meshive.example", "none"),
    ],
)
def test_production_email_delivery_requires_transport_security(
    public_url: str, smtp_security: str
) -> None:
    settings = Settings(
        _env_file=None,
        environment="production",
        public_url=public_url,
        smtp_host="smtp.example",
        smtp_username="meshive@example.com",
        smtp_password="mailbox-password",
        smtp_from="meshive@example.com",
        smtp_security=smtp_security,
    )

    assert settings.email_delivery_enabled is False
