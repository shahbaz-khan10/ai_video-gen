"""Generation endpoints. Text-to-image runs on the local model; video modes are not connected yet."""

import uuid

from fastapi import APIRouter, Path

from app.api.deps import GenerationServiceDep
from app.schemas.generation import ErrorResponse, GenerationJob, GenerationRequest, ValidationResponse

router = APIRouter(prefix="/generations", tags=["generations"])

_validation_error = {422: {"model": ErrorResponse, "description": "Invalid generation settings"}}


@router.post(
    "/validate",
    response_model=ValidationResponse,
    responses=_validation_error,
    summary="Validate and normalize a request without generating anything",
)
def validate_generation(request: GenerationRequest, service: GenerationServiceDep) -> ValidationResponse:
    return ValidationResponse(settings=service.normalize(request), generation_available=service.available)


@router.post(
    "",
    status_code=202,
    response_model=GenerationJob,
    responses={
        **_validation_error,
        429: {"model": ErrorResponse, "description": "Too many generations are queued"},
        501: {"model": ErrorResponse, "description": "Mode not supported yet, or no engine configured"},
        503: {"model": ErrorResponse, "description": "Model weights or AI libraries are missing"},
    },
    summary="Queue a text-to-image generation",
    description="Returns immediately with a queued job. Poll `GET /generations/{id}` until it is completed or failed.",
)
def create_generation(request: GenerationRequest, service: GenerationServiceDep) -> GenerationJob:
    return service.create(request)


@router.get(
    "/{generation_id}",
    response_model=GenerationJob,
    responses={404: {"model": ErrorResponse, "description": "Unknown generation"}},
    summary="Get a generation's status",
)
def get_generation(
    service: GenerationServiceDep,
    generation_id: uuid.UUID = Path(description="Generation ID (UUID)."),
) -> GenerationJob:
    return service.get(str(generation_id))
