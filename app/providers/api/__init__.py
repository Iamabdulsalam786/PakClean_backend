"""providers.api — HTTP adapters for the provider feature."""

from app.providers.api.profiles import admin_router, provider_router

__all__ = ["admin_router", "provider_router"]
