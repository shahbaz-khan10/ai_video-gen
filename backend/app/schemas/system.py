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


class ReadinessResponse(BaseModel):
    ready: bool = Field(description="Whether the API itself can serve requests.")
    checks: dict[str, ReadinessCheck]


class Limits(BaseModel):
    prompt_max_chars: int
    duration_options_seconds: list[int]
    source_image_max_bytes: int
    source_image_types: list[str]
    max_request_bytes: int


class GenerationAvailability(BaseModel):
    available: bool
    engine: str
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
