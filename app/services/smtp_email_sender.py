"""
Gmail (or any SMTP) adapter for EmailSender.

Why this file exists:
  - Implements the EmailSender port with real SMTP delivery (no mocks).
  - Auth/OTP code stays unaware of smtplib details.
  - Later we can add ResendEmailSender beside this file without touching AuthService.

Development: use Gmail SMTP + a Google Account App Password
  host=smtp.gmail.com, port=587, STARTTLS.

Security note:
  Pass credentials in via constructor (from Settings/.env), never hardcode them here.
"""

from __future__ import annotations

import logging
import smtplib
import ssl
from email.message import EmailMessage as SmtpEmailMessage

from app.services.email_sender import EmailMessage, EmailSendError, EmailSender

logger = logging.getLogger(__name__)


class SmtpEmailSender(EmailSender):
    """
    Synchronous SMTP email sender.

    Constructor injection keeps this class testable:
      - Unit tests can pass fake host/credentials
      - Production wires real values from Settings in a later factory/dependency
    """

    def __init__(
        self,
        *,
        host: str,
        port: int,
        username: str,
        password: str,
        from_email: str,
        use_tls: bool = True,
        timeout_seconds: float = 30.0,
    ) -> None:
        # SMTP server hostname, e.g. "smtp.gmail.com"
        self._host = host
        # Submission port: 587 with STARTTLS is the usual Gmail choice
        self._port = port
        # SMTP AUTH username (for Gmail: your full Gmail address)
        self._username = username
        # SMTP AUTH password (for Gmail: App Password, NOT your normal login password)
        self._password = password
        # Envelope / From header address users will see
        self._from_email = from_email
        # True → SMTP_SSL or STARTTLS path; we use STARTTLS on 587 when True
        self._use_tls = use_tls
        # Prevent hung workers if the mail server never responds
        self._timeout_seconds = timeout_seconds

    def send(self, message: EmailMessage) -> None:
        """
        Build a MIME text message and deliver it over SMTP.

        Raises EmailSendError on any SMTP/OS failure so callers can map to HTTP 503.
        """
        # email.message.EmailMessage is the stdlib MIME builder (name clash with our DTO)
        mime = SmtpEmailMessage()
        mime["Subject"] = message.subject
        mime["From"] = self._from_email
        mime["To"] = message.to_email
        mime.set_content(message.body_text)

        try:
            if self._use_tls:
                # Port 587 + STARTTLS: connect plain, then upgrade to TLS
                with smtplib.SMTP(
                    self._host,
                    self._port,
                    timeout=self._timeout_seconds,
                ) as server:
                    server.ehlo()
                    server.starttls(context=ssl.create_default_context())
                    server.ehlo()
                    server.login(self._username, self._password)
                    server.send_message(mime)
            else:
                # Non-TLS path (local mailhog/dev relays only — not for Gmail production)
                with smtplib.SMTP(
                    self._host,
                    self._port,
                    timeout=self._timeout_seconds,
                ) as server:
                    server.login(self._username, self._password)
                    server.send_message(mime)
        except smtplib.SMTPException as exc:
            # Includes auth failures, recipient rejected, etc.
            logger.exception(
                "SMTP send failed to_domain=%s",
                _email_domain(message.to_email),
            )
            raise EmailSendError("Failed to send email") from exc
        except OSError as exc:
            # Network down, DNS failure, timeout
            logger.exception(
                "SMTP connection failed host=%s port=%s",
                self._host,
                self._port,
            )
            raise EmailSendError("Failed to send email") from exc

        # Log success without subject/body (body may contain OTP)
        logger.info(
            "Email sent to_domain=%s from=%s",
            _email_domain(message.to_email),
            self._from_email,
        )


def _email_domain(email: str) -> str:
    """
    Return only the domain part for safe logs (privacy).

    Example: "ali@gmail.com" → "gmail.com"
    """
    if "@" not in email:
        return "unknown"
    return email.rsplit("@", 1)[-1].lower()
