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
        {"thumbnail_size": 32},
        {"thumbnail_quality": 101},
        {"smtp_port": 0},
        {"smtp_security": "tls"},
        {"password_reset_lifetime_minutes": 1},
        {"email_verification_lifetime_hours": 0},
    ],
)
def test_invalid_runtime_limits_are_rejected(override: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **override)


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
