"""
Email OTP request/verify schemas.
"""

from pydantic import BaseModel, EmailStr, Field

from app.schemas.auth import Token


class OtpRequest(BaseModel):
    """Body for POST /auth/otp/request."""

    email: EmailStr


class OtpRequestResponse(BaseModel):
    """
    Response after requesting an OTP.

    In development (DEBUG=true) we may include `dev_code` so you can test
    without a real email provider. Never set in production.
    """

    message: str = "If the email is valid, an OTP has been sent."
    expires_in_seconds: int = 300
    # Only populated when settings.debug is True (see service layer).
    dev_code: str | None = None


class OtpVerify(BaseModel):
    """Body for POST /auth/otp/verify."""

    email: EmailStr
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class OtpVerifyResponse(BaseModel):
    """Successful OTP verify returns the same JWT shape as password login."""

    access_token: str
    token_type: str = "bearer"
    is_new_user: bool = False


# Re-export Token name clarity for OpenAPI readers (optional alias).
TokenAfterOtp = Token
