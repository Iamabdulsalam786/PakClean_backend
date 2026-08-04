import logging

from app.integrations.email.base import EmailDeliveryResult, EmailProvider, OtpEmailPayload

logger = logging.getLogger(__name__)


class ConsoleEmailProvider(EmailProvider):
    """Dev fallback — logs OTP to terminal (no real email)."""

    name = "console"

    def is_configured(self) -> bool:
        return True

    def send_otp(self, payload: OtpEmailPayload) -> EmailDeliveryResult:
        logger.info(
            "OTP for %s: %s (expires in %s min) [console — no email provider configured]",
            payload.to_email,
            payload.code,
            payload.expires_minutes,
        )
        return EmailDeliveryResult(
            delivered=False,
            provider=self.name,
            detail="logged to backend terminal only",
        )
