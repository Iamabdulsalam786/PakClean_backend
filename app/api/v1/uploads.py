"""
Multipart upload for listing gallery images (dev-friendly local storage).

Flow:
  1. Provider uploads file here → receives HTTPS/HTTP URL
  2. Client registers URL on listing via POST .../service-listings/{id}/images

Production: swap storage backend (S3/R2) — keep the same response shape.
"""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Request, UploadFile, status

from app.core.config import settings
from app.core.dependencies import CurrentProvider

router = APIRouter(prefix="/uploads", tags=["uploads"])

ALLOWED_CONTENT_TYPES = {
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/webp",
}
MAX_BYTES = 5 * 1024 * 1024


def _listing_upload_dir() -> Path:
    base = Path(settings.upload_dir)
    target = base / "listings"
    target.mkdir(parents=True, exist_ok=True)
    return target


def _extension_for(content_type: str) -> str:
    mapping = {
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
    }
    return mapping.get(content_type, ".jpg")


@router.post(
    "/listing-image",
    summary="Upload a listing gallery image (provider)",
)
async def upload_listing_image(
    request: Request,
    current_user: CurrentProvider,
    file: UploadFile = File(...),
) -> dict[str, str]:
    _ = current_user

    content_type = (file.content_type or "").lower()
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only JPEG, PNG, and WebP images are allowed",
        )

    data = await file.read()
    if not data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Empty file",
        )
    if len(data) > MAX_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Image must be 5 MB or smaller",
        )

    filename = f"{uuid.uuid4().hex}{_extension_for(content_type)}"
    destination = _listing_upload_dir() / filename
    destination.write_bytes(data)

    base = str(request.base_url).rstrip("/")
    public_url = f"{base}/uploads/listings/{filename}"

    return {
        "url": public_url,
        "path": f"/uploads/listings/{filename}",
    }
