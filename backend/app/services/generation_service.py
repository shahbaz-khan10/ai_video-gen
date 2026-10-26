"""Generation service.

Routes talk only to :class:`GenerationService`. A real model is added later by
implementing :class:`GenerationEngine` and passing it in; the API layer stays the same.
"""

import logging
from typing import Protocol

from app.core.errors import AppError
from app.schemas.generation import (
    GenerationJob,
    GenerationRequest,
    GenerationSettings,
    ImageToVideoRequest,
    TextToImageRequest,
)

logger = logging.getLogger(__name__)


class GenerationEngine(Protocol):
    """What a model backend must provide."""

    name: str

    @property
    def configured(self) -> bool: ...

    def submit(self, settings: GenerationSettings) -> GenerationJob: ...


class UnconfiguredEngine:
    """Default engine: no model is connected, so every submission is refused."""

    name = "none"

    @property
    def configured(self) -> bool:
        return False

    def submit(self, settings: GenerationSettings) -> GenerationJob:
        raise AppError(
            status_code=501,
            code="engine_not_configured",
            message="AI generation is not connected yet. No media was generated.",
        )


class JobStore:
    """In-memory job registry. Empty until an engine creates real jobs."""

    def __init__(self) -> None:
        self._jobs: dict[str, GenerationJob] = {}

    def add(self, job: GenerationJob) -> None:
        self._jobs[job.id] = job

    def get(self, job_id: str) -> GenerationJob | None:
        return self._jobs.get(job_id)


class GenerationService:
    def __init__(self, engine: GenerationEngine, store: JobStore) -> None:
        self.engine = engine
        self.store = store

    @property
    def available(self) -> bool:
        return self.engine.configured

    def normalize(self, request: GenerationRequest) -> GenerationSettings:
        duration = None if isinstance(request, TextToImageRequest) else request.duration_seconds
        return GenerationSettings(
            mode=request.mode,
            prompt=request.prompt,
            prompt_length=len(request.prompt),
            aspect_ratio=request.aspect_ratio,
            style=request.style,
            duration_seconds=duration,
            source_image=request.source_image if isinstance(request, ImageToVideoRequest) else None,
        )

    def create(self, request: GenerationRequest) -> GenerationJob:
        settings = self.normalize(request)
        # Log shape only; prompts can contain personal content.
        logger.info("generation requested mode=%s prompt_chars=%d", settings.mode, settings.prompt_length)
        job = self.engine.submit(settings)
        self.store.add(job)
        return job

    def get(self, job_id: str) -> GenerationJob:
        job = self.store.get(job_id)
        if job is None:
            raise AppError(status_code=404, code="generation_not_found", message="No generation exists with this ID.")
        return job
