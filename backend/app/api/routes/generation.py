"""Generation endpoints. Validation works today; creation returns 501 until an engine exists."""

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
    responses={**_validation_error, 501: {"model": ErrorResponse, "description": "No AI engine is connected"}},
    summary="Submit a generation",
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
