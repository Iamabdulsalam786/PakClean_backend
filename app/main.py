from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import (
    api_router,
    app_http_exception_handler,
    validation_exception_handler,
)
from app.core.config import settings
from app.core.database import Base, engine
import app.models.user  # noqa: F401 — register SQLAlchemy models
from app.core.exceptions import AppHTTPException


@asynccontextmanager
async def lifespan(_: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_exception_handler(AppHTTPException, app_http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.include_router(api_router)


@app.get("/")
async def root() -> dict[str, str]:
    return {
        "message": "PakClean API",
        "docs": "/docs",
        "health": f"{settings.api_prefix}/health",
    }
