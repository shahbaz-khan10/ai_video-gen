"""FastAPI application factory."""

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import generation, health
from app.core.config import Settings, get_settings
from app.core.errors import register_error_handlers
from app.core.limits import BodySizeLimitMiddleware
from app.services.generation_service import GenerationEngine, GenerationService, JobStore, UnconfiguredEngine

API_PREFIX = "/api/v1"


def create_app(settings: Settings | None = None, engine: GenerationEngine | None = None) -> FastAPI:
    settings = settings or get_settings()

    app = FastAPI(
        title=settings.app_name,
        version=settings.version,
        description="Backend for AI Video Studio. AI generation is not connected yet.",
        docs_url="/docs" if settings.docs_enabled else None,
        redoc_url="/redoc" if settings.docs_enabled else None,
        openapi_url=f"{API_PREFIX}/openapi.json" if settings.docs_enabled else None,
    )
    app.state.settings = settings
    app.state.generation_service = GenerationService(engine or UnconfiguredEngine(), JobStore())

    # Order matters: the last added middleware runs first, so CORS headers wrap every response.
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=settings.max_request_bytes)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "Accept"],
    )

    register_error_handlers(app)

    api = APIRouter(prefix=API_PREFIX)
    api.include_router(health.router)
    api.include_router(generation.router)
    app.include_router(api)
    return app


app = create_app()
