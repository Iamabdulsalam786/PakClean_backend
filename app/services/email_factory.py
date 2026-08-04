"""
Wire Settings → concrete EmailSender (factory).

Why this file exists:
  - Auth/OTP services should ask for EmailSender, not SmtpEmailSender.
  - This is the single place that knows "we use Gmail SMTP in development".
  - Switching to Resend later = change this factory (or settings flag), not AuthService.
"""

from __future__ import annotations

from functools import lru_cache

from app.core.config import Settings, get_settings
from app.services.email_sender import EmailSender, EmailSendError
from app.services.smtp_email_sender import SmtpEmailSender


def build_email_sender(settings: Settings | None = None) -> EmailSender:
    """
    Construct the active EmailSender from configuration.

    Validates that SMTP credentials are present before returning a sender.
    Call this at send-time (or via Depends) so the API can still boot if
    mail is not configured yet.
    """
    cfg = settings or get_settings()

    username = cfg.smtp_username.strip()
    password = cfg.smtp_password.strip()
    from_email = (cfg.email_from or username).strip()

    if not username or not password or not from_email:
        raise EmailSendError(
            "Email is not configured. Set SMTP_USERNAME, SMTP_PASSWORD, and EMAIL_FROM."
        )

    return SmtpEmailSender(
        host=cfg.smtp_host,
        port=cfg.smtp_port,
        username=username,
        password=password,
        from_email=from_email,
        use_tls=cfg.smtp_use_tls,
    )


@lru_cache
def get_email_sender() -> EmailSender:
    """
    Cached process-wide sender for FastAPI Depends(get_email_sender).

    Why cache?
      - Building the object is cheap, but we avoid re-reading logic every request.
      - Tests can clear the cache: get_email_sender.cache_clear()
    """
    return build_email_sender()
