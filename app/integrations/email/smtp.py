import logging
import smtplib
from email.message import EmailMessage

from app.core.config import settings
from app.integrations.email.base import EmailDeliveryResult, EmailProvider, OtpEmailPayload

logger = logging.getLogger(__name__)


class SmtpEmailProvider(EmailProvider):
    name = "smtp"

    def is_configured(self) -> bool:
        return bool(
            settings.smtp_enabled
            and settings.smtp_host
            and settings.smtp_from_email
            and settings.smtp_user
            and settings.smtp_password
        )

    def send_otp(self, payload: OtpEmailPayload) -> EmailDeliveryResult:
        if not self.is_configured():
            missing = []
            if not settings.smtp_password:
                missing.append("SMTP_PASSWORD")
            if not settings.smtp_user:
                missing.append("SMTP_USER")
            detail = f"SMTP incomplete — set: {', '.join(missing) or 'check .env'}"
            return EmailDeliveryResult(delivered=False, provider=self.name, detail=detail)

        subject = f"{settings.app_name} — Your verification code"
        text = (
            f"Hi,\n\nYour PakClean verification code is:\n\n  {payload.code}\n\n"
            f"This code expires in {payload.expires_minutes} minutes.\n\n"
            f"— {settings.app_name}\n"
        )

        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = settings.smtp_from_display
        message["To"] = payload.to_email
        message.set_content(text)

        try:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as server:
                if settings.smtp_use_tls:
                    server.starttls()
                server.login(settings.smtp_user, settings.smtp_password)
                server.send_message(message)
        except Exception as exc:
            logger.exception("SMTP OTP email failed for %s", payload.to_email)
            return EmailDeliveryResult(
                delivered=False,
                provider=self.name,
                detail=str(exc),
            )

        logger.info("SMTP OTP email sent to %s", payload.to_email)
        return EmailDeliveryResult(
            delivered=True,
            provider=self.name,
            detail="sent via Gmail/SMTP",
        )
