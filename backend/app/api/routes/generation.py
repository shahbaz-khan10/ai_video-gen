"""Generation endpoints. Text-to-image and text-to-video run on local models where available."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Path

from app.api.deps import GenerationServiceDep
from app.schemas.generation import (
    ErrorResponse,
    GenerationJob,
    GenerationMode,
    GenerationRequest,
    ValidationResponse,
)
from app.schemas.scene_plan import ScenePlan
from app.services.prompt_understanding import PromptUnderstandingEngine

router = APIRouter(prefix="/generations", tags=["generations"])

_validation_error = {422: {"model": ErrorResponse, "description": "Invalid generation settings"}}


@router.post(
    "/validate",
    response_model=ValidationResponse,
    responses=_validation_error,
    summary="Validate and normalize a request without generating anything",
)
def validate_generation(request: GenerationRequest, service: GenerationServiceDep) -> ValidationResponse:
    generation_available = False
    if request.mode == GenerationMode.TEXT_TO_IMAGE:
        generation_available = service.available
    elif request.mode == GenerationMode.IMAGE_TO_VIDEO:
        status = getattr(service.video_engine, "i2v_status", None)
        generation_available = bool(status and status()[0])
    elif request.mode == GenerationMode.TEXT_TO_VIDEO:
        try:
            if service.video_engine is not None:
                service.video_engine.ensure_can_accept()
                generation_available = True
        except Exception:
            generation_available = False

    scene_plan_dict = None
    if request.mode == GenerationMode.TEXT_TO_IMAGE:
        try:
            plan = PromptUnderstandingEngine.plan_scene(request.prompt, request.style)
            scene_plan_dict = plan.to_dict()
        except Exception:
            scene_plan_dict = None

    return ValidationResponse(
        settings=service.normalize(request),
        generation_available=generation_available,
        scene_plan=scene_plan_dict,
    )


@router.post(
    "/plan",
    summary="Generate a structured scene plan and optimized prompt breakdown",
)
def plan_scene_endpoint(request: GenerationRequest) -> dict[str, Any]:
    plan = PromptUnderstandingEngine.plan_scene(request.prompt, request.style)
    return plan.to_dict()


@router.post(
    "",
    status_code=202,
    response_model=GenerationJob,
    responses={
        **_validation_error,
        429: {"model": ErrorResponse, "description": "Generation queue is full"},
        501: {"model": ErrorResponse, "description": "Mode not available or generation disabled"},
        503: {"model": ErrorResponse, "description": "Model libraries or weights are missing"},
    },
    summary="Queue a generation",
)
def create_generation(request: GenerationRequest, service: GenerationServiceDep) -> GenerationJob:
    return service.create(request)


@router.get(
    "/{generation_id}",
    response_model=GenerationJob,
    responses={404: {"model": ErrorResponse, "description": "Unknown generation (jobs are lost on restart)"}},
    summary="Get a generation's real status",
)
def get_generation(
    service: GenerationServiceDep,
    generation_id: uuid.UUID = Path(description="Generation ID (UUID)."),
) -> GenerationJob:
    return service.get(str(generation_id))


@router.post(
    "/scene-plan",
    response_model=ScenePlan,
    responses=_validation_error,
    summary="How a prompt will be understood: characters, place, camera, scenes, coverage and limitations",
)
def scene_plan(request: GenerationRequest, service: GenerationServiceDep) -> ScenePlan:
    return service.plan(request)


@router.post(
    "/{generation_id}/scenes/{index}/retry",
    response_model=GenerationJob,
    status_code=202,
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
    summary="Retry one failed scene of a long video; finished clips are reused",
)
def retry_scene(
    service: GenerationServiceDep,
    generation_id: uuid.UUID = Path(description="Generation ID (UUID)."),
    index: int = Path(ge=1, le=24, description="Scene number (1-based)."),
) -> GenerationJob:
    return service.retry_scene(str(generation_id), index)


@router.post(
    "/{generation_id}/cancel",
    response_model=GenerationJob,
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
    summary="Cancel a queued or running video generation (a running one stops at its next step)",
)
def cancel_generation(
    service: GenerationServiceDep,
    generation_id: uuid.UUID = Path(description="Generation ID (UUID)."),
) -> GenerationJob:
    return service.cancel(str(generation_id))


@router.post(
    "/{generation_id}/retry",
    response_model=GenerationJob,
    status_code=202,
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}, 429: {"model": ErrorResponse}},
    summary="Run a failed or cancelled single generation again with the same settings and seed",
)
def retry_generation(
    service: GenerationServiceDep,
    generation_id: uuid.UUID = Path(description="Generation ID (UUID)."),
) -> GenerationJob:
    return service.retry(str(generation_id))
