"""Delivery of generated images. Only server-named PNGs in the output directory are served."""

from fastapi import APIRouter, Path, Query
from fastapi.responses import FileResponse

from app.api.deps import ImageStoreDep
from app.core.errors import AppError
from app.schemas.generation import ErrorResponse
from app.services.image_store import FILENAME_PATTERN

router = APIRouter(prefix="/files", tags=["files"])


@router.get(
    "/images/{filename}",
    response_class=FileResponse,
    responses={
        200: {"content": {"image/png": {}}, "description": "The generated PNG"},
        404: {"model": ErrorResponse, "description": "No such image"},
    },
    summary="Download a generated image",
)
def get_image(
    images: ImageStoreDep,
    filename: str = Path(pattern=FILENAME_PATTERN, description="Image file name returned in output_url."),
    download: bool = Query(False, description="Send as an attachment instead of inline."),
) -> FileResponse:
    path = images.resolve(filename)
    if path is None:
        raise AppError(status_code=404, code="image_not_found", message="No generated image exists with this name.")
    return FileResponse(
        path,
        media_type="image/png",
        filename=f"ai-studio-{filename}" if download else None,
        content_disposition_type="attachment" if download else "inline",
        headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "private, max-age=86400, immutable"},
    )
