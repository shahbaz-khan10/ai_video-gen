"""Generation jobs.

Routes only talk to :class:`GenerationService`. Inference runs on a small thread
pool, never on the event loop.
Jobs live in memory and are lost when the backend restarts.
"""

from __future__ import annotations

import logging
import math
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
    DURATION_OPTIONS_SECONDS,
    IMAGE_SIZES,
    MAX_SEED,
    GeneratedImage,
    GeneratedVideo,
    GenerationJob,
    GenerationMode,
    GenerationRequest,
    GenerationSettings,
    GenerationStatus,
    ImageToVideoRequest,
    ImageResolution,
    JobError,
    TextToImageRequest,
    TextToVideoRequest,
)
from app.services.image_engine import EngineError, EngineStatus, ImageEngine, ImageParams
from app.services.image_storage import ImageStorage
from app.services.video_engine import VideoEngine, VideoEngineError, VideoParams
from app.services.video_storage import VideoStorage

logger = logging.getLogger(__name__)

FILES_PREFIX = "/api/v1/files/images"
VIDEOS_PREFIX = "/api/v1/files/videos"
MAX_JOBS_IN_MEMORY = 200


def _now() -> datetime:
    return datetime.now(UTC)


class JobStore:
    """Thread-safe in-memory registry. Oldest finished jobs are dropped past MAX_JOBS_IN_MEMORY."""

    def __init__(self) -> None:
        self._jobs: OrderedDict[str, GenerationJob] = OrderedDict()
        self._lock = threading.Lock()

    def add(self, job: GenerationJob) -> None:
        with self._lock:
            self._jobs[job.id] = job
            finished = [j.id for j in self._jobs.values() if j.status in (GenerationStatus.COMPLETED, GenerationStatus.FAILED)]
            for job_id in finished[: max(0, len(self._jobs) - MAX_JOBS_IN_MEMORY)]:
                del self._jobs[job_id]

    def update(self, job_id: str, **changes: object) -> GenerationJob:
        with self._lock:
            if job_id not in self._jobs:
                raise KeyError(job_id)
            job = self._jobs[job_id].model_copy(update=changes)
            self._jobs[job_id] = job
            return job

    def get(self, job_id: str) -> GenerationJob | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.status != GenerationStatus.QUEUED:
                return job
            # Position = unfinished jobs submitted before this one
            ahead = 0
            for other in self._jobs.values():
                if other.id == job_id:
                    break
                if other.status in (GenerationStatus.QUEUED, GenerationStatus.PROCESSING):
                    ahead += 1
            return job.model_copy(update={"queue_position": ahead})

    def active_count(self) -> int:
        with self._lock:
            return sum(j.status in (GenerationStatus.QUEUED, GenerationStatus.PROCESSING) for j in self._jobs.values())


