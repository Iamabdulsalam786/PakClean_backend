from app.core.config import settings


async def send_otp_email(*, to_email: str, otp: str, purpose: str) -> None:
    subject = "PakClean verification code"
    if purpose == "password_reset":
        subject = "PakClean password reset code"

    body = (
        f"Your PakClean verification code is: {otp}\n\n"
        f"This code expires in {settings.otp_expires_minutes} minutes.\n"
        "If you did not request this, you can ignore this email."
    )

    if not settings.smtp_host:
        print(f"[DEV OTP] {purpose} → {to_email}: {otp}")
        return

    import aiosmtplib
    from email.message import EmailMessage

    message = EmailMessage()
    message["From"] = settings.smtp_from
    message["To"] = to_email
    message["Subject"] = subject
    message.set_content(body)

    await aiosmtplib.send(
        message,
        hostname=settings.smtp_host,
        port=settings.smtp_port,
        username=settings.smtp_user,
        password=settings.smtp_pass,
        start_tls=True,
    )
