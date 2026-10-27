"""FastAPI application factory."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import files, generation, health, models
from app.core.config import Settings, get_settings
from app.core.errors import register_error_handlers
from app.core.limits import BodySizeLimitMiddleware
from app.services.generation_service import GenerationService
from app.services.image_engine import DiffusersImageEngine, ImageEngine

API_PREFIX = "/api/v1"

_DEFAULT = object()


def _default_engine(settings: Settings) -> ImageEngine | None:
    # Constructing the engine is cheap: nothing is imported or loaded until first use.
    return DiffusersImageEngine(settings) if settings.image_engine == "diffusers" else None


def create_app(settings: Settings | None = None, engine: ImageEngine | None | object = _DEFAULT) -> FastAPI:
    settings = settings or get_settings()
    image_engine = _default_engine(settings) if engine is _DEFAULT else engine
    service = GenerationService(settings, image_engine)  # type: ignore[arg-type]

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        service.shutdown()

    app = FastAPI(
        title=settings.app_name,
        version=settings.version,
        description=(
            "Backend for AI Video Studio. Text-to-image runs on a local open-weight model; "
            "video modes are not connected yet. Jobs are kept in memory and lost on restart."
        ),
        docs_url="/docs" if settings.docs_enabled else None,
        redoc_url="/redoc" if settings.docs_enabled else None,
        openapi_url=f"{API_PREFIX}/openapi.json" if settings.docs_enabled else None,
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.generation_service = service

    # Order matters: the last added middleware runs first, so CORS headers wrap every response.
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=settings.max_request_bytes)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "Accept"],
        expose_headers=["Content-Disposition"],
    )

    register_error_handlers(app)

    api = APIRouter(prefix=API_PREFIX)
    api.include_router(health.router)
    api.include_router(generation.router)
    api.include_router(models.router)
    api.include_router(files.router)
    app.include_router(api)
    return app


app = create_app()