class GenerationService:
    def __init__(self, settings: Settings, engine: ImageEngine | None, video_engine: VideoEngine | None = None, store: JobStore | None = None) -> None:
        self.settings = settings
        self.engine = engine
        self.video_engine = video_engine
        self.store = store or JobStore()
        self.storage = ImageStorage(settings.image_output_dir)
        self.video_storage = VideoStorage(settings.video_output_dir)
        self._executor = ThreadPoolExecutor(
            max_workers=max(settings.image_max_concurrent_jobs, settings.video_max_concurrent_jobs),
            thread_name_prefix="generation",
        )
        self._video_lock = threading.Lock()  # ensure one video job at a time

    def engine_status(self) -> EngineStatus | None:
        return self.engine.status() if self.engine else None

    @property
    def available(self) -> bool:
        if self.engine is None:
            return False
        try:
            self.engine.ensure_can_accept()
        except EngineError:
            return False
        return True

    def normalize(self, request: GenerationRequest) -> GenerationSettings:
        settings = GenerationSettings(
            mode=request.mode,
            prompt=request.prompt,
            prompt_length=len(request.prompt),
            aspect_ratio=request.aspect_ratio,
            style=request.style,
            duration_seconds=None if isinstance(request, TextToImageRequest) else request.duration_seconds,
            source_image=request.source_image if isinstance(request, ImageToVideoRequest) else None,
        )
        if isinstance(request, TextToImageRequest):
            width, height = IMAGE_SIZES[request.resolution][request.aspect_ratio]
            settings = settings.model_copy(
                update={
                    "resolution": request.resolution,
                    "width": width,
                    "height": height,
                    "steps": request.steps,
                    "seed": request.seed,
                }
            )
        elif isinstance(request, (TextToVideoRequest, ImageToVideoRequest)):
            # Use reasonable defaults for LTX-Video - prefer small sizes for 8GB
            width, height = IMAGE_SIZES[ImageResolution.STANDARD][request.aspect_ratio]
            steps = getattr(request, "steps", None) or 30
            if steps > 50:
                raise AppError(422, "validation_error", "Steps too high for video model.")
            num_frames = getattr(request, "num_frames", None) or min(121, max(25, int((request.duration_seconds or 6) * 24)))
            settings = settings.model_copy(
                update={
                    "resolution": ImageResolution.STANDARD,
                    "width": width,
                    "height": height,
                    "steps": steps,
                    "seed": getattr(request, "seed", None),
                    "num_frames": num_frames,
                }
            )
        return settings

    def create(self, request: GenerationRequest) -> GenerationJob:
        if request.mode == GenerationMode.TEXT_TO_IMAGE:
            if self.engine is None:
                raise AppError(501, "engine_not_configured", "AI generation is turned off on this server (IMAGE_ENGINE=none).")
            try:
                self.engine.ensure_can_accept()
            except EngineError as err:
                raise AppError(503, err.code, err.message) from None
            limit = self.settings.image_max_queued_jobs + self.settings.image_max_concurrent_jobs
            if self.store.active_count() >= limit:
                raise AppError(429, "queue_full", "The generation queue is full. Try again in a moment.")
            settings = self.normalize(request)
            if settings.seed is None:
                settings = settings.model_copy(update={"seed": secrets.randbelow(MAX_SEED + 1)})
            job = GenerationJob(
                id=str(uuid.uuid4()),
                status=GenerationStatus.QUEUED,
                settings=settings,
                model_id=self.engine.model_id,
                created_at=_now(),
            )
            self.store.add(job)
            logger.info("job %s queued mode=%s size=%sx%s", job.id, settings.mode, settings.width, settings.height)
            self._executor.submit(self._run_image, job.id)
            return self.store.get(job.id) or job
        elif request.mode == GenerationMode.TEXT_TO_VIDEO:
            if self.video_engine is None:
                raise AppError(501, "engine_not_configured", "Video generation is not available on this server.")
            try:
                self.video_engine.ensure_can_accept()
            except VideoEngineError as err:
                raise AppError(503, err.code, err.message) from None
            limit = self.settings.video_max_queued_jobs + self.settings.video_max_concurrent_jobs
            if self.store.active_count() >= limit:
                raise AppError(429, "queue_full", "The generation queue is full. Try again in a moment.")
            settings = self.normalize(request)
            if settings.seed is None:
                settings = settings.model_copy(update={"seed": secrets.randbelow(MAX_SEED + 1)})
            job = GenerationJob(
                id=str(uuid.uuid4()),
                status=GenerationStatus.QUEUED,
                settings=settings,
                model_id=getattr(self.video_engine, "model_id", None),
                created_at=_now(),
            )
            self.store.add(job)
            logger.info("job %s queued mode=%s", job.id, settings.mode)
            self._executor.submit(self._run_video, job.id)
            return self.store.get(job.id) or job
        elif request.mode == GenerationMode.IMAGE_TO_VIDEO:
            raise AppError(501, "mode_not_available", "Image-to-video is not available in this phase.")
        else:
            raise AppError(501, "mode_not_available", "This mode is not available.")

    def get(self, job_id: str) -> GenerationJob:
        job = self.store.get(job_id)
        if job is None:
            raise AppError(404, "generation_not_found", "No generation exists with this ID.")
        return job

    def preload(self) -> None:
        if self.engine is None:
            raise AppError(501, "engine_not_configured", "AI generation is turned off on this server.")
        try:
            self.engine.ensure_can_accept()
        except EngineError as err:
            raise AppError(503, err.code, err.message) from None
        self._executor.submit(self._safe_load)

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)

    def _safe_load(self) -> None:
        try:
            if self.engine:
                self.engine.load()
        except Exception:
            logger.warning("Model preload failed")

    def _run_image(self, job_id: str) -> None:
        job = self.store.update(job_id, status=GenerationStatus.PROCESSING, started_at=_now(), queue_position=None)
        s = job.settings
        assert self.engine is not None and s.width and s.height and s.steps and s.seed is not None
        try:
            image, device = self.engine.generate(
                ImageParams(prompt=s.prompt, style=s.style, width=s.width, height=s.height, steps=s.steps, seed=s.seed),
                deadline=time.monotonic() + self.settings.image_timeout_seconds,
            )
            self.store.update(job_id, device=device)
            stored = self.storage.save(job_id, image)
            url = f"{FILES_PREFIX}/{stored.filename}"
            self.store.update(
                job_id,
                status=GenerationStatus.COMPLETED,
                finished_at=_now(),
                image=GeneratedImage(
                    url=url,
                    download_url=f"{url}?download=true",
                    width=stored.width,
                    height=stored.height,
                    size_bytes=stored.size_bytes,
                ),
                output_url=url,
            )
            logger.info("job %s completed on %s", job_id, device)
        except EngineError as err:
            logger.warning("job %s failed: %s", job_id, err.code)
            self._fail(job_id, JobError(code=err.code, message=err.message, retryable=err.retryable))
        except Exception:
            logger.exception("job %s failed unexpectedly", job_id)
            self._fail(
                job_id,
                JobError(code="generation_failed", message="Image generation failed on the server.", retryable=True),
            )

    def _run_video(self, job_id: str) -> None:
        with self._video_lock:
            job = self.store.update(job_id, status=GenerationStatus.PROCESSING, started_at=_now(), queue_position=None)
            s = job.settings
            if self.video_engine is None or s.width is None or s.height is None or s.steps is None or s.seed is None or s.num_frames is None:
                self._fail(job_id, JobError(code="engine_not_configured", message="Video engine not properly configured.", retryable=False))
                return
            try:
                video_bytes, meta = self.video_engine.generate(
                    VideoParams(prompt=s.prompt, width=s.width, height=s.height, num_frames=s.num_frames, num_inference_steps=s.steps, seed=s.seed),
                    deadline=time.monotonic() + self.settings.video_timeout_seconds,
                )
                self.store.update(job_id, device=self.video_engine._device if hasattr(self.video_engine, "_device") else None)
                stored = self.video_storage.save(job_id, video_bytes)
                url = f"{VIDEOS_PREFIX}/{stored.filename}"
                self.store.update(
                    job_id,
                    status=GenerationStatus.COMPLETED,
                    finished_at=_now(),
                    video=GeneratedVideo(
                        url=url,
                        download_url=f"{url}?download=true",
                        width=stored.width,
                        height=stored.height,
                        size_bytes=stored.size_bytes,
                        num_frames=stored.num_frames,
                        duration_seconds=stored.duration_seconds,
                    ),
                    output_url=url,
                )
                logger.info("video job %s completed", job_id)
            except VideoEngineError as err:
                logger.warning("video job %s failed: %s", job_id, err.code)
                self._fail(job_id, JobError(code=err.code, message=err.message, retryable=err.retryable))
            except Exception:
                logger.exception("video job %s failed unexpectedly", job_id)
                self._fail(
                    job_id,
                    JobError(code="generation_failed", message="Video generation failed on the server.", retryable=True),
                )

    def _fail(self, job_id: str, error: JobError) -> None:
        status = None
        try:
            if self.engine:
                status = self.engine.status()
        except Exception:
            pass
        self.store.update(
            job_id,
            status=GenerationStatus.FAILED,
            finished_at=_now(),
            error=error,
            device=status.device if status else None,
        )
