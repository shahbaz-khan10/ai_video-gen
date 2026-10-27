"""Schemas for health, readiness and application info."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.generation import AspectRatio, GenerationMode, VisualStyle


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: str
    version: str
    timestamp: datetime


CheckStatus = Literal["ok", "not_configured", "error"]


class ReadinessCheck(BaseModel):
    status: CheckStatus
    detail: str


ModelState = Literal["disabled", "not_installed", "weights_missing", "not_loaded", "loading", "ready", "error"]


class ModelReadiness(BaseModel):
    """State of the image model. Reported without loading it."""

    state: ModelState
    loaded: bool = Field(description="Whether the model is in memory right now.")
    accepts_jobs: bool = Field(description="Whether a text-to-image request would be queued.")
    model_id: str | None
    device: str | None = Field(description="'cuda' or 'cpu' once known.")
    cuda_available: bool | None = Field(description="Whether PyTorch can access a CUDA GPU. Null if PyTorch is missing.")
    detail: str


class ReadinessResponse(BaseModel):
    ready: bool = Field(description="Whether the API itself can serve requests. Independent of the model.")
    checks: dict[str, ReadinessCheck]
    model: ModelReadiness


class Limits(BaseModel):
    prompt_max_chars: int
    duration_options_seconds: list[int]
    source_image_max_bytes: int
    source_image_types: list[str]
    max_request_bytes: int
    image_resolutions: list[int] = Field(description="Size tiers this model offers.")
    image_default_resolution: int
    image_max_steps: int
    image_step_presets: list[int] = Field(description="Step counts offered as Fast / Balanced / Detailed.")
    image_default_steps: int
    seed_max: int


class GenerationAvailability(BaseModel):
    available: bool
    engine: str
    model_id: str | None = None
    available_modes: list[GenerationMode] = Field(description="Modes that can be generated right now.")
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
