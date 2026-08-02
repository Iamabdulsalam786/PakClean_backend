from fastapi import APIRouter, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.v1.auth import router as auth_router
from app.core.config import settings
from app.core.exceptions import AppHTTPException

api_router = APIRouter(prefix=settings.api_prefix)
api_router.include_router(auth_router, prefix="/auth", tags=["Auth"])


@api_router.get("/health", tags=["Health"])
async def health_check() -> dict[str, str]:
    return {"status": "ok", "service": settings.app_name}


async def app_http_exception_handler(_: Request, exc: AppHTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "message": exc.message,
            "code": exc.code,
            "errors": exc.errors,
        },
    )


async def validation_exception_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    errors: dict[str, list[str]] = {}
    for error in exc.errors():
        loc = error.get("loc", [])
        field = str(loc[-1]) if loc else "root"
        errors.setdefault(field, []).append(error.get("msg", "Invalid value"))

    return JSONResponse(
        status_code=422,
        content={
            "success": False,
            "message": "Validation failed",
            "code": "VALIDATION_ERROR",
            "errors": errors,
        },
    )
