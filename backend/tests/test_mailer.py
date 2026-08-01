from meshive.config import Settings
from meshive.services.mailer import send_password_reset_email


def test_implicit_tls_uses_smtp_ssl(monkeypatch) -> None:
    calls: dict[str, object] = {}

    class FakeSmtpSsl:
        def __init__(self, host, port, **kwargs):
            calls["connection"] = (host, port, kwargs)

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def login(self, username, password):
            calls["login"] = (username, password)

        def send_message(self, message):
            calls["message"] = message

    monkeypatch.setattr("meshive.services.mailer.smtplib.SMTP_SSL", FakeSmtpSsl)
    settings = Settings(
        _env_file=None,
        public_url="https://meshive.example/",
        smtp_host="smtp.example",
        smtp_port=465,
        smtp_username="meshive@example.com",
        smtp_password="mailbox-password",
        smtp_from="meshive@example.com",
        smtp_security="ssl",
    )

    send_password_reset_email(settings, "viewer@example.com", "raw-token")

    assert calls["connection"][0:2] == ("smtp.example", 465)
    assert calls["login"] == ("meshive@example.com", "mailbox-password")
    message = calls["message"]
    assert message["To"] == "viewer@example.com"
    assert "https://meshive.example/reset-password#token=raw-token" in str(message)
