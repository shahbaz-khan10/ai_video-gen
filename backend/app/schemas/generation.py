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


class ValidationResponse(BaseModel):
    valid: Literal[True] = True
    settings: GenerationSettings
    generation_available: bool = Field(description="Whether an AI engine could run this request now.")


class GenerationStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class GenerationJob(BaseModel):
    """A stored generation job. No jobs exist until an engine is connected."""

    id: str
    status: GenerationStatus
    settings: GenerationSettings
    created_at: datetime
    output_url: str | None = None
    error: str | None = None


class ErrorDetail(BaseModel):
    field: str
    message: str


class ErrorInfo(BaseModel):
    code: str
    message: str
    details: list[ErrorDetail] | dict[str, object] | None = None


class ErrorResponse(BaseModel):
    error: ErrorInfo
