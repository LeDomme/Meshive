import smtplib
import ssl
from email.message import EmailMessage
from urllib.parse import quote

from meshive.config import Settings


class EmailDeliveryError(RuntimeError):
    pass


def send_password_reset_email(
    settings: Settings, recipient: str, raw_token: str
) -> None:
    url = _action_url(settings, "reset-password", raw_token)
    _send(
        settings,
        recipient,
        "Reset your Meshive password",
        "A password reset was requested for your Meshive account.\n\n"
        f"Open this link to choose a new password:\n{url}\n\n"
        f"This link expires in {settings.password_reset_lifetime_minutes} minutes. "
        "If you did not request this, you can ignore this email.",
    )


def send_email_verification(
    settings: Settings, recipient: str, raw_token: str
) -> None:
    url = _action_url(settings, "verify-email", raw_token)
    _send(
        settings,
        recipient,
        "Verify your Meshive recovery email",
        "Confirm this address for password recovery on your Meshive account.\n\n"
        f"Open this link to verify the address:\n{url}\n\n"
        f"This link expires in {settings.email_verification_lifetime_hours} hours. "
        "If you did not request this, you can ignore this email.",
    )


def _action_url(settings: Settings, path: str, raw_token: str) -> str:
    if not settings.public_url:
        raise EmailDeliveryError("MESHIVE_PUBLIC_URL is not configured")
    public_url = settings.public_url.strip().rstrip("/")
    if not public_url.startswith(("https://", "http://")):
        raise EmailDeliveryError("MESHIVE_PUBLIC_URL must use HTTP or HTTPS")
    return f"{public_url}/{path}#token={quote(raw_token, safe='')}"


def _send(settings: Settings, recipient: str, subject: str, body: str) -> None:
    if not settings.email_delivery_enabled:
        raise EmailDeliveryError("Email delivery is not configured")
    assert settings.smtp_host is not None
    assert settings.smtp_username is not None
    assert settings.smtp_password is not None
    assert settings.smtp_from is not None
    for value in (recipient, settings.smtp_from, settings.smtp_host):
        if "\r" in value or "\n" in value:
            raise EmailDeliveryError("Email configuration contains invalid characters")

    message = EmailMessage()
    message["From"] = settings.smtp_from.strip()
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(body)

    try:
        if settings.smtp_security == "ssl":
            with smtplib.SMTP_SSL(
                settings.smtp_host,
                settings.smtp_port,
                timeout=settings.smtp_timeout_seconds,
                context=ssl.create_default_context(),
            ) as client:
                _authenticate_and_send(client, settings, message)
        else:
            with smtplib.SMTP(
                settings.smtp_host,
                settings.smtp_port,
                timeout=settings.smtp_timeout_seconds,
            ) as client:
                if settings.smtp_security == "starttls":
                    client.starttls(context=ssl.create_default_context())
                _authenticate_and_send(client, settings, message)
    except (OSError, smtplib.SMTPException) as error:
        raise EmailDeliveryError("The email could not be delivered") from error


def _authenticate_and_send(
    client: smtplib.SMTP, settings: Settings, message: EmailMessage
) -> None:
    assert settings.smtp_username is not None
    assert settings.smtp_password is not None
    client.login(
        settings.smtp_username.strip(), settings.smtp_password.get_secret_value()
    )
    client.send_message(message)
