"""
NotificationService — in-app inbox + FCM push for booking lifecycle events.

Each lifecycle step notifies the right party (often both customer and provider).
Push failures never break booking mutations (caller wraps in try/except).
"""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.booking import Booking
from app.models.user import User
from app.service_listings.models.service_listing import ServiceListing
from app.notifications.repositories.device_token_repository import DeviceTokenRepository
from app.notifications.repositories.notification_repository import NotificationRepository
from app.notifications.schemas.notification import NotificationListResponse, NotificationRead
from app.notifications.services.fcm_client import init_firebase, send_push

logger = logging.getLogger(__name__)

# (notification_type, title, body) — body may be prefixed with listing title
BOOKING_EVENT_COPY: dict[str, tuple[str, str, str]] = {
    "booking_created": (
        "booking_created",
        "New booking request",
        "A customer requested your service.",
    ),
    "booking_created_customer": (
        "booking_created_customer",
        "Booking submitted",
        "Your booking request was sent to the provider.",
    ),
    "booking_accepted": (
        "booking_accepted",
        "Booking accepted",
        "Your provider accepted the booking.",
    ),
    "booking_accepted_provider": (
        "booking_accepted_provider",
        "Booking confirmed",
        "You accepted this booking request.",
    ),
    "booking_rejected": (
        "booking_rejected",
        "Booking declined",
        "Your booking request was declined.",
    ),
    "booking_started": (
        "booking_started",
        "Service started",
        "Your provider has started the job.",
    ),
    "booking_started_provider": (
        "booking_started_provider",
        "Work started",
        "You started work on this booking.",
    ),
    "booking_provider_completed": (
        "booking_provider_completed",
        "Confirm your service",
        "The provider marked the job as done. Please confirm completion.",
    ),
    "booking_provider_completed_provider": (
        "booking_provider_completed_provider",
        "Awaiting confirmation",
        "You marked the job as done. Waiting for the customer to confirm.",
    ),
    "booking_customer_confirmed": (
        "booking_customer_confirmed",
        "Booking completed",
        "The customer confirmed the service was completed.",
    ),
    "booking_customer_confirmed_customer": (
        "booking_customer_confirmed_customer",
        "Service completed",
        "Thanks for confirming. This booking is now complete.",
    ),
    "booking_cancelled_customer": (
        "booking_cancelled_customer",
        "Booking cancelled",
        "You cancelled this booking.",
    ),
    "booking_cancelled_provider": (
        "booking_cancelled_provider",
        "Booking cancelled",
        "The customer cancelled this booking.",
    ),
}

LISTING_PUBLISHED_COPY = (
    "Service published",
    "Your listing is now live. Push notifications are working.",
)


