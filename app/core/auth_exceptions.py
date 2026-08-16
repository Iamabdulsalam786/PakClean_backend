"""
Auth domain exceptions.

Why this file exists:
  - Services raise typed errors with stable `code` strings.
  - API routes map those codes → HTTP status codes.
  - Keeps business logic free of FastAPI's HTTPException.

Interview talking point:
  Domain layer should not know about HTTP. HTTP is a delivery detail.
"""

from __future__ import annotations


class AuthDomainError(Exception):
    """Base class for authentication / verification failures."""

    def __init__(self, message: str, *, code: str) -> None:
        self.message = message
        self.code = code
        super().__init__(message)


class EmailTakenError(AuthDomainError):
    def __init__(self) -> None:
        super().__init__("Email already registered", code="email_taken")


class PhoneTakenError(AuthDomainError):
    def __init__(self) -> None:
        super().__init__("Phone already registered", code="phone_taken")


class InvalidCredentialsError(AuthDomainError):
    def __init__(self) -> None:
        super().__init__("Invalid email or password", code="invalid_credentials")


class EmailNotVerifiedError(AuthDomainError):
    def __init__(self) -> None:
        super().__init__(
            "Email is not verified. Please verify the OTP sent to your email.",
            code="email_not_verified",
        )


class InactiveUserError(AuthDomainError):
    def __init__(self) -> None:
        super().__init__("Inactive user", code="inactive_user")


class InvalidOtpError(AuthDomainError):
    """Wrong / expired / used OTP — generic message to reduce enumeration."""

    def __init__(self, message: str = "Invalid or expired OTP") -> None:
        super().__init__(message, code="invalid_otp")


class OtpAttemptsExceededError(AuthDomainError):
    def __init__(self) -> None:
        super().__init__(
            "Too many invalid OTP attempts. Please request a new code.",
            code="otp_attempts_exceeded",
        )


class OtpResendCooldownError(AuthDomainError):
    def __init__(self, retry_after_seconds: int) -> None:
        self.retry_after_seconds = retry_after_seconds
        super().__init__(
            f"Please wait {retry_after_seconds} seconds before requesting another OTP.",
            code="otp_resend_cooldown",
        )


class InvalidRefreshTokenError(AuthDomainError):
    def __init__(self) -> None:
        super().__init__("Invalid or expired refresh token", code="invalid_refresh_token")


class EmailDeliveryError(AuthDomainError):
    def __init__(self, message: str = "Failed to send verification email") -> None:
        super().__init__(message, code="email_delivery_failed")
