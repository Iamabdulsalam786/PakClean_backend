"""
OtpPurpose — why an OTP row was issued.

Why this file exists:
  - Registration and password-reset both use otp_codes.
  - Mixing them without a purpose allows cross-flow abuse
    (e.g. using a signup OTP to reset a password).
  - One enum keeps API, service, repository, and DB aligned (DRY + type safety).

Values are lowercase strings for stable JSON/DB storage (same pattern as UserRole).
"""

from __future__ import annotations

import enum


class OtpPurpose(str, enum.Enum):
    """
    Discriminator for rows in otp_codes.

    EMAIL_VERIFICATION:
      Issued during register / resend-otp. Proves mailbox ownership before login.

    PASSWORD_RESET:
      Issued during forgot-password. Proves mailbox ownership before changing password.
    """

    EMAIL_VERIFICATION = "email_verification"
    PASSWORD_RESET = "password_reset"
