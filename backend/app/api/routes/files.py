"""Serves generated images. Only ``<uuid>.png`` names from the output directory are reachable."""

from fastapi import APIRouter, Query
from fastapi.responses import FileResponse

from app.api.deps import GenerationServiceDep
from app.core.errors import AppError
from app.schemas.generation import ErrorResponse

router = APIRouter(prefix="/files", tags=["files"])


@router.get(
    "/images/{filename}",
    response_class=FileResponse,
    responses={200: {"content": {"image/png": {}}}, 404: {"model": ErrorResponse}},
    summary="Fetch a generated image",
)
def get_image(
    filename: str,
    service: GenerationServiceDep,
    download: bool = Query(False, description="Send as an attachment instead of inline."),
) -> FileResponse:
    path = service.storage.resolve(filename)
    if path is None:
        # Same response for malformed, traversal and missing names: nothing to probe.
        raise AppError(404, "file_not_found", "No generated image with this name.")
    return FileResponse(
        path,
        media_type="image/png",
        filename=f"ai-video-studio-{filename}" if download else None,
        content_disposition_type="attachment" if download else "inline",
        headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "private, max-age=86400, immutable"},
    )
