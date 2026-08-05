"""
BookingStatus — marketplace booking lifecycle vocabulary.

Why this file (feature-leaning domain type):
  - Phase-1 bookings used pending/confirmed/cancelled/completed only.
  - Marketplace flow needs REJECTED (provider decline) and IN_PROGRESS (job started).
  - One enum shared by ORM, Pydantic, services, and Alembic — no string drift.
  - Transition helpers document the legal state machine in code (interview gold).

Soft rules:
  - Reviews are NOT a status; they are a separate entity after COMPLETED.
  - CANCELLED is terminal (customer/provider/system cancel policies live in service).

Values are lowercase for stable Postgres ENUM + JSON (same pattern as ListingStatus).
"""

from __future__ import annotations

import enum


class BookingStatus(str, enum.Enum):
    """
    Lifecycle of a marketplace booking (listing_id-based).

    PENDING:
      Customer created the request. Waiting for the listing's provider.

    CONFIRMED:
      Provider accepted. Job is scheduled; not started yet.

    REJECTED:
      Provider declined. Terminal for this booking (customer may re-book).

    IN_PROGRESS:
      Provider marked the job as started.

    COMPLETED:
      Provider finished. Eligible for customer review (separate module).

    CANCELLED:
      Cancelled by customer (or later provider/admin policy). Terminal.
    """

    PENDING = "pending"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"

    def is_terminal(self) -> bool:
        """Terminal states cannot transition further."""
        return self in {
            BookingStatus.REJECTED,
            BookingStatus.COMPLETED,
            BookingStatus.CANCELLED,
        }

    def can_transition_to(self, new_status: BookingStatus) -> bool:
        """
        Legal edges of the marketplace state machine.

        Service layer still enforces *who* may trigger each edge.
        """
        allowed: dict[BookingStatus, set[BookingStatus]] = {
            BookingStatus.PENDING: {
                BookingStatus.CONFIRMED,
                BookingStatus.REJECTED,
                BookingStatus.CANCELLED,
            },
            BookingStatus.CONFIRMED: {
                BookingStatus.IN_PROGRESS,
                BookingStatus.CANCELLED,
            },
            BookingStatus.IN_PROGRESS: {
                BookingStatus.COMPLETED,
            },
            BookingStatus.REJECTED: set(),
            BookingStatus.COMPLETED: set(),
            BookingStatus.CANCELLED: set(),
        }
        return new_status in allowed.get(self, set())
