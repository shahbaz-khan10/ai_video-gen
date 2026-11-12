"""Schemas for health, readiness, application info and model status."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.generation import AspectRatio, GenerationMode, ImageResolution, VisualStyle


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: str
    version: str
    timestamp: datetime


CheckStatus = Literal["ok", "not_configured", "unavailable", "not_downloaded", "not_loaded", "loading", "error"]


class ReadinessCheck(BaseModel):
    status: CheckStatus
    detail: str


class ReadinessResponse(BaseModel):
    ready: bool = Field(description="Whether the API itself can serve requests. Model readiness is reported separately.")
    model_ready: bool = Field(description="Whether the image model is loaded in memory right now.")
    checks: dict[str, ReadinessCheck]


ModelState = Literal["disabled", "unavailable", "not_downloaded", "not_loaded", "loading", "loaded", "error"]


class ImageModelStatus(BaseModel):
    engine: str
    model_id: str | None
    state: ModelState
    detail: str
    device: str | None = Field(None, description="Known once the model has loaded.")
    optimizations: list[str] = []
    can_generate: bool = Field(description="Libraries and weights are present, so jobs are accepted.")


class ImageSizeOption(BaseModel):
    resolution: ImageResolution
    aspect_ratio: AspectRatio
    width: int
    height: int


class Limits(BaseModel):
    prompt_max_chars: int
    duration_options_seconds: list[int]
    source_image_max_bytes: int
    source_image_types: list[str]
    max_request_bytes: int
    image_sizes: list[ImageSizeOption]
    image_steps: list[int]
    max_seed: int
    # Text-to-video (the video model's real limits; anything else is rejected).
    video_duration_options_seconds: list[int]
    video_sizes: list[ImageSizeOption]
    video_steps: list[int]
    video_max_frames: int
    video_fps: int


class ModelLicense(BaseModel):
    name: str
    url: str
    attribution: str


class GenerationAvailability(BaseModel):
    available: bool = Field(description="True when text-to-image jobs are accepted right now.")
    modes_available: list[GenerationMode]
    engine: str
    model_id: str | None
    license: ModelLicense | None
    message: str


class VideoAvailability(BaseModel):
    available: bool = Field(description="True when text-to-video jobs are accepted right now.")
    engine: str
    model_id: str | None
    state: str = Field(description="disabled, unavailable, not_downloaded, not_loaded, loading, loaded or error.")
    detail: str
    device: str | None = None
    license: ModelLicense | None
    message: str


class InfoResponse(BaseModel):
    name: str
    version: str
    api_version: Literal["v1"] = "v1"
    environment: str
    modes: list[GenerationMode]
    aspect_ratios: list[AspectRatio]
    styles: list[VisualStyle]
    limits: Limits
    generation: GenerationAvailability
    video: VideoAvailability
