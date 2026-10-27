"""Generation endpoints. Text-to-image runs on the local model; video modes return 501."""

import uuid

from fastapi import APIRouter, Path

from app.api.deps import GenerationServiceDep
from app.schemas.generation import (
    ErrorResponse,
    GenerationJob,
    GenerationMode,
    GenerationRequest,
    ValidationResponse,
)

router = APIRouter(prefix="/generations", tags=["generations"])

_validation_error = {422: {"model": ErrorResponse, "description": "Invalid generation settings"}}


@router.post(
    "/validate",
    response_model=ValidationResponse,
    responses=_validation_error,
    summary="Validate and normalize a request without generating anything",
)
def validate_generation(request: GenerationRequest, service: GenerationServiceDep) -> ValidationResponse:
    return ValidationResponse(
        settings=service.normalize(request),
        generation_available=request.mode == GenerationMode.TEXT_TO_IMAGE and service.available,
    )


@router.post(
    "",
    status_code=202,
    response_model=GenerationJob,
    responses={
        **_validation_error,
        429: {"model": ErrorResponse, "description": "Generation queue is full"},
        501: {"model": ErrorResponse, "description": "Mode not available yet (video), or generation disabled"},
        503: {"model": ErrorResponse, "description": "Model libraries or weights are missing"},
    },
    summary="Queue a text-to-image generation",
)
def create_generation(request: GenerationRequest, service: GenerationServiceDep) -> GenerationJob:
    # Returns immediately with status "queued"; poll GET /generations/{id} for progress.
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
