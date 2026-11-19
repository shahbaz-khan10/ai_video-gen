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
import os
import time
import uuid
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

from app.core.config import Settings
from app.core.errors import AppError
from app.core.models_registry import get_model_profile, is_known_model
from app.schemas.generation import (
    VIDEO_SIZES,
    IMAGE_SIZES,
    MAX_SEED,
    GeneratedImage,
    GeneratedVideo,
    GenerationJob,
    GenerationMode,
    GenerationRequest,
    GenerationSettings,
    GenerationStatus,
    AgentCheck,
    AgentResult,
    I2V_CAMERA_TEXT,
    I2V_MOTION_TEXT,
    ImageToVideoRequest,
    JobError,
    TextToImageRequest,
    TextToVideoRequest,
    video_frames_for,
    SINGLE_CLIP_MAX_SECONDS,
    SceneJob,
)
from app.schemas.scene_plan import SceneBeat, ScenePlan
from app.services.image_engine import STYLE_PROMPTS, EngineError, EngineStatus, ImageEngine, ImageParams
from app.services.long_video import CROSSFADE_FRAMES, SCENE_CUT_FRAMES, join_clips, plan_clips, scene_durations
from app.services.prompt_compiler import VIDEO_STYLE_PROMPTS, compile_plan
from app.services.prompt_tokens import CLIP_MAX_TOKENS, UMT5_MAX_TOKENS, count_tokens, load_tokenizer
from app.services.image_storage import ImageStorage
from app.services.upload_storage import UploadStorage
from app.services import prompt_agent as agent_mod
from app.services.video_engine import ImageVideoParams, VideoEngine, VideoEngineError, VideoParams
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

    def transition(self, job_id: str, expected: GenerationStatus, **changes: object) -> GenerationJob | None:
        """Applies ``changes`` only if the job is still in ``expected`` status, atomically. Without this a cancel
        could mark a queued job failed just as a worker started it, and the worker would overwrite the cancel."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.status != expected:
                return None
            job = job.model_copy(update=changes)
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
        swept = self.video_storage.sweep_temp()  # no job can be running yet
        if swept:
            logger.info("Removed %d unfinished video file(s) left by a previous run", swept)
        self._executor = ThreadPoolExecutor(
            max_workers=max(settings.image_max_concurrent_jobs, settings.video_max_concurrent_jobs),
            thread_name_prefix="generation",
        )
        self._video_lock = threading.Lock()
        self.uploads = UploadStorage(settings.upload_dir)
        self.agent = agent_mod.PromptAgent(settings)
        # Set to stop a running job at its next denoising step (POST /generations/{id}/cancel).
        self._cancel: dict[str, threading.Event] = {}

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
            prompt_agent=request.prompt_agent,
        )
        if isinstance(request, TextToImageRequest):
            width, height = IMAGE_SIZES[request.resolution][request.aspect_ratio]
            # The server runs one configured model (IMAGE_MODEL_ID). A request's model_id cannot switch it, so
            # the job records the model that actually runs rather than the one the client asked for.
            model_id = getattr(self.engine, "model_id", None)
            # Distilled models (Turbo, Lightning) produce broken images outside their step range, so the
            # effective count is clamped and recorded on the job.
            if model_id and is_known_model(model_id):
                steps = get_model_profile(model_id).clamp_steps(request.steps)
            elif request.steps is not None:
                steps = request.steps
            else:
                steps = get_model_profile(model_id).default_steps if model_id else 25
            settings = settings.model_copy(
                update={
                    "resolution": request.resolution,
                    "width": width,
                    "height": height,
                    "steps": steps,
                    "seed": request.seed,
                    "negative_prompt": request.negative_prompt,
                    "guidance_scale": request.guidance_scale,
                    "model_id": model_id,
                }
            )
        elif isinstance(request, TextToVideoRequest):
            fps = self.settings.video_fps
            width, height = VIDEO_SIZES[request.resolution][request.aspect_ratio]
            fast = getattr(self.video_engine, "sampler", None) == "fastwan"
            if fast and request.steps is not None:
                raise AppError(
                    422, "validation_error", "The request is invalid.",
                    [{"field": "steps", "message": "This server uses the 3-step distilled FastWan model; steps are fixed."}],
                )
            long = request.duration_seconds > SINGLE_CLIP_MAX_SECONDS
            # An explicit frame count wins; otherwise the duration decides (Wan needs 4k+1 frames, max 81).
            num_frames = None if long else request.num_frames or video_frames_for(request.duration_seconds, fps)
            settings = settings.model_copy(
                update={
                    "duration_seconds": request.duration_seconds,
                    "resolution": request.resolution,
                    "width": width,
                    "height": height,
                    "steps": 3 if fast else request.steps or self.settings.video_default_steps,
                    "seed": request.seed,
                    "num_frames": num_frames,
                    "fps": fps,
                    "guidance_scale": None if fast else self.settings.video_guidance_scale,
                    "model_id": getattr(self.video_engine, "model_id", None),
                }
            )
        elif isinstance(request, ImageToVideoRequest):
            from app.services.video_engine import I2V_GUIDANCE, I2V_QUALITY_STEPS

            fps = self.settings.video_fps
            width, height = VIDEO_SIZES[request.resolution][request.aspect_ratio]
            draft = request.quality == "draft"
            settings = settings.model_copy(
                update={
                    "duration_seconds": request.duration_seconds,
                    "resolution": request.resolution,
                    "width": width,
                    "height": height,
                    "steps": 3 if draft else I2V_QUALITY_STEPS,
                    "seed": request.seed,
                    "num_frames": video_frames_for(request.duration_seconds, fps),
                    "fps": fps,
                    "guidance_scale": None if draft else I2V_GUIDANCE,
                    "model_id": self.settings.video_continuity_model_id
                    + (f" + {self.settings.video_fast_model_id} base (3-step)" if draft else ""),
                    "quality": request.quality,
                    "motion": request.motion,
                    "camera": request.camera,
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
                model_id=settings.model_id or getattr(self.engine, "model_id", None),
                plan=self.plan(request),
                created_at=_now(),
            )
            self.store.add(job)
            logger.info("job %s queued mode=%s size=%sx%s steps=%s", job.id, settings.mode, settings.width, settings.height, settings.steps)
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
            plan, scenes = self._plan_video(request, settings)
            job = GenerationJob(
                id=str(uuid.uuid4()),
                status=GenerationStatus.QUEUED,
                settings=settings,
                model_id=getattr(self.video_engine, "model_id", None),
                created_at=_now(),
                plan=plan,
                scenes=scenes,
                clips_total=sum(len(s.clips) for s in scenes) or None,
                clips_completed=0 if scenes else None,
            )
            self.store.add(job)
            logger.info("job %s queued mode=%s scenes=%d", job.id, settings.mode, len(scenes))
            self._executor.submit(self._run_long_video if scenes else self._run_video, job.id)
            return self.store.get(job.id) or job
        elif request.mode == GenerationMode.IMAGE_TO_VIDEO:
            assert isinstance(request, ImageToVideoRequest)
            if self.video_engine is None:
                raise AppError(501, "engine_not_configured", "Video generation is not available on this server.")
            ok, detail = self.video_engine.i2v_status() if hasattr(self.video_engine, "i2v_status") else (False, "")
            if not ok:
                raise AppError(503, "model_not_downloaded", detail or "Image-to-video is not available on this server.")
            if self.uploads.resolve(request.source_image.upload_id) is None:
                raise AppError(
                    422, "validation_error", "The request is invalid.",
                    [{"field": "source_image.upload_id", "message": "The uploaded image was not found or has expired (24 h). Upload it again."}],
                )
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
                model_id=settings.model_id,
                created_at=_now(),
                plan=self._i2v_plan(request),
            )
            self.store.add(job)
            logger.info("job %s queued mode=image-to-video quality=%s", job.id, settings.quality)
            self._executor.submit(self._run_i2v, job.id)
            return self.store.get(job.id) or job
        else:
            raise AppError(501, "mode_not_available", "This mode is not available.")

    # --- image-to-video ------------------------------------------------------------------

    @staticmethod
    def i2v_prompt(request: ImageToVideoRequest) -> str:
        """The movement the user asked for, then motion strength and camera words. Nothing about how the
        picture looks: VACE takes that from the image, and style words would repaint it."""
        parts = [request.prompt.rstrip(". ") + "."]
        parts.append(I2V_MOTION_TEXT[request.motion].capitalize() + ".")
        camera = I2V_CAMERA_TEXT[request.camera]
        if camera:
            parts.append(camera[0].upper() + camera[1:] + ".")
        parts.append("Keep the same people, faces, clothing, objects, background and lighting as in the first frame.")
        return " ".join(parts)

    def _i2v_plan(self, request: ImageToVideoRequest) -> ScenePlan:
        return ScenePlan(
            original_prompt=request.prompt,
            planner="image-to-video",
            model_prompt=self.i2v_prompt(request),
            limitations=[
                "The uploaded image is the first frame; it is centre-cropped to the chosen aspect ratio.",
                "The model invents the frames after the first one: faces can drift a little, fast or large "
                "movements are weak, and nothing outside the frame is known to the model.",
                "Video is silent.",
            ],
        )

    def _run_i2v(self, job_id: str) -> None:
        with self._video_lock:
            cancel = self._cancel.setdefault(job_id, threading.Event())
            job = self.store.transition(
                job_id, GenerationStatus.QUEUED,
                status=GenerationStatus.PROCESSING, started_at=_now(), queue_position=None, error=None,
            )
            if job is None:
                self._cancel.pop(job_id, None)
                return  # cancelled while queued
            s = job.settings
            assert self.video_engine is not None and s.source_image is not None
            assert s.width and s.height and s.seed is not None and s.num_frames and s.fps
            try:
                image_path = self.uploads.resolve(s.source_image.upload_id)
                if image_path is None:
                    raise VideoEngineError("upload_expired", "The uploaded image is gone (uploads are kept 24 h). Upload it again.")
                self._unload(self.engine)
                tmp = self.video_storage.temp_path(job_id)
                prompt = job.plan.model_prompt if job.plan and job.plan.model_prompt else s.prompt
                check = None
                if self._agent_on(job):
                    prompt, check = self._prepare_i2v_agent(job_id, image_path, prompt)

                def make(seed: int, path: Path) -> str:
                    return self.video_engine.generate_from_image(  # type: ignore[attr-defined]
                        ImageVideoParams(
                            prompt=prompt,
                            image_path=image_path,
                            width=s.width,
                            height=s.height,
                            num_frames=s.num_frames,
                            seed=seed,
                            quality=s.quality or "draft",
                            fps=s.fps,
                        ),
                        deadline=time.monotonic() + self.settings.video_timeout_seconds,
                        output_path=path,
                        cancel=cancel,
                    )

                device = self._generate_checked(job_id, s.seed, tmp, make, check)
                self.store.update(job_id, device=device)
                stored = self.video_storage.finalize(job_id, tmp)
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
                logger.info("image-to-video job %s completed", job_id)
            except VideoEngineError as err:
                logger.warning("image-to-video job %s failed: %s", job_id, err.code)
                self.video_storage.discard(job_id)
                self._fail(job_id, JobError(code=err.code, message=err.message, retryable=err.retryable))
            except Exception:
                logger.exception("image-to-video job %s failed unexpectedly", job_id)
                self.video_storage.discard(job_id)
                self._fail(job_id, JobError(code="generation_failed", message="Video generation failed on the server.", retryable=True))
            finally:
                self._cancel.pop(job_id, None)

    # --- prompt agent ----------------------------------------------------------------------

    def _agent_on(self, job: GenerationJob) -> bool:
        return bool(job.settings.prompt_agent) and self.agent.available()

    def _count_checks(self, image, targets: list[tuple[str, int]]) -> list[AgentCheck]:
        checks = []
        for phrase, expected in targets:
            try:
                found = self.agent.count(image, phrase)
            except Exception:
                logger.exception("prompt agent: count failed")
                continue
            checks.append(AgentCheck(name=f"count of {phrase}", expected=str(expected), found=str(found), passed=found == expected))
        return checks

    def _prepare_i2v_agent(self, job_id: str, image_path: Path, prompt: str):
        """Describes the photo into the prompt and returns the checks to run on the video (subject counts and, for a
        plain background, its colour). Agent errors only skip the agent; they never fail the job."""
        from PIL import Image

        try:
            with Image.open(image_path) as src:
                photo = src.convert("RGB")
            description = self.agent.describe(photo)
            subjects = {k: v for k, v in self.agent.subjects(photo).items() if k != "person" or v <= 2}
            r, g, b, spread = agent_mod.border_colour(photo)
        except Exception:
            logger.exception("prompt agent: photo analysis failed")
            self.store.update(job_id, agent=AgentResult(notes=["The prompt agent could not analyse the photo; it was skipped."]))
            return prompt, None
        plain = spread < agent_mod.PLAIN_SPREAD
        extra = f" The scene: {description}" if description else ""
        if plain:
            extra += f" Plain {agent_mod.colour_name((r, g, b))} background that stays the same colour."
        full = prompt + extra
        job = self.store.get(job_id)
        if job and job.plan:
            self.store.update(job_id, plan=job.plan.model_copy(update={"model_prompt": full}))
        notes = [f"Detected in the photo: {', '.join(f'{v} {k}' for k, v in subjects.items()) or 'no people or animals'}."]
        self.store.update(job_id, agent=AgentResult(description=description, notes=notes))
        self.agent.unload()  # the video model needs the VRAM; Florence-2 reloads in ~2 s for the check

        def check(path: Path) -> list[AgentCheck]:
            first, _middle, last = _frames(path)
            checks = []
            for label, expected in subjects.items():
                try:
                    found = self.agent.count(last, label)
                except Exception:
                    logger.exception("prompt agent: count failed")
                    continue
                checks.append(AgentCheck(name=f"{label} at the end", expected=str(expected), found=str(found), passed=found == expected))
            if plain:
                shift = agent_mod.colour_distance(agent_mod.border_colour(first), agent_mod.border_colour(last))
                checks.append(AgentCheck(
                    name="background colour", expected=agent_mod.colour_name((r, g, b)),
                    found=agent_mod.colour_name(agent_mod.border_colour(last)[:3]),
                    passed=shift < agent_mod.BACKGROUND_SHIFT_LIMIT,
                ))
            return checks

        return full, check

    def _generate_checked(self, job_id: str, seed: int, tmp: Path, make, check, retry: bool = True) -> str:
        """Generates once; when the agent's checks fail, generates again with the next seed and keeps the better
        video. Without checks this is a single generation."""
        device = make(seed, tmp)
        if check is None:
            return device
        job = self.store.get(job_id)
        report = (job.agent if job and job.agent else AgentResult()).model_copy(deep=True)
        try:
            checks = check(tmp)
        except Exception:
            logger.exception("prompt agent: video check failed")
            report.notes.append("The result could not be checked.")
            self.store.update(job_id, agent=report)
            self.agent.unload()
            return device
        report.checks = checks
        if checks and not all(c.passed for c in checks) and not retry:
            report.notes.append("A check failed; for text-to-video the agent reports it but does not regenerate.")
        elif checks and not all(c.passed for c in checks):
            first = tmp.with_name(tmp.name.replace(".part.mp4", ".first.part.mp4"))
            os.replace(tmp, first)
            retry_seed = (seed + 1) % (MAX_SEED + 1)
            self.agent.unload()  # free VRAM for the video model
            try:
                device = make(retry_seed, tmp)
                checks2 = check(tmp)
            except Exception:
                os.replace(first, tmp)
                raise
            report.attempts = 2
            if sum(c.passed for c in checks2) > sum(c.passed for c in checks):
                first.unlink(missing_ok=True)
                report.checks = checks2
                job = self.store.get(job_id)
                if job:
                    self.store.update(job_id, settings=job.settings.model_copy(update={"seed": retry_seed}))
                report.notes.append(f"The first video failed a check; the retry (seed {retry_seed}) was better and is shown.")
            else:
                os.replace(first, tmp)
                report.notes.append("The first video failed a check; the retry was not better, so the first is shown.")
        self.store.update(job_id, agent=report)
        self.agent.unload()
        return device

    # --- cancel / retry ------------------------------------------------------------------

    def cancel(self, job_id: str) -> GenerationJob:
        """Queued jobs stop at once; a running job stops at its next denoising step (seconds, not minutes)."""
        job = self.get(job_id)
        if job.status in (GenerationStatus.COMPLETED, GenerationStatus.FAILED):
            raise AppError(409, "not_cancellable", "This generation has already finished.")
        if job.settings.mode == GenerationMode.TEXT_TO_IMAGE and job.status == GenerationStatus.PROCESSING:
            raise AppError(409, "not_cancellable", "An image that is already being generated finishes in seconds.")
        error = JobError(code="cancelled", message="The generation was cancelled.", retryable=True)
        if self.store.transition(job_id, GenerationStatus.QUEUED, status=GenerationStatus.FAILED, finished_at=_now(), error=error):
            return self.get(job_id)
        # Running: the engine checks this before and between denoising steps. Loading the model (up to a minute
        # the first time) cannot be interrupted, so the job stops right after that.
        self._cancel.setdefault(job_id, threading.Event()).set()
        return self.get(job_id)

    def retry(self, job_id: str) -> GenerationJob:
        """Runs a failed or cancelled single-clip job again with the same settings and seed."""
        job = self.get(job_id)
        if job.status != GenerationStatus.FAILED:
            raise AppError(409, "not_retryable", "Only failed or cancelled generations can be retried.")
        if job.scenes:
            raise AppError(409, "not_retryable", "Long videos are retried per scene.")
        if job.error and not job.error.retryable:
            raise AppError(409, "not_retryable", job.error.message)
        if job.settings.mode == GenerationMode.IMAGE_TO_VIDEO:
            assert job.settings.source_image is not None
            if self.uploads.resolve(job.settings.source_image.upload_id) is None:
                raise AppError(409, "upload_expired", "The uploaded image is gone (uploads are kept 24 h). Upload it again.")
        limit = (
            self.settings.image_max_queued_jobs + self.settings.image_max_concurrent_jobs
            if job.settings.mode == GenerationMode.TEXT_TO_IMAGE
            else self.settings.video_max_queued_jobs + self.settings.video_max_concurrent_jobs
        )
        if self.store.active_count() >= limit:
            raise AppError(429, "queue_full", "The generation queue is full. Try again in a moment.")
        self.store.update(job_id, status=GenerationStatus.QUEUED, error=None, finished_at=None, started_at=None, device=None)
        run = {
            GenerationMode.TEXT_TO_IMAGE: self._run_image,
            GenerationMode.TEXT_TO_VIDEO: self._run_video,
            GenerationMode.IMAGE_TO_VIDEO: self._run_i2v,
        }[job.settings.mode]
        self._executor.submit(run, job_id)
        logger.info("job %s retried", job_id)
        return self.store.get(job_id) or job

    def get(self, job_id: str) -> GenerationJob:
        job = self.store.get(job_id)
        if job is None:
            raise AppError(404, "generation_not_found", "No generation exists with this ID.")
        return job

    # --- planning ----------------------------------------------------------------------------

    def plan(self, request: GenerationRequest) -> ScenePlan:
        """The plan a generation would use, without generating. Shown to the user for review and editing."""
        settings = self.normalize(request)
        if isinstance(request, TextToVideoRequest):
            return self._plan_video(request, settings)[0]
        if isinstance(request, ImageToVideoRequest):
            return self._i2v_plan(request)
        return self._compile(request.prompt, mode=str(request.mode.value if hasattr(request.mode, "value") else request.mode),
                             style=settings.style, duration=None, user_scenes=None)

    def _budget(self, target: str) -> tuple[object, int, str, bool]:
        """The real tokenizer and token budget of the model that will read the prompt."""
        if target == "image":
            model_id, cache, budget, name = (
                self.settings.image_model_id, self.settings.image_model_cache_dir, CLIP_MAX_TOKENS - 2, "clip (RealVisXL)",
            )
        else:
            model_id = self.settings.video_model_id  # FastWan uses the base Wan2.1 text encoder and tokenizer
            cache = self.settings.video_model_cache_dir or self.settings.image_model_cache_dir
            budget, name = UMT5_MAX_TOKENS - 1, "umt5 (Wan2.1)"  # -1: the end-of-sequence token
        tokenizer = load_tokenizer(model_id, str(cache))
        if tokenizer is None:
            # Weights not downloaded (generation is unavailable then): a word/punctuation count stands in, and
            # every compiled prompt says it was not measured with the real tokenizer.
            return None, budget, f"{name} (not downloaded: estimated)", False
        return tokenizer, budget, name, True

    def _compile(self, prompt: str, *, mode: str, style: str, duration: float | None, user_scenes) -> ScenePlan:
        tokenizer, budget, name, measured = self._budget("image" if mode == "text-to-image" else "video")
        measure = (lambda t: count_tokens(tokenizer, t)) if tokenizer is not None else _estimate_tokens
        return compile_plan(
            prompt,
            mode=mode,
            # Video prompts use motion wording; "film still"/"photograph" kept people static (docs/motion).
            style_text=(VIDEO_STYLE_PROMPTS.get(str(style)) if mode != "text-to-image" else None) or STYLE_PROMPTS.get(style),
            style_name=style,
            duration_seconds=duration,
            user_scenes=user_scenes,
            measure=measure,
            budget=budget,
            tokenizer_name=name,
            measured=measured,
        )

    def _plan_video(self, request: TextToVideoRequest, settings) -> tuple[ScenePlan, list[SceneJob]]:
        if request.duration_seconds > SINGLE_CLIP_MAX_SECONDS and request.continuity == "last_frame":
            raise AppError(
                501,
                "continuity_not_available",
                "Last-frame continuity (Wan VACE) is not enabled: measured at ~7x slower per clip on this GPU. "
                "Use continuity 'prompt'.",
            )
        user_scenes = [(s.description, s.duration_seconds) for s in request.scenes] if request.scenes else None
        plan = self._compile(
            request.prompt, mode="text-to-video", style=settings.style,
            duration=float(request.duration_seconds), user_scenes=user_scenes,
        )
        if request.duration_seconds <= SINGLE_CLIP_MAX_SECONDS:
            return plan, []
        beats = plan.scenes
        try:
            durations = scene_durations(float(request.duration_seconds), [b.duration_seconds for b in beats])
        except ValueError as err:
            raise AppError(422, "validation_error", "The request is invalid.", [{"field": "scenes", "message": str(err)}]) from None
        clips = plan_clips(durations, settings.fps, request.continuity)
        beats = [b.model_copy(update={"index": i + 1, "duration_seconds": d}) for i, (b, d) in enumerate(zip(beats, durations))]
        prompts = {c.target: c.text for c in plan.compiled}
        scenes = [
            SceneJob(
                index=b.index,
                description=b.description,
                prompt=prompts[f"scene {b.index}"],
                duration_seconds=b.duration_seconds,
                clips=[c.frames for c in clips if c.scene == b.index - 1],
            )
            for b in beats
        ]
        return plan.model_copy(update={"scenes": beats}), scenes

    def retry_scene(self, job_id: str, index: int) -> GenerationJob:
        """Re-queues a failed long video. Clips already on disk are kept; only missing ones are generated."""
        job = self.get(job_id)
        if not job.scenes:
            raise AppError(422, "not_a_long_video", "Only long (multi-scene) videos have scenes to retry.")
        if job.status != GenerationStatus.FAILED:
            raise AppError(409, "job_not_failed", "This video has not failed; there is nothing to retry.")
        scene = next((s for s in job.scenes if s.index == index), None)
        if scene is None:
            raise AppError(404, "scene_not_found", "No scene with this number.")
        if scene.status != GenerationStatus.FAILED:
            raise AppError(409, "scene_not_failed", "This scene did not fail.")
        scenes = [s.model_copy(update={"status": GenerationStatus.QUEUED, "error": None}) if s.index == index else s for s in job.scenes]
        self.store.update(job_id, status=GenerationStatus.QUEUED, error=None, finished_at=None, scenes=scenes)
        self._executor.submit(self._run_long_video, job_id)
        return self.get(job_id)

    def _update_scene(self, job_id: str, index: int, **changes: object) -> GenerationJob:
        job = self.store.get(job_id)
        assert job is not None
        scenes = [s.model_copy(update=changes) if s.index == index else s for s in job.scenes]
        completed = sum(s.clips_completed for s in scenes)
        return self.store.update(job_id, scenes=scenes, clips_completed=completed)

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
        job = self.store.transition(
            job_id, GenerationStatus.QUEUED, status=GenerationStatus.PROCESSING, started_at=_now(), queue_position=None
        )
        if job is None:
            return  # cancelled while queued
        s = job.settings
        assert self.engine is not None and s.width and s.height and s.steps and s.seed is not None
        try:
            self._unload(self.video_engine)
            targets = agent_mod.count_targets(job.plan) if self._agent_on(job) else []

            def make(seed: int):
                return self.engine.generate(
                    ImageParams(
                        prompt=s.prompt,
                        style=s.style,
                        width=s.width,
                        height=s.height,
                        steps=s.steps,
                        seed=seed,
                        negative_prompt=s.negative_prompt,
                        guidance_scale=s.guidance_scale,
                    ),
                    deadline=time.monotonic() + self.settings.image_timeout_seconds,
                )

            image, device = make(s.seed)
            if targets:
                checks = self._count_checks(image, targets)
                report = AgentResult(checks=checks)
                if not all(c.passed for c in checks):
                    retry_seed = (s.seed + 1) % (MAX_SEED + 1)
                    image2, device = make(retry_seed)
                    checks2 = self._count_checks(image2, targets)
                    report.attempts = 2
                    if sum(c.passed for c in checks2) > sum(c.passed for c in checks):
                        image, report.checks = image2, checks2
                        self.store.update(job_id, settings=s.model_copy(update={"seed": retry_seed}))
                        report.notes.append(f"First image failed a check; the retry (seed {retry_seed}) was better and is shown.")
                    else:
                        report.notes.append("First image failed a check; the retry was not better, so the first is shown.")
                self.store.update(job_id, agent=report)
                self.agent.unload()
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
            cancel = self._cancel.setdefault(job_id, threading.Event())
            job = self.store.transition(
                job_id, GenerationStatus.QUEUED, status=GenerationStatus.PROCESSING, started_at=_now(), queue_position=None
            )
            if job is None:
                self._cancel.pop(job_id, None)
                return  # cancelled while queued
            s = job.settings
            assert self.video_engine is not None
            assert s.width and s.height and s.steps and s.seed is not None and s.num_frames and s.fps
            try:
                # The image and video models do not fit in GPU memory (or comfortably in RAM) together.
                self._unload(self.engine)
                tmp = self.video_storage.temp_path(job_id)

                def make(seed: int, path: Path) -> str:
                    return self.video_engine.generate(
                        VideoParams(
                            # The planner's scene description (user words first, then cast/place/camera/style).
                            prompt=(job.plan.model_prompt if job.plan and job.plan.model_prompt else s.prompt),
                            width=s.width,
                            height=s.height,
                            num_frames=s.num_frames,
                            num_inference_steps=s.steps,
                            seed=seed,
                            fps=s.fps,
                        ),
                        deadline=time.monotonic() + self.settings.video_timeout_seconds,
                        output_path=path,
                        cancel=cancel,
                    )

                targets = agent_mod.count_targets(job.plan) if self._agent_on(job) else []
                check = (lambda path: self._count_checks(_frames(path)[1], targets)) if targets else None
                # Counts are reported for text-to-video but not retried: in tests a new seed did not fix counts, and a
                # retry doubles a video's time. Images (seconds) do retry once.
                device = self._generate_checked(job_id, s.seed, tmp, make, check, retry=False)
                self.store.update(job_id, device=device)
                # Decoded and checked before the job may report success.
                stored = self.video_storage.finalize(job_id, tmp)
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
                self.video_storage.discard(job_id)
                self._fail(job_id, JobError(code=err.code, message=err.message, retryable=err.retryable))
            except Exception:
                logger.exception("video job %s failed unexpectedly", job_id)
                self.video_storage.discard(job_id)
                self._fail(
                    job_id,
                    JobError(code="generation_failed", message="Video generation failed on the server.", retryable=True),
                )
            finally:
                self._cancel.pop(job_id, None)

    def _run_long_video(self, job_id: str) -> None:
        """Generates each scene's clips (skipping ones already on disk), then joins and validates the MP4."""
        from app.services.video_storage import probe_mp4

        with self._video_lock:
            job = self.store.get(job_id)
            assert job is not None and self.video_engine is not None
            self.store.update(
                job_id, status=GenerationStatus.PROCESSING, started_at=job.started_at or _now(), queue_position=None
            )
            s = job.settings
            assert s.width and s.height and s.steps and s.seed is not None and s.fps and s.duration_seconds
            # Clips are stored by what they contain, not by job: if the backend has to restart (jobs are in
            # memory; a CUDA driver error needs a new process), the same request with the same seed reuses them.
            parts_key = _parts_key(self.video_engine.model_id, s, job.scenes)
            parts = self.video_storage.parts_dir(parts_key)
            current: int | None = None
            device = None
            try:
                self._unload(self.engine)
                ordered: list[tuple[Path, int]] = []
                for scene in job.scenes:
                    current = scene.index
                    self._update_scene(job_id, scene.index, status=GenerationStatus.PROCESSING, error=None)
                    for k, frames in enumerate(scene.clips):
                        path = parts / f"s{scene.index:02d}_c{k:02d}.mp4"
                        if not _valid_clip(path, frames, probe_mp4):
                            tmp = parts / f".s{scene.index:02d}_c{k:02d}.part.mp4"
                            device = self.video_engine.generate(
                                VideoParams(
                                    prompt=scene.prompt,
                                    width=s.width,
                                    height=s.height,
                                    num_frames=frames,
                                    num_inference_steps=s.steps,
                                    # Every scene starts from the same noise: with the same character text this
                                    # keeps the person more alike across scenes (benchmark 2026-11-14,
                                    # docs/consistency). Clips within a scene still differ (k), so nothing repeats.
                                    seed=(s.seed + k) % (MAX_SEED + 1),
                                    fps=s.fps,
                                ),
                                deadline=time.monotonic() + self.settings.video_timeout_seconds,
                                output_path=tmp,
                            )
                            if not _valid_clip(tmp, frames, probe_mp4):
                                tmp.unlink(missing_ok=True)
                                raise VideoEngineError("video_invalid", "A generated clip could not be decoded.", retryable=True)
                            os.replace(tmp, path)
                        # Clips of one scene crossfade; a new scene starts with a cut.
                        overlap = CROSSFADE_FRAMES if k > 0 else (SCENE_CUT_FRAMES if ordered else 0)
                        ordered.append((path, overlap))
                        self._update_scene(job_id, scene.index, clips_completed=k + 1)
                    self._update_scene(job_id, scene.index, status=GenerationStatus.COMPLETED)
                current = None
                total = round(s.duration_seconds * s.fps)
                tmp_final = self.video_storage.temp_path(job_id)
                written = join_clips(ordered, tmp_final, s.fps, total)
                if written != total:
                    raise VideoEngineError("video_invalid", f"Joined {written} of {total} frames.", retryable=True)
                stored = self.video_storage.finalize(job_id, tmp_final)
                if stored.num_frames != total:
                    raise VideoEngineError("video_invalid", "The final video has the wrong length.", retryable=True)
                url = f"{VIDEOS_PREFIX}/{stored.filename}"
                self.store.update(
                    job_id,
                    status=GenerationStatus.COMPLETED,
                    finished_at=_now(),
                    device=device or job.device,
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
                self.video_storage.discard_parts(parts_key)
                logger.info("long video %s completed: %d clips, %.1fs", job_id, len(ordered), stored.duration_seconds)
            except Exception as exc:
                error = (
                    JobError(code=exc.code, message=exc.message, retryable=exc.retryable)
                    if isinstance(exc, VideoEngineError)
                    else JobError(code="generation_failed", message="Video generation failed on the server.", retryable=True)
                )
                if not isinstance(exc, VideoEngineError):
                    logger.exception("long video %s failed", job_id)
                self.video_storage.discard(job_id)
                if current is not None:
                    self._update_scene(job_id, current, status=GenerationStatus.FAILED, error=error)
                self._fail(job_id, error)

    @staticmethod
    def _unload(engine: object) -> None:
        unload = getattr(engine, "unload", None)
        if callable(unload):
            try:
                unload()
            except Exception:
                logger.warning("Could not unload %s", type(engine).__name__)

    def _fail(self, job_id: str, error: JobError) -> None:
        job = self.store.get(job_id)
        device = job.device if job else None
        if device is None and job is not None and job.settings.mode == GenerationMode.TEXT_TO_IMAGE and self.engine:
            try:
                device = self.engine.status().device
            except Exception:
                pass
        self.store.update(job_id, status=GenerationStatus.FAILED, finished_at=_now(), error=error, device=device)


def _frames(path: Path):
    """First, middle and last frame of an MP4 as PIL images (iterated: list(reader) raises MemoryError)."""
    import imageio.v2 as imageio
    from PIL import Image

    frames = []
    reader = imageio.get_reader(str(path), "ffmpeg")
    try:
        for frame in reader:
            frames.append(frame)
    finally:
        reader.close()
    return Image.fromarray(frames[0]), Image.fromarray(frames[len(frames) // 2]), Image.fromarray(frames[-1])


def _estimate_tokens(text: str) -> int:
    """Used only when the model's tokenizer is not on disk; real tokenizers count more (sub-words)."""
    import re

    return len(re.findall(r"\w+|[^\w\s]", text))


def _parts_key(model_id: str, s: NormalizedSettings, scenes: list[SceneJob]) -> str:
    """A UUID derived from everything that determines the clips' pixels (model, size, fps, steps, seed and
    each scene's prompt and clip lengths). Equal requests map to the same clip folder."""
    import hashlib
    import json

    content = json.dumps(
        {
            "model": model_id, "w": s.width, "h": s.height, "fps": s.fps, "steps": s.steps, "seed": s.seed,
            "scenes": [[sc.index, sc.prompt, sc.clips] for sc in scenes],
        },
        sort_keys=True,
    )
    return str(uuid.UUID(bytes=hashlib.sha256(content.encode()).digest()[:16]))


def _valid_clip(path: Path, frames: int, probe) -> bool:
    """A clip counts as done only if it decodes to the planned number of frames."""
    if not path.is_file():
        return False
    try:
        return probe(path)[2] == frames
    except Exception:
        return False
