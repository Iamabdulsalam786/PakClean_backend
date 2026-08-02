from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import AppHTTPException
from app.core.security import decode_access_token

DbSession = Annotated[AsyncSession, Depends(get_db)]


async def get_current_user_id(authorization: Annotated[str | None, Header()] = None) -> UUID:
    if not authorization or not authorization.startswith("Bearer "):
        raise AppHTTPException(
            status_code=401,
            message="Missing or invalid authorization header",
            code="UNAUTHORIZED",
        )

    token = authorization.removeprefix("Bearer ").strip()
    try:
        payload = decode_access_token(token)
    except ValueError as exc:
        raise AppHTTPException(
            status_code=401,
            message="Invalid or expired access token",
            code="UNAUTHORIZED",
        ) from exc

    return UUID(payload["sub"])
