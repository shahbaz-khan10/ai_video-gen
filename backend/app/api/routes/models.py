"""Image model status and deliberate preloading."""

from fastapi import APIRouter

from app.api.deps import GenerationServiceDep
from app.api.routes.health import image_model_status
from app.schemas.generation import ErrorResponse
from app.schemas.system import ImageModelStatus

router = APIRouter(prefix="/models", tags=["models"])


@router.get("/image", response_model=ImageModelStatus, summary="Image model status (never loads the model)")
def get_image_model(service: GenerationServiceDep) -> ImageModelStatus:
    return image_model_status(service)


@router.post(
    "/image/load",
    status_code=202,
    response_model=ImageModelStatus,
    responses={503: {"model": ErrorResponse, "description": "Libraries or weights missing"}},
    summary="Start loading the model in the background",
)
def load_image_model(service: GenerationServiceDep) -> ImageModelStatus:
    # Loading can take a while; it runs on the generation worker and is reported via GET /models/image.
    service.preload()
    return image_model_status(service)
