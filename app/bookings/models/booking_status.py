"""
BookingStatus — marketplace booking lifecycle vocabulary.

Lifecycle (marketplace):
  PENDING → provider accepts → CONFIRMED
  CONFIRMED → provider starts → IN_PROGRESS
  IN_PROGRESS → provider marks work done → AWAITING_CONFIRMATION
  AWAITING_CONFIRMATION → customer confirms → COMPLETED

Reviews are a separate entity after COMPLETED (optional for customer).

Terminal: REJECTED, COMPLETED, CANCELLED
"""

from __future__ import annotations

import enum


class BookingStatus(str, enum.Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    IN_PROGRESS = "in_progress"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    COMPLETED = "completed"
    CANCELLED = "cancelled"

    def is_terminal(self) -> bool:
        return self in {
            BookingStatus.REJECTED,
            BookingStatus.COMPLETED,
            BookingStatus.CANCELLED,
        }

    def can_transition_to(self, new_status: BookingStatus) -> bool:
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
                BookingStatus.AWAITING_CONFIRMATION,
            },
            BookingStatus.AWAITING_CONFIRMATION: {
                BookingStatus.COMPLETED,
            },
            BookingStatus.REJECTED: set(),
            BookingStatus.COMPLETED: set(),
            BookingStatus.CANCELLED: set(),
        }
        return new_status in allowed.get(self, set())
