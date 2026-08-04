import logging

from app.core.config import settings
from app.integrations.email.base import EmailDeliveryResult, OtpEmailPayload
from app.integrations.email.console import ConsoleEmailProvider
from app.integrations.email.resend import ResendEmailProvider
from app.integrations.email.smtp import SmtpEmailProvider

logger = logging.getLogger(__name__)

_resend = ResendEmailProvider()
_smtp = SmtpEmailProvider()
_console = ConsoleEmailProvider()


def _active_providers():
    if settings.email_provider == "resend":
        return [_resend, _console]
    if settings.email_provider == "smtp":
        return [_smtp, _console]
    if settings.email_provider == "console":
        return [_console]

    # auto — prefer Resend, then Gmail SMTP, then console
    providers: list = []
    if _resend.is_configured():
        providers.append(_resend)
    if _smtp.is_configured():
        providers.append(_smtp)
    providers.append(_console)
    return providers


def get_email_provider_status() -> dict[str, object]:
    return {
        "mode": settings.email_provider,
        "resend_ready": _resend.is_configured(),
        "smtp_ready": _smtp.is_configured(),
        "smtp_missing_password": settings.smtp_enabled and not settings.smtp_password,
        "active_provider": next(
            (p.name for p in _active_providers() if p.is_configured() and p.name != "console"),
            "console",
        ),
    }


def deliver_otp_email(*, to_email: str, code: str, expires_minutes: int) -> EmailDeliveryResult:
    payload = OtpEmailPayload(
        to_email=to_email,
        code=code,
        expires_minutes=expires_minutes,
    )

    for provider in _active_providers():
        if not provider.is_configured():
            continue

        result = provider.send_otp(payload)

        if result.delivered:
            return result

        if provider.name != "console":
            logger.warning(
                "Email provider %s failed (%s) — trying fallback",
                provider.name,
                result.detail,
            )

    return _console.send_otp(payload)
