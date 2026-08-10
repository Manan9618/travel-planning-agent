import smtplib
from unittest.mock import MagicMock, patch

from travel_agent.config import settings
from travel_agent.tools.email_sender import EmailSender


def _configure_smtp(monkeypatch, **overrides):
    defaults = dict(
        smtp_host="smtp.example.com",
        smtp_port=587,
        smtp_username="bot@example.com",
        smtp_password="hunter2222",  # noqa: S105 - test fixture, not a real credential
        smtp_from_email="waypoint@example.com",
    )
    defaults.update(overrides)
    for key, value in defaults.items():
        monkeypatch.setattr(settings, key, value)


def test_logs_instead_of_sending_when_smtp_is_not_configured(monkeypatch, caplog):
    monkeypatch.setattr(settings, "smtp_host", "")
    with patch("smtplib.SMTP") as mock_smtp:
        EmailSender().send("traveler@example.com", "Subject", "Body text")
    mock_smtp.assert_not_called()
    assert "traveler@example.com" in caplog.text
    assert "Body text" in caplog.text


def test_sends_via_smtp_when_configured(monkeypatch):
    _configure_smtp(monkeypatch)
    mock_server = MagicMock()
    with patch("smtplib.SMTP") as mock_smtp:
        mock_smtp.return_value.__enter__.return_value = mock_server
        EmailSender().send("traveler@example.com", "Reset your password", "Click here: ...")

    mock_smtp.assert_called_once_with("smtp.example.com", 587, timeout=10)
    mock_server.starttls.assert_called_once()
    mock_server.login.assert_called_once_with("bot@example.com", "hunter2222")
    mock_server.send_message.assert_called_once()
    sent_message = mock_server.send_message.call_args[0][0]
    assert sent_message["To"] == "traveler@example.com"
    assert sent_message["From"] == "waypoint@example.com"
    assert sent_message["Subject"] == "Reset your password"
    assert "Click here" in sent_message.get_content()


def test_skips_login_when_no_username_configured(monkeypatch):
    _configure_smtp(monkeypatch, smtp_username="")
    mock_server = MagicMock()
    with patch("smtplib.SMTP") as mock_smtp:
        mock_smtp.return_value.__enter__.return_value = mock_server
        EmailSender().send("traveler@example.com", "Subject", "Body")
    mock_server.login.assert_not_called()


def test_send_failure_is_caught_not_raised(monkeypatch):
    _configure_smtp(monkeypatch)
    with patch("smtplib.SMTP") as mock_smtp:
        mock_smtp.side_effect = smtplib.SMTPConnectError(421, "connection refused")
        EmailSender().send("traveler@example.com", "Subject", "Body")  # must not raise
