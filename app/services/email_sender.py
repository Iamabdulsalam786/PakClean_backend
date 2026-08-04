"""
Email sender contract (port / interface).

Why this file exists first:
  Auth must send real OTPs, but AuthService must NOT import Gmail SMTP,
  Resend, or SendGrid directly. That would violate Dependency Inversion
  (SOLID-D) and force a rewrite of authentication when we change providers.

  This module defines ONLY the interface. Concrete adapters (SMTP, Resend)
  come in later files and plug into the same contract.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class EmailMessage:
    """
    Immutable email payload passed to any EmailSender implementation.

    Why a small dataclass instead of many loose arguments?
      - One object is easier to log (safely), test, and extend (cc, html, etc.)
      - frozen=True prevents accidental mutation after construction
      - slots=True reduces memory overhead for many sends (micro-optimization)
    """

    to_email: str
    subject: str
    body_text: str


class EmailSendError(Exception):
    """
    Raised when the email provider fails (SMTP down, bad credentials, etc.).

    Why a dedicated exception type?
      - AuthService can catch EmailSendError and map it to HTTP 503
      - Distinguishes "mail failed" from "validation failed" or "DB failed"
      - Never attach the OTP to this exception message (leak risk)
    """

    def __init__(self, message: str = "Failed to send email") -> None:
        self.message = message
        super().__init__(message)


class EmailSender(ABC):
    """
    Abstract email port.

    Any provider (Gmail SMTP, Resend, SES) must implement `send`.
    Auth / OTP services depend on THIS type, not on smtplib.
    """

    @abstractmethod
    def send(self, message: EmailMessage) -> None:
        """
        Deliver one email.

        Implementations must:
          - Raise EmailSendError on failure (not silent return)
          - Never log secrets or OTP codes
          - Be synchronous for Phase 1 (async queue can wrap this later)
        """
        raise NotImplementedError
