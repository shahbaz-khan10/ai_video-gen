"""Generation service.

Routes talk only to :class:`GenerationService`. It validates what the engine can run,
records jobs in memory, and runs inference on a small thread pool so GPU work never
blocks the event loop.

Jobs are kept in memory only: they are lost when the backend restarts. Images already
written to the output directory stay on disk.
"""

import logging
import secrets
import threading
import time
import uuid
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

from app.core.config import Settings
from app.core.errors import AppError
from app.schemas.generation import (
    IMAGE_SIZES,
    SEED_MAX,
    GenerationJob,
    GenerationMode,
    GenerationRequest,
    GenerationResult,
    GenerationSettings,
    GenerationStatus,
    ImageToVideoRequest,
    TextToImageRequest,
    VisualStyle,
)
from app.services.image_engine import EngineError, ImageEngine, ImageParams
from app.services.image_store import ImageSaveError, ImageStore

logger = logging.getLogger(__name__)

# Finished jobs beyond this count are forgotten (oldest first) so memory stays bounded.
MAX_RETAINED_JOBS = 200

# Short style cues placed before the prompt, so CLIP's 77-token limit trims the prompt's tail, not the style.
# Every style except anime asks for a photograph, which steers photoreal models away from painted looks.
STYLE_PROMPTS: dict[VisualStyle, str] = {
    VisualStyle.CINEMATIC: "cinematic photo, 35mm film, natural lighting, highly detailed",
    VisualStyle.DREAMLIKE: "dreamy photo, soft bloom, pastel haze",
    VisualStyle.NEON_NOIR: "night photo, neon lights, wet streets, deep shadows",
    VisualStyle.DOCUMENTARY: "RAW photo, documentary photography, natural light, realistic skin, highly detailed",
    VisualStyle.ANIME: "anime illustration, clean linework, vibrant colour",
    VisualStyle.GOLDEN_HOUR: "photo at golden hour, warm low sun, long shadows, highly detailed",
}

# The default negative prompt rejects drawings and anime, which would fight the anime style.
_STYLES_WITHOUT_NEGATIVE = {VisualStyle.ANIME}

_MODE_LABELS = {GenerationMode.TEXT_TO_VIDEO: "Text-to-video", GenerationMode.IMAGE_TO_VIDEO: "Image-to-video"}

_TERMINAL = (GenerationStatus.COMPLETED, GenerationStatus.FAILED)


def _invalid(field: str, message: str) -> AppError:
    return AppError(
        status_code=422,
        code="validation_error",
        message="The request is invalid.",
        details=[{"field": field, "message": message}],
    )


class JobStore:
    """Thread-safe in-memory job registry."""

    def __init__(self, max_jobs: int = MAX_RETAINED_JOBS) -> None:
        self._jobs: OrderedDict[str, GenerationJob] = OrderedDict()
        self._lock = threading.Lock()
        self._max_jobs = max_jobs

    def add(self, job: GenerationJob) -> None:
        with self._lock:
            self._jobs[job.id] = job
            excess = len(self._jobs) - self._max_jobs
            for job_id in [k for k, v in self._jobs.items() if v.status in _TERMINAL][: max(excess, 0)]:
                del self._jobs[job_id]

    def get(self, job_id: str) -> GenerationJob | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return job.model_copy(deep=True) if job else None

    def update(self, job_id: str, **changes: object) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is not None:
                self._jobs[job_id] = job.model_copy(update=changes)

    def active_count(self) -> int:
        with self._lock:
            return sum(1 for job in self._jobs.values() if job.status not in _TERMINAL)


