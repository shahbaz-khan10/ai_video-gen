"""Request and response schemas for the generation API.

Options mirror the Next.js frontend (``src/lib/studio-options.ts``).
"""

import re
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator

PROMPT_MAX_CHARS = 1000
MAX_SOURCE_IMAGE_BYTES = 10 * 1024 * 1024
DURATION_OPTIONS_SECONDS = (4, 6, 8)
DEFAULT_DURATION_SECONDS = 6
SEED_MAX = 2**32 - 1
# Upper bound accepted by the schema; the engine's own limit (IMAGE_MAX_STEPS) is checked by the service.
STEPS_SCHEMA_MAX = 50

# Control characters other than tab/newline have no place in a prompt.
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_WHITESPACE_RUN = re.compile(r"[ \t]+")


class GenerationMode(StrEnum):
    TEXT_TO_IMAGE = "text-to-image"
    TEXT_TO_VIDEO = "text-to-video"
    IMAGE_TO_VIDEO = "image-to-video"


class AspectRatio(StrEnum):
    LANDSCAPE = "16:9"
    PORTRAIT = "9:16"
    SQUARE = "1:1"


class VisualStyle(StrEnum):
    CINEMATIC = "cinematic"
    DREAMLIKE = "dreamlike"
    NEON_NOIR = "neon-noir"
    DOCUMENTARY = "documentary"
    ANIME = "anime"
    GOLDEN_HOUR = "golden-hour"


DurationSeconds = Literal[4, 6, 8]
ImageResolution = Literal[512, 768, 1024]

# Output size per resolution tier and aspect ratio. Every side is a multiple of 8, as the
# UNet/VAE require. 512 suits SD 1.x/2.x and SD-Turbo; 1024 is SDXL's training size (1344x768 is
# one of SDXL's native bucket sizes). Which tiers a model offers is set by IMAGE_RESOLUTIONS.
IMAGE_SIZES: dict[int, dict[AspectRatio, tuple[int, int]]] = {
    512: {AspectRatio.SQUARE: (512, 512), AspectRatio.LANDSCAPE: (688, 384), AspectRatio.PORTRAIT: (384, 688)},
    768: {AspectRatio.SQUARE: (768, 768), AspectRatio.LANDSCAPE: (1024, 576), AspectRatio.PORTRAIT: (576, 1024)},
    1024: {AspectRatio.SQUARE: (1024, 1024), AspectRatio.LANDSCAPE: (1344, 768), AspectRatio.PORTRAIT: (768, 1344)},
}


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SourceImageInfo(StrictModel):
    """Metadata about the image the user picked. Image bytes are not uploaded in this phase,
    and no file names or paths are accepted."""

    content_type: Literal["image/png", "image/jpeg", "image/webp"]
    size_bytes: int = Field(gt=0, le=MAX_SOURCE_IMAGE_BYTES)


class _GenerationBase(StrictModel):
    prompt: str = Field(max_length=PROMPT_MAX_CHARS, json_schema_extra={"minLength": 1})
    aspect_ratio: AspectRatio = AspectRatio.LANDSCAPE
    style: VisualStyle = VisualStyle.CINEMATIC

    @field_validator("prompt", mode="before")
    @classmethod
    def _normalize_prompt(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        cleaned = _CONTROL_CHARS.sub("", value.replace("\r\n", "\n"))
        lines = [_WHITESPACE_RUN.sub(" ", line).strip() for line in cleaned.split("\n")]
        return "\n".join(lines).strip()

    @field_validator("prompt")
    @classmethod
    def _require_prompt(cls, value: str) -> str:
        # Checked after normalization, so whitespace- or control-only prompts are rejected too.
        if not value:
            raise ValueError("Prompt is empty. Describe what you want to create.")
        return value


class TextToImageRequest(_GenerationBase):
    mode: Literal[GenerationMode.TEXT_TO_IMAGE]
    resolution: ImageResolution | None = Field(
        None,
        description="Size tier; the exact width and height follow from the aspect ratio. "
        "Omit for the model's default. Allowed tiers are listed in /info.",
    )
    num_inference_steps: int | None = Field(
        None, ge=1, le=STEPS_SCHEMA_MAX, description="Omit for the model's default (see /info)."
    )
    seed: int | None = Field(None, ge=0, le=SEED_MAX, description="Omit for a random seed. The seed used is returned.")


class TextToVideoRequest(_GenerationBase):
    mode: Literal[GenerationMode.TEXT_TO_VIDEO]
    duration_seconds: DurationSeconds = DEFAULT_DURATION_SECONDS


class ImageToVideoRequest(_GenerationBase):
    mode: Literal[GenerationMode.IMAGE_TO_VIDEO]
    duration_seconds: DurationSeconds = DEFAULT_DURATION_SECONDS
    source_image: SourceImageInfo


GenerationRequest = Annotated[
    Union[TextToImageRequest, TextToVideoRequest, ImageToVideoRequest],
    Field(discriminator="mode"),
]


class GenerationSettings(BaseModel):
    """Normalized settings, as the engine would receive them."""

    mode: GenerationMode
    prompt: str
    prompt_length: int
    aspect_ratio: AspectRatio
    style: VisualStyle
    duration_seconds: int | None = Field(description="Null for still images.")
    source_image: SourceImageInfo | None = None
    # Still-image settings; null for video modes.
    width: int | None = None
    height: int | None = None
    num_inference_steps: int | None = None
    seed: int | None = None


class ValidationResponse(BaseModel):
    valid: Literal[True] = True
    settings: GenerationSettings
    generation_available: bool = Field(description="Whether an AI engine could run this request now.")


class GenerationStatus(StrEnum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class GenerationResult(BaseModel):
    """Metadata about an image that was actually generated and saved."""

    width: int
    height: int
    seed: int
    num_inference_steps: int
    model_id: str
    device: str
    duration_seconds: float = Field(description="Wall-clock inference time, including any model loading.")


class GenerationJob(BaseModel):
    """A generation job. Jobs live in memory and do not survive a backend restart."""

    id: str
    status: GenerationStatus
    settings: GenerationSettings
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    output_url: str | None = Field(None, description="Set only once the image exists on disk.")
    result: GenerationResult | None = None
    error: str | None = None
    error_code: str | None = None


class ErrorDetail(BaseModel):
    field: str
    message: str


class ErrorInfo(BaseModel):
    code: str
    message: str
    details: list[ErrorDetail] | dict[str, object] | None = None


class ErrorResponse(BaseModel):
    error: ErrorInfo
