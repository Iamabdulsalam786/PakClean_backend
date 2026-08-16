"""
FastAPI application entrypoint.

Run from pak-clean-backend (venv active):
  uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

Then open:
  http://127.0.0.1:8000/health
  http://127.0.0.1:8000/docs
"""

from pathlib import Path

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.requests import Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.v1.router import api_v1_router
from app.core.config import settings
from app.db.session import engine
from app.notifications.services.fcm_client import init_firebase


def create_app() -> FastAPI:
    """
    Application factory — build and configure the FastAPI instance.

    Why a function instead of a bare `app = FastAPI()` at module level?
      - Tests can call create_app() with different settings later
      - Clear place to attach middleware, routers, and exception handlers
    """
    application = FastAPI(
        title=settings.app_name,
        debug=settings.debug,
        # Hide interactive docs in production (basic hardening).
        docs_url="/docs" if not settings.is_production else None,
        redoc_url="/redoc" if not settings.is_production else None,
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @application.get("/", tags=["system"])
    def root() -> dict[str, str]:
        """Helpful entrypoint — avoids bare 404 when opening the server root in a browser."""
        return {
            "status": "ok",
            "app": settings.app_name,
            "health": "/health",
            "docs": "/docs",
            "api": settings.api_v1_prefix,
        }

    @application.get("/health", tags=["system"])
    def health_check() -> dict[str, str]:
        """
        Liveness probe for load balancers / Docker / interview demos.

        Does not check DB — use /health/ready for database connectivity.
        """
        return {
            "status": "ok",
            "app": settings.app_name,
            "env": settings.app_env,
        }

    @application.get("/health/ready", tags=["system"])
    def readiness_check() -> dict[str, str]:
        """Readiness probe — verifies Postgres is reachable."""
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
        except SQLAlchemyError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=(
                    "Database is not running. From Pakclean_backend run: "
                    "docker compose up -d"
                ),
            ) from exc

        return {
            "status": "ok",
            "app": settings.app_name,
            "database": "connected",
        }

    @application.exception_handler(SQLAlchemyError)
    async def sqlalchemy_exception_handler(
        _request: Request,
        _exc: SQLAlchemyError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "detail": (
                    "Database is not available. From Pakclean_backend run: "
                    "docker compose up -d"
                ),
            },
        )

    # Mount all versioned API routes under /api/v1 (see settings.api_v1_prefix).
    application.include_router(api_v1_router, prefix=settings.api_v1_prefix)

    @application.on_event("startup")
    def _startup_init_firebase() -> None:
        init_firebase(settings.firebase_credentials_path)

    uploads_path = Path(settings.upload_dir)
    uploads_path.mkdir(parents=True, exist_ok=True)
    application.mount(
        "/uploads",
        StaticFiles(directory=str(uploads_path)),
        name="uploads",
    )

    return application


app = create_app()
