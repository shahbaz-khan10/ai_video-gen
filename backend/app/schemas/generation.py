"""Request and response schemas for the generation API.

Options mirror the Next.js frontend (``src/lib/studio-options.ts``).
"""

from __future__ import annotations

import re
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator

PROMPT_MAX_CHARS = 1000
MAX_SOURCE_IMAGE_BYTES = 10 * 1024 * 1024
DURATION_OPTIONS_SECONDS = (4, 6, 8)
DEFAULT_DURATION_SECONDS = 6
MAX_SEED = 2**32 - 1
IMAGE_STEP_OPTIONS = (1, 2, 4)

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
    PHOTOREALISTIC = "photorealistic"
    PORTRAIT = "portrait"
    GROUP_PHOTO = "group-photo"
    STREET = "street"


DurationSeconds = Literal[4, 6, 8]
# Values the UI may send; the engine clamps them to what the chosen model supports.
ImageSteps = Literal[1, 2, 4, 5, 6, 8, 15, 20, 25, 30, 35]

# --- Text-to-video (Wan2.1 T2V 1.3B) -------------------------------------------------
# Wan generates 4k+1 frames, up to 81 (about 5 s at its native 16 fps). Longer clips are not supported.
VIDEO_DURATION_OPTIONS_SECONDS = (2, 3, 5)
DEFAULT_VIDEO_DURATION_SECONDS = 2
VideoDurationSeconds = Literal[2, 3, 5]
VIDEO_MAX_FRAMES = 81
VIDEO_STEP_OPTIONS = (15, 25, 40)
VIDEO_MIN_STEPS, VIDEO_MAX_STEPS = 10, 50


def video_frames_for(duration_seconds: int, fps: int) -> int:
    """Smallest valid Wan frame count (4k+1) covering the duration, capped at VIDEO_MAX_FRAMES."""
    frames = duration_seconds * fps + 1
    frames += (-(frames - 1)) % 4
    return min(frames, VIDEO_MAX_FRAMES)


class ImageResolution(StrEnum):
    """Size tiers. Exact pixels come from IMAGE_SIZES, never from the client."""

    STANDARD = "standard"
    LARGE = "large"
    HIGH = "high"


# All sides are multiples of 8, as Stable Diffusion's latent space requires.
IMAGE_SIZES: dict[ImageResolution, dict[AspectRatio, tuple[int, int]]] = {
    ImageResolution.STANDARD: {
        AspectRatio.SQUARE: (512, 512),
        AspectRatio.LANDSCAPE: (680, 384),
        AspectRatio.PORTRAIT: (384, 680),
    },
    ImageResolution.LARGE: {
        AspectRatio.SQUARE: (768, 768),
        AspectRatio.LANDSCAPE: (1024, 576),
        AspectRatio.PORTRAIT: (576, 1024),
    },
    # 1344x768 / 768x1344 are SDXL native buckets; 1024x576 left SDXL models below their trained size.
    ImageResolution.HIGH: {
        AspectRatio.SQUARE: (1024, 1024),
        AspectRatio.LANDSCAPE: (1344, 768),
        AspectRatio.PORTRAIT: (768, 1344),
    },
}


# Wan2.1 sizes: multiples of 16 (VAE x8, transformer patch x2). 832x480 is the 1.3B model's trained 480p
# size; "standard" is a smaller, much faster draft. 720p ("high") is unstable on the 1.3B model.
VIDEO_SIZES: dict[ImageResolution, dict[AspectRatio, tuple[int, int]]] = {
    ImageResolution.STANDARD: {
        AspectRatio.SQUARE: (416, 416),
        AspectRatio.LANDSCAPE: (576, 320),
        AspectRatio.PORTRAIT: (320, 576),
    },
    ImageResolution.LARGE: {
        AspectRatio.SQUARE: (624, 624),
        AspectRatio.LANDSCAPE: (832, 480),
        AspectRatio.PORTRAIT: (480, 832),
    },
}


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SourceImageInfo(StrictModel):
    """Metadata about the image the user picked."""

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
        if not value:
            raise ValueError("Prompt is empty. Describe what you want to create.")
        return value


