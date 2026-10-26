"""Health, readiness and application info."""

from datetime import UTC, datetime

from fastapi import APIRouter

from app.api.deps import GenerationServiceDep, SettingsDep
from app.schemas.generation import (
    DURATION_OPTIONS_SECONDS,
    MAX_SOURCE_IMAGE_BYTES,
    PROMPT_MAX_CHARS,
    AspectRatio,
    GenerationMode,
    SourceImageInfo,
    VisualStyle,
)
from app.schemas.system import (
    GenerationAvailability,
    HealthResponse,
    InfoResponse,
    Limits,
    ReadinessCheck,
    ReadinessResponse,
)

router = APIRouter(tags=["system"])


def _source_image_types() -> list[str]:
    annotation = SourceImageInfo.model_fields["content_type"].annotation
    return list(getattr(annotation, "__args__", ()))


@router.get("/health", response_model=HealthResponse, summary="Liveness check")
def health(settings: SettingsDep) -> HealthResponse:
    return HealthResponse(service=settings.app_name, version=settings.version, timestamp=datetime.now(UTC))


@router.get("/health/ready", response_model=ReadinessResponse, summary="Readiness of the API itself")
def ready(settings: SettingsDep, service: GenerationServiceDep) -> ReadinessResponse:
    engine_check = (
        ReadinessCheck(status="ok", detail=f"Engine '{service.engine.name}' is configured.")
        if service.available
        else ReadinessCheck(status="not_configured", detail="No AI engine is connected. Generation requests return 501.")
    )
    checks = {
        "api": ReadinessCheck(status="ok", detail="Serving requests."),
        "config": ReadinessCheck(status="ok", detail=f"Loaded for '{settings.environment}'."),
        "generation_engine": engine_check,
    }
    # The engine is optional for readiness: the API can serve validation and info without it.
    return ReadinessResponse(ready=checks["api"].status == "ok" and checks["config"].status == "ok", checks=checks)


@router.get("/info", response_model=InfoResponse, summary="Application metadata and capabilities")
def info(settings: SettingsDep, service: GenerationServiceDep) -> InfoResponse:
    return InfoResponse(
        name=settings.app_name,
        version=settings.version,
        environment=settings.environment,
        modes=list(GenerationMode),
        aspect_ratios=list(AspectRatio),
        styles=list(VisualStyle),
        limits=Limits(
            prompt_max_chars=PROMPT_MAX_CHARS,
            duration_options_seconds=list(DURATION_OPTIONS_SECONDS),
            source_image_max_bytes=MAX_SOURCE_IMAGE_BYTES,
            source_image_types=_source_image_types(),
            max_request_bytes=settings.max_request_bytes,
        ),
        generation=GenerationAvailability(
            available=service.available,
            engine=service.engine.name,
            message=(
                "AI generation is available."
                if service.available
                else "AI generation is not configured yet. Requests can be validated, but no media is generated."
            ),
        ),
    )
