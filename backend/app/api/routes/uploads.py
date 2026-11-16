"""Source image uploads for image-to-video.

The body is the raw image file (``Content-Type: image/jpeg|png|webp``), not multipart form data, so no extra
form-parsing dependency is needed. The bytes are decoded and checked whatever the declared type says.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from app.api.deps import GenerationServiceDep
from app.core.errors import AppError
from app.schemas.generation import ErrorResponse
from app.services.upload_storage import MAX_SIDE, MIN_SIDE, UploadError

router = APIRouter(prefix="/uploads", tags=["uploads"])


class UploadedImage(BaseModel):
    upload_id: str
    width: int
    height: int
    content_type: str
    size_bytes: int


@router.post(
    "/images",
    status_code=201,
    response_model=UploadedImage,
    responses={
        413: {"model": ErrorResponse, "description": "Larger than 10 MB"},
        415: {"model": ErrorResponse, "description": "Not a JPG, PNG or WebP image"},
        422: {"model": ErrorResponse, "description": f"Corrupted, or a side outside {MIN_SIDE}-{MAX_SIDE} px"},
    },
    summary="Upload the image to animate; send the raw file as the body",
)
async def upload_image(request: Request, service: GenerationServiceDep) -> UploadedImage:
    data = await request.body()
    try:
        stored = await run_in_threadpool(service.uploads.save, data)
    except UploadError as err:
        raise AppError(err.status, err.code, err.message) from None
    return UploadedImage(
        upload_id=stored.id,
        width=stored.width,
        height=stored.height,
        content_type=stored.original_type,
        size_bytes=len(data),
    )