class TextToImageRequest(_GenerationBase):
    mode: Literal[GenerationMode.TEXT_TO_IMAGE]
    resolution: ImageResolution = ImageResolution.STANDARD
    steps: ImageSteps = Field(1, description="Denoising steps. Offered values for the current model are listed in /info (image_steps).")
    seed: int | None = Field(None, ge=0, le=MAX_SEED, description="Omit for a random seed.")
    negative_prompt: str | None = Field(None, max_length=2000, description="Negative prompt instructions.")
    guidance_scale: float | None = Field(None, ge=0.0, le=20.0, description="CFG scale.")
    model_id: str | None = Field(None, description="Optional model ID override.")


class TextToVideoRequest(_GenerationBase):
    mode: Literal[GenerationMode.TEXT_TO_VIDEO]
    duration_seconds: VideoDurationSeconds = Field(
        DEFAULT_VIDEO_DURATION_SECONDS, description="Clip length. The model generates at most 81 frames (~5 s)."
    )
    resolution: Literal[ImageResolution.STANDARD, ImageResolution.LARGE] = Field(
        ImageResolution.STANDARD, description="standard ≈ 320p draft, large = 480p. 720p is not supported."
    )
    steps: int | None = Field(
        None, ge=VIDEO_MIN_STEPS, le=VIDEO_MAX_STEPS, description="Denoising steps; omit for the server default."
    )
    seed: int | None = Field(None, ge=0, le=MAX_SEED, description="Omit for a random seed.")
    num_frames: int | None = Field(
        None, ge=5, le=VIDEO_MAX_FRAMES, description="Optional explicit frame count; must be 4k+1 (e.g. 33, 49, 81)."
    )

    @field_validator("num_frames")
    @classmethod
    def _wan_frame_count(cls, value: int | None) -> int | None:
        if value is not None and (value - 1) % 4 != 0:
            raise ValueError("Frame count must be one more than a multiple of 4 (e.g. 33, 49, 81).")
        return value


class ImageToVideoRequest(_GenerationBase):
    mode: Literal[GenerationMode.IMAGE_TO_VIDEO]
    duration_seconds: DurationSeconds = DEFAULT_DURATION_SECONDS
    resolution: ImageResolution = ImageResolution.STANDARD
    steps: int | None = Field(None, ge=1, le=50)
    seed: int | None = Field(None, ge=0, le=MAX_SEED)
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
    # Image/video settings
    resolution: ImageResolution | None = None
    width: int | None = None
    height: int | None = None
    steps: int | None = None
    seed: int | None = Field(None, description="Null until the server picks one for a random-seed job.")
    num_frames: int | None = None
    fps: int | None = Field(None, description="Frames per second of the generated video.")
    negative_prompt: str | None = None
    guidance_scale: float | None = None
    model_id: str | None = None


class GeneratedVideo(BaseModel):
    """A real video file written by the engine."""

    url: str = Field(description="Path on this API, e.g. /api/v1/files/videos/<id>.mp4")
    download_url: str
    content_type: Literal["video/mp4"] = "video/mp4"
    width: int
    height: int
    size_bytes: int
    num_frames: int | None = None
    duration_seconds: float | None = None


class ValidationResponse(BaseModel):
    valid: Literal[True] = True
    settings: GenerationSettings
    generation_available: bool = Field(description="Whether an AI engine could run this request now.")
    scene_plan: dict[str, Any] | None = None


class GenerationStatus(StrEnum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class GeneratedImage(BaseModel):
    """A real image file written by the engine. Only present once it exists on disk."""

    url: str = Field(description="Path on this API, e.g. /api/v1/files/images/<id>.png")
    download_url: str
    content_type: Literal["image/png"] = "image/png"
    width: int
    height: int
    size_bytes: int


class JobError(BaseModel):
    code: str
    message: str
    retryable: bool


class GenerationJob(BaseModel):
    """A generation job. Jobs live in memory and do not survive a backend restart."""

    id: str
    status: GenerationStatus
    settings: GenerationSettings
    model_id: str | None = None
    device: str | None = Field(None, description="Device the model ran on, once known.")
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    queue_position: int | None = Field(None, description="Jobs ahead of this one while queued.")
    image: GeneratedImage | None = None
    video: GeneratedVideo | None = None
    error: JobError | None = None
    output_url: str | None = None


class ErrorDetail(BaseModel):
    field: str
    message: str


class ErrorInfo(BaseModel):
    code: str
    message: str
    details: list[ErrorDetail] | dict[str, object] | None = None


class ErrorResponse(BaseModel):
    error: ErrorInfo
