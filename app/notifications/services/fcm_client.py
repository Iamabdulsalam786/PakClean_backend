"""Lazy Firebase Admin SDK init + FCM HTTP v1 send helpers."""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_firebase_ready = False


def init_firebase(credentials_path: str | None) -> bool:
    """Initialize Firebase Admin once per process. Returns True if ready."""
    global _firebase_ready
    if _firebase_ready:
        return True
    if not credentials_path:
        logger.warning("FIREBASE_CREDENTIALS_PATH not set — push notifications disabled")
        return False

    try:
        import firebase_admin
        from firebase_admin import credentials
    except ImportError:
        logger.error("firebase-admin not installed — push notifications disabled")
        return False

    if firebase_admin._apps:
        _firebase_ready = True
        return True

    path = Path(credentials_path)
    if not path.is_absolute():
        # Resolve relative to Pakclean_backend/ project root
        backend_root = Path(__file__).resolve().parents[3]
        path = backend_root / path

    if not path.is_file():
        logger.error("Firebase credentials file not found: %s", path)
        return False

    try:
        cred = credentials.Certificate(str(path))
        firebase_admin.initialize_app(cred)
        _firebase_ready = True
        logger.info("Firebase Admin initialized for FCM")
    except Exception:
        logger.exception("Failed to initialize Firebase Admin")
        return False

    return True


def send_push(
    *,
    tokens: list[str],
    title: str,
    body: str,
    data: dict[str, str] | None = None,
) -> int:
    """
    Send FCM to device tokens. Returns count of successful sends.
    Invalid tokens are logged; callers may prune stale tokens later.
    """
    if not tokens:
        return 0

    if not _firebase_ready:
        return 0

    try:
        from firebase_admin import messaging
    except ImportError:
        return 0

    payload_data = {k: str(v) for k, v in (data or {}).items()}
    success = 0

    for token in tokens:
        try:
            message = messaging.Message(
                notification=messaging.Notification(title=title, body=body),
                data=payload_data,
                token=token,
                android=messaging.AndroidConfig(priority="high"),
            )
            messaging.send(message)
            success += 1
        except Exception:
            logger.exception("FCM send failed token_prefix=%s", token[:12])

    return success
