"""
FastAPI application entrypoint.

Run from pak-clean-backend (venv active):
  uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

Then open:
  http://127.0.0.1:8000/health
  http://127.0.0.1:8000/docs
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_v1_router
from app.core.config import settings
from app.integrations.email import get_email_provider_status


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

    @application.get("/health", tags=["system"])
    def health_check() -> dict[str, str]:
        """
        Liveness probe for load balancers / Docker / interview demos.

        Does not check DB yet — that can be /ready later (readiness probe).
        """
        return {
            "status": "ok",
            "app": settings.app_name,
            "env": settings.app_env,
        }

    @application.get("/health/email", tags=["system"])
    def email_health() -> dict[str, object]:
        """Shows whether real email delivery is configured (dev helper)."""
        return get_email_provider_status()

    # Mount all versioned API routes under /api/v1 (see settings.api_v1_prefix).
    application.include_router(api_v1_router, prefix=settings.api_v1_prefix)

    return application


app = create_app()
