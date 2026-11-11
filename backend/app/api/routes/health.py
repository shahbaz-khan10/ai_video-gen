"""Health, readiness, application info and image-model status. None of these load the model."""

from datetime import UTC, datetime

from fastapi import APIRouter

from app.api.deps import GenerationServiceDep, SettingsDep
from app.core.models_registry import get_model_profile, is_known_model
from app.schemas.generation import (
    DURATION_OPTIONS_SECONDS,
    IMAGE_SIZES,
    IMAGE_STEP_OPTIONS,
    MAX_SEED,
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
    ImageModelStatus,
    ImageSizeOption,
    InfoResponse,
    Limits,
    ModelLicense,
    ReadinessCheck,
    ReadinessResponse,
)
from app.services.generation_service import GenerationService

router = APIRouter(tags=["system"])

def _step_presets(model_id: str | None) -> list[int]:
    """Fast / balanced / best step counts for the current model, so the UI never offers unusable values."""
    if not model_id or not is_known_model(model_id):
        return list(IMAGE_STEP_OPTIONS)
    p = get_model_profile(model_id)
    return sorted({p.min_steps, p.default_steps, p.max_steps})


# Licenses of models we document. Unknown models report no license rather than a guessed one.
KNOWN_LICENSES = {
    "stabilityai/sd-turbo": ModelLicense(
        name="Stability AI Community License",
        url="https://huggingface.co/stabilityai/sd-turbo/blob/main/LICENSE.md",
        attribution="Powered by Stability AI",
    ),
    "SG161222/RealVisXL_V5.0_Lightning": ModelLicense(
        name="CreativeML Open RAIL++-M",
        url="https://huggingface.co/SG161222/RealVisXL_V5.0_Lightning",
        attribution="RealVisXL V5.0 Lightning by SG161222",
    ),
}


def _source_image_types() -> list[str]:
    annotation = SourceImageInfo.model_fields["content_type"].annotation
    return list(getattr(annotation, "__args__", ()))


def image_model_status(service: GenerationService) -> ImageModelStatus:
    status = service.engine_status()
    if status is None:
        return ImageModelStatus(
            engine="none", model_id=None, state="disabled", detail="AI generation is turned off.", can_generate=False
        )
    return ImageModelStatus(
        engine=service.engine.name,  # type: ignore[union-attr]
        model_id=status.model_id,
        state=status.state,
        detail=status.detail,
        device=status.device,
        optimizations=status.optimizations,
        can_generate=service.available,
    )


@router.get("/health", response_model=HealthResponse, summary="Liveness check")
def health(settings: SettingsDep) -> HealthResponse:
    return HealthResponse(service=settings.app_name, version=settings.version, timestamp=datetime.now(UTC))


_MODEL_CHECK = {
    "disabled": "not_configured",
    "unavailable": "unavailable",
    "not_downloaded": "not_downloaded",
    "not_loaded": "not_loaded",
    "loading": "loading",
    "loaded": "ok",
    "error": "error",
}


@router.get("/health/ready", response_model=ReadinessResponse, summary="Readiness of the API and, separately, the model")
def ready(settings: SettingsDep, service: GenerationServiceDep) -> ReadinessResponse:
    model = image_model_status(service)
    checks = {
        "api": ReadinessCheck(status="ok", detail="Serving requests."),
        "config": ReadinessCheck(status="ok", detail=f"Loaded for '{settings.environment}'."),
        "image_model": ReadinessCheck(status=_MODEL_CHECK[model.state], detail=model.detail),  # type: ignore[arg-type]
    }
    return ReadinessResponse(ready=True, model_ready=model.state == "loaded", checks=checks)


@router.get("/info", response_model=InfoResponse, summary="Application metadata and capabilities")
def info(settings: SettingsDep, service: GenerationServiceDep) -> InfoResponse:
    model = image_model_status(service)
    available = model.can_generate
    if available:
        message = "Text-to-image runs on a local open-weight model. Video modes are coming soon."
    elif model.state == "disabled":
        message = "AI generation is turned off on this server."
    else:
        message = f"Text-to-image is not ready: {model.detail}"
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
            image_sizes=[
                ImageSizeOption(resolution=res, aspect_ratio=ratio, width=w, height=h)
                for res, by_ratio in IMAGE_SIZES.items()
                for ratio, (w, h) in by_ratio.items()
            ],
            image_steps=_step_presets(model.model_id),
            max_seed=MAX_SEED,
        ),
        generation=GenerationAvailability(
            available=available,
            modes_available=[GenerationMode.TEXT_TO_IMAGE] if available else [],
            engine=model.engine,
            model_id=model.model_id,
            license=KNOWN_LICENSES.get(model.model_id or ""),
            message=message,
        ),
    )
