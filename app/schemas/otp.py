"""
Email OTP request/verify schemas.
"""

from pydantic import BaseModel, EmailStr, Field

from app.schemas.auth import Token


class OtpRequest(BaseModel):
    """Body for POST /auth/otp/request."""

    email: EmailStr


class OtpRequestResponse(BaseModel):
    """Response after requesting an OTP."""

    message: str = "If the email is valid, an OTP has been sent."
    expires_in_seconds: int = 300
    email_delivered: bool = False
    delivery_provider: str | None = None
    dev_code: str | None = None


class OtpVerify(BaseModel):
    """Body for POST /auth/otp/verify."""

    email: EmailStr
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


# OTP verify now returns AuthSessionResponse from app.schemas.auth
