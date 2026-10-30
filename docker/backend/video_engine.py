from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from app.core.config import Settings


class VideoEngineError(Exception):
    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable


@dataclass
class VideoEngineStatus:
    state: str
    detail: str
    model_id: str
    device: str | None = None
    optimizations: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class VideoParams:
    prompt: str
    width: int
    height: int
    num_frames: int
    num_inference_steps: int
    seed: int


class VideoEngine(Protocol):
    name: str
    model_id: str
    _device: str | None

    def status(self) -> VideoEngineStatus: ...

    def ensure_can_accept(self) -> None: ...

    def generate(self, params: VideoParams, deadline: float) -> tuple[bytes, dict[str, object]]: ...


class DisabledVideoEngine:
    name = "none"
    _device = None

    def __init__(self, model_id: str) -> None:
        self.model_id = model_id

    def status(self) -> VideoEngineStatus:
        return VideoEngineStatus(
            "unavailable",
            "Video generation is disabled in this Docker setup.",
            self.model_id,
        )

    def ensure_can_accept(self) -> None:
        raise VideoEngineError(
            "engine_not_configured",
            "Video generation is disabled in this Docker setup.",
        )

    def generate(self, params: VideoParams, deadline: float) -> tuple[bytes, dict[str, object]]:
        self.ensure_can_accept()
        raise AssertionError("unreachable")


def build_video_engine(settings: Settings) -> DisabledVideoEngine:
    return DisabledVideoEngine(settings.video_model_id)
