"""EmailSender — real SMTP delivery when configured, graceful no-op
(logs the message instead) otherwise.

Same optional-credential pattern as every other integration in this
project (Sentry, LangSmith, Unsplash): a real deployment sets SMTP_HOST/
SMTP_USERNAME/SMTP_PASSWORD and gets a real email; local dev with nothing
configured still works end to end — the message (including any link it
carries, e.g. a password-reset URL) just goes to the log instead, which is
enough to develop/demo the flow without a real mail provider.
"""

from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

from travel_agent.config import settings

logger = logging.getLogger(__name__)

SMTP_TIMEOUT = 10


class EmailSender:
    def send(self, to: str, subject: str, body: str) -> None:
        if not settings.smtp_host:
            logger.warning(
                "SMTP not configured; logging email instead of sending. To=%s Subject=%r\n%s",
                to,
                subject,
                body,
            )
            return

        message = EmailMessage()
        message["From"] = settings.smtp_from_email
        message["To"] = to
        message["Subject"] = subject
        message.set_content(body)

        try:
            with smtplib.SMTP(
                settings.smtp_host, settings.smtp_port, timeout=SMTP_TIMEOUT
            ) as server:
                server.starttls()
                if settings.smtp_username:
                    server.login(settings.smtp_username, settings.smtp_password)
                server.send_message(message)
        except (smtplib.SMTPException, OSError) as exc:
            # A failed send shouldn't break the request that triggered it
            # (e.g. /auth/forgot-password already returns a generic
            # "if that email exists..." response regardless) - log and
            # move on rather than raising.
            logger.warning("Failed to send email to %s: %s", to, exc)