class GenerationService:
    def __init__(self, engine: ImageEngine, store: JobStore, images: ImageStore, settings: Settings) -> None:
        self.engine = engine
        self.store = store
        self.images = images
        self.settings = settings
        self._executor = ThreadPoolExecutor(
            max_workers=settings.image_max_concurrent_jobs, thread_name_prefix="image-gen"
        )
        self._submit_lock = threading.Lock()

    @property
    def available(self) -> bool:
        return self.engine.status().accepts_jobs

    def normalize(self, request: GenerationRequest) -> GenerationSettings:
        image_fields: dict[str, int | None] = {}
        if isinstance(request, TextToImageRequest):
            resolution = request.resolution or self.settings.image_default_resolution
            if resolution not in self.settings.image_resolutions:
                allowed = ", ".join(str(r) for r in self.settings.image_resolutions)
                raise _invalid("resolution", f"This model supports these resolutions: {allowed}.")
            steps = request.num_inference_steps or self.settings.image_default_steps
            if steps > self.settings.image_max_steps:
                raise _invalid("num_inference_steps", f"This model allows at most {self.settings.image_max_steps} steps.")
            width, height = IMAGE_SIZES[resolution][request.aspect_ratio]
            image_fields = {"width": width, "height": height, "num_inference_steps": steps, "seed": request.seed}
        return GenerationSettings(
            mode=request.mode,
            prompt=request.prompt,
            prompt_length=len(request.prompt),
            aspect_ratio=request.aspect_ratio,
            style=request.style,
            duration_seconds=None if isinstance(request, TextToImageRequest) else request.duration_seconds,
            source_image=request.source_image if isinstance(request, ImageToVideoRequest) else None,
            **image_fields,
        )

    def create(self, request: GenerationRequest) -> GenerationJob:
        settings = self.normalize(request)
        # Log shape only; prompts can contain personal content.
        logger.info("generation requested mode=%s prompt_chars=%d", settings.mode, settings.prompt_length)

        if settings.mode != GenerationMode.TEXT_TO_IMAGE:
            raise AppError(
                status_code=501,
                code="mode_not_supported",
                message=f"{_MODE_LABELS[settings.mode]} is not available yet. Only text-to-image is connected.",
            )
        self._check_engine()
        if settings.seed is None:
            # Record the seed actually used, so the result can be reproduced.
            settings = settings.model_copy(update={"seed": secrets.randbelow(SEED_MAX + 1)})

        with self._submit_lock:
            if self.store.active_count() >= self.settings.image_max_queued_jobs:
                raise AppError(
                    status_code=429,
                    code="queue_full",
                    message="Too many generations are waiting. Try again when the current ones finish.",
                )
            job = GenerationJob(
                id=str(uuid.uuid4()), status=GenerationStatus.QUEUED, settings=settings, created_at=datetime.now(UTC)
            )
            self.store.add(job)
        self._executor.submit(self._run, job.id, settings)
        return job

    def _check_engine(self) -> None:
        status = self.engine.status()
        if status.accepts_jobs:
            return
        if status.state == "weights_missing":
            raise AppError(
                status_code=503,
                code="model_not_downloaded",
                message="The image model's weights are not downloaded yet. Ask the server admin to run "
                "scripts/download_model.py.",
            )
        if status.state == "not_installed":
            raise AppError(
                status_code=503,
                code="engine_not_installed",
                message="The AI image libraries (PyTorch, Diffusers) are not installed on the server.",
            )
        raise AppError(
            status_code=501,
            code="engine_not_configured",
            message="AI generation is not connected. No image was generated.",
        )

    def _run(self, job_id: str, settings: GenerationSettings) -> None:
        assert settings.width and settings.height and settings.num_inference_steps and settings.seed is not None
        started = time.monotonic()
        self.store.update(job_id, status=GenerationStatus.PROCESSING, started_at=datetime.now(UTC))
        style = STYLE_PROMPTS.get(settings.style)
        params = ImageParams(
            prompt=f"{style}, {settings.prompt}" if style else settings.prompt,
            width=settings.width,
            height=settings.height,
            num_inference_steps=settings.num_inference_steps,
            seed=settings.seed,
            negative_prompt=None
            if settings.style in _STYLES_WITHOUT_NEGATIVE
            else (self.settings.image_negative_prompt or None),
        )
        try:
            generated = self.engine.generate(params, deadline=started + self.settings.image_generation_timeout_seconds)
            filename = self.images.save(generated.image, (settings.width, settings.height))
        except EngineError as exc:
            self._fail(job_id, exc.code, exc.message)
            return
        except ImageSaveError as exc:
            logger.error("saving generated image failed job=%s: %s", job_id, exc)
            self._fail(job_id, "image_save_failed", "The image was generated but could not be saved on the server.")
            return
        except Exception:
            logger.exception("generation failed job=%s", job_id)
            self._fail(job_id, "generation_failed", "Image generation failed unexpectedly. Please try again.")
            return

        elapsed = round(time.monotonic() - started, 2)
        self.store.update(
            job_id,
            status=GenerationStatus.COMPLETED,
            completed_at=datetime.now(UTC),
            output_url=self.images.url_for(filename),
            result=GenerationResult(
                width=settings.width,
                height=settings.height,
                seed=settings.seed,
                num_inference_steps=settings.num_inference_steps,
                model_id=generated.model_id,
                device=generated.device,
                duration_seconds=elapsed,
            ),
        )
        logger.info("generation completed job=%s in %.2fs", job_id, elapsed)

    def _fail(self, job_id: str, code: str, message: str) -> None:
        logger.warning("generation failed job=%s code=%s", job_id, code)
        self.store.update(
            job_id, status=GenerationStatus.FAILED, completed_at=datetime.now(UTC), error=message, error_code=code
        )

    def get(self, job_id: str) -> GenerationJob:
        job = self.store.get(job_id)
        if job is None:
            raise AppError(
                status_code=404,
                code="generation_not_found",
                message="No generation exists with this ID. Jobs are kept in memory and are lost when the backend restarts.",
            )
        return job

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)
