from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class OtpEmailPayload:
    to_email: str
    code: str
    expires_minutes: int


@dataclass(frozen=True)
class EmailDeliveryResult:
    delivered: bool
    provider: str
    detail: str


class EmailProvider(ABC):
    name: str

    @abstractmethod
    def is_configured(self) -> bool: ...

    @abstractmethod
    def send_otp(self, payload: OtpEmailPayload) -> EmailDeliveryResult: ...
