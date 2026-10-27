"""Health, readiness and application info."""

from datetime import UTC, datetime

from fastapi import APIRouter

from app.api.deps import GenerationServiceDep, SettingsDep
from app.schemas.generation import (
    DURATION_OPTIONS_SECONDS,
    MAX_SOURCE_IMAGE_BYTES,
    PROMPT_MAX_CHARS,
    SEED_MAX,
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
    ModelReadiness,
    ReadinessCheck,
    ReadinessResponse,
)
from app.services.image_engine import EngineStatus

router = APIRouter(tags=["system"])

_ENGINE_MESSAGES = {
    "disabled": "AI generation is disabled on this server.",
    "not_installed": "AI image libraries are not installed on the server yet.",
    "weights_missing": "The image model is not downloaded yet, so images can't be generated.",
}


def _source_image_types() -> list[str]:
    annotation = SourceImageInfo.model_fields["content_type"].annotation
    return list(getattr(annotation, "__args__", ()))


def _model_readiness(status: EngineStatus) -> ModelReadiness:
    return ModelReadiness(
        state=status.state,
        loaded=status.state == "ready",
        accepts_jobs=status.accepts_jobs,
        model_id=status.model_id,
        device=status.device,
        cuda_available=status.cuda_available,
        detail=status.detail,
    )


@router.get("/health", response_model=HealthResponse, summary="Liveness check")
def health(settings: SettingsDep) -> HealthResponse:
    return HealthResponse(service=settings.app_name, version=settings.version, timestamp=datetime.now(UTC))


@router.get("/health/ready", response_model=ReadinessResponse, summary="Readiness of the API and the image model")
def ready(settings: SettingsDep, service: GenerationServiceDep) -> ReadinessResponse:
    # Lightweight: reports the engine's state without loading the model.
    status = service.engine.status()
    if status.state == "error":
        engine_check = ReadinessCheck(status="error", detail=status.detail)
    elif status.accepts_jobs:
        engine_check = ReadinessCheck(status="ok", detail=status.detail)
    else:
        engine_check = ReadinessCheck(status="not_configured", detail=status.detail)
    checks = {
        "api": ReadinessCheck(status="ok", detail="Serving requests."),
        "config": ReadinessCheck(status="ok", detail=f"Loaded for '{settings.environment}'."),
        "generation_engine": engine_check,
    }
    # The model is optional for readiness: the API can serve validation and info without it.
    return ReadinessResponse(
        ready=checks["api"].status == "ok" and checks["config"].status == "ok",
        checks=checks,
        model=_model_readiness(status),
    )


@router.get("/info", response_model=InfoResponse, summary="Application metadata and capabilities")
def info(settings: SettingsDep, service: GenerationServiceDep) -> InfoResponse:
    status = service.engine.status()
    available = status.accepts_jobs
    if available:
        message = f"Text-to-image runs locally on {status.model_id}. Video generation is not connected yet."
        if status.state == "error":
            message = f"The last model load failed: {status.detail} The next request will retry."
    else:
        message = _ENGINE_MESSAGES.get(status.state, status.detail)
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
            image_resolutions=settings.image_resolutions,
            image_default_resolution=settings.image_default_resolution,
            image_max_steps=settings.image_max_steps,
            image_step_presets=settings.image_step_presets,
            image_default_steps=settings.image_default_steps,
            seed_max=SEED_MAX,
        ),
        generation=GenerationAvailability(
            available=available,
            engine=service.engine.name,
            model_id=status.model_id,
            available_modes=[GenerationMode.TEXT_TO_IMAGE] if available else [],
            message=message,
        ),
    )