class NotificationService:
    def __init__(self, db: Session) -> None:
        self._db = db
        self._devices = DeviceTokenRepository(db)
        self._notifications = NotificationRepository(db)
        init_firebase(settings.firebase_credentials_path)

    def register_device(self, user: User, *, token: str, platform: str) -> None:
        if platform not in {"android", "ios"}:
            platform = "android"
        self._devices.upsert(user_id=user.id, token=token, platform=platform)
        self._db.commit()

    def unregister_device(self, user: User, *, token: str) -> None:
        self._devices.delete_token(user_id=user.id, token=token)
        self._db.commit()

    def list_notifications(
        self,
        user: User,
        *,
        page: int = 1,
        page_size: int = 20,
    ) -> NotificationListResponse:
        page = max(1, page)
        page_size = min(max(1, page_size), 50)
        offset = (page - 1) * page_size
        rows = self._notifications.list_for_user(user.id, limit=page_size, offset=offset)
        return NotificationListResponse(
            items=[NotificationRead.model_validate(row) for row in rows],
            total=self._notifications.count_for_user(user.id),
            unread_count=self._notifications.count_unread(user.id),
            page=page,
            page_size=page_size,
        )

    def unread_count(self, user: User) -> int:
        return self._notifications.count_unread(user.id)

    def mark_read(self, user: User, notification_id: UUID) -> NotificationRead | None:
        row = self._notifications.mark_read(user_id=user.id, notification_id=notification_id)
        if row is None:
            return None
        self._db.commit()
        return NotificationRead.model_validate(row)

    def mark_all_read(self, user: User) -> int:
        count = self._notifications.mark_all_read(user.id)
        self._db.commit()
        return count

    def notify_booking_event(self, booking: Booking, event: str) -> None:
        deliveries = self._deliveries_for_booking_event(booking, event)
        for delivery in deliveries:
            self._deliver_booking_notification(booking, delivery)

    def _deliver_booking_notification(
        self,
        booking: Booking,
        delivery: tuple[UUID, str, str, str],
    ) -> None:
        recipient_id, event_type, title, body = delivery

        self._notifications.add(
            user_id=recipient_id,
            type=event_type,
            title=title,
            body=body,
            booking_id=booking.id,
        )
        self._db.commit()

        tokens = self._devices.list_tokens_for_user(recipient_id)
        data = {
            "type": event_type,
            "booking_id": str(booking.id),
        }
        sent = send_push(tokens=tokens, title=title, body=body, data=data)
        logger.info(
            "booking_notification event=%s booking_id=%s recipient=%s push_sent=%s",
            event_type,
            booking.id,
            recipient_id,
            sent,
        )

    @staticmethod
    def _body_with_listing(booking: Booking, body: str) -> str:
        if booking.listing_title_snapshot:
            return f"{booking.listing_title_snapshot}: {body}"
        return body

    @classmethod
    def _copy_delivery(
        cls,
        booking: Booking,
        user_id: UUID | None,
        copy_key: str,
    ) -> tuple[UUID, str, str, str] | None:
        if user_id is None:
            return None
        entry = BOOKING_EVENT_COPY.get(copy_key)
        if entry is None:
            return None
        event_type, title, body = entry
        return (user_id, event_type, title, cls._body_with_listing(booking, body))

    def _deliveries_for_booking_event(
        self,
        booking: Booking,
        event: str,
    ) -> list[tuple[UUID, str, str, str]]:
        deliveries: list[tuple[UUID, str, str, str]] = []

        def add(user_id: UUID | None, copy_key: str) -> None:
            delivery = self._copy_delivery(booking, user_id, copy_key)
            if delivery is not None:
                deliveries.append(delivery)

        if event == "booking_created":
            add(booking.provider_id, "booking_created")
            add(booking.customer_id, "booking_created_customer")
        elif event == "booking_accepted":
            add(booking.customer_id, "booking_accepted")
            add(booking.provider_id, "booking_accepted_provider")
        elif event == "booking_rejected":
            add(booking.customer_id, "booking_rejected")
        elif event == "booking_started":
            add(booking.customer_id, "booking_started")
            add(booking.provider_id, "booking_started_provider")
        elif event == "booking_provider_completed":
            add(booking.customer_id, "booking_provider_completed")
            add(booking.provider_id, "booking_provider_completed_provider")
        elif event == "booking_customer_confirmed":
            add(booking.provider_id, "booking_customer_confirmed")
            add(booking.customer_id, "booking_customer_confirmed_customer")
        elif event == "booking_cancelled":
            add(booking.customer_id, "booking_cancelled_customer")
            add(booking.provider_id, "booking_cancelled_provider")

        return deliveries

    def notify_listing_published(self, provider: User, listing: ServiceListing) -> None:
        """Confirm push pipeline when a provider publishes a listing."""
        event = "listing_published"
        title, body = LISTING_PUBLISHED_COPY
        body = f'"{listing.title}" is now live. Push notifications are working!'

        self._notifications.add(
            user_id=provider.id,
            type=event,
            title=title,
            body=body,
        )
        self._db.commit()

        tokens = self._devices.list_tokens_for_user(provider.id)
        data = {
            "type": event,
            "listing_id": str(listing.id),
        }
        sent = send_push(tokens=tokens, title=title, body=body, data=data)
        logger.info(
            "listing_notification event=%s listing_id=%s recipient=%s push_sent=%s",
            event,
            listing.id,
            provider.id,
            sent,
        )


def dispatch_booking_notification(db: Session, booking: Booking, event: str) -> None:
    """Fire-and-forget helper for booking_service — never raises."""
    try:
        NotificationService(db).notify_booking_event(booking, event)
    except Exception:
        logger.exception(
            "booking_notification_failed event=%s booking_id=%s",
            event,
            booking.id,
        )


def dispatch_listing_published_notification(
    db: Session,
    provider: User,
    listing: ServiceListing,
) -> None:
    """Fire-and-forget helper for listing publish — never raises."""
    try:
        NotificationService(db).notify_listing_published(provider, listing)
    except Exception:
        logger.exception(
            "listing_notification_failed event=listing_published listing_id=%s",
            listing.id,
        )
