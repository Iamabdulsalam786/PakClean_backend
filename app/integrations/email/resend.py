import logging

import httpx

from app.core.config import settings
from app.integrations.email.base import EmailDeliveryResult, EmailProvider, OtpEmailPayload

logger = logging.getLogger(__name__)

RESEND_API_URL = "https://api.resend.com/emails"


class ResendEmailProvider(EmailProvider):
    name = "resend"

    def is_configured(self) -> bool:
        return bool(settings.resend_api_key and settings.resend_from_email)

    def send_otp(self, payload: OtpEmailPayload) -> EmailDeliveryResult:
        if not self.is_configured():
            return EmailDeliveryResult(
                delivered=False,
                provider=self.name,
                detail="Resend API key or from-email missing",
            )

        subject = f"{settings.app_name} — Your verification code"
        text = (
            f"Your PakClean verification code is: {payload.code}\n\n"
            f"It expires in {payload.expires_minutes} minutes.\n"
            f"If you did not request this, ignore this email."
        )

        body = {
            "from": settings.resend_from_display,
            "to": [payload.to_email],
            "subject": subject,
            "text": text,
        }

        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.post(
                    RESEND_API_URL,
                    headers={
                        "Authorization": f"Bearer {settings.resend_api_key}",
                        "Content-Type": "application/json",
                    },
                    json=body,
                )
                response.raise_for_status()
        except Exception as exc:
            logger.exception("Resend OTP email failed for %s", payload.to_email)
            return EmailDeliveryResult(
                delivered=False,
                provider=self.name,
                detail=str(exc),
            )

        logger.info("Resend OTP email sent to %s", payload.to_email)
        return EmailDeliveryResult(
            delivered=True,
            provider=self.name,
            detail="sent via Resend",
        )
