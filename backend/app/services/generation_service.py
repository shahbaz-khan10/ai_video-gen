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
from app.services.prompt_compiler import compile_plan
from app.services.prompt_tokens import CLIP_MAX_TOKENS, UMT5_MAX_TOKENS, count_tokens, load_tokenizer
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
        self._video_lock = threading.Lock()

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
            # The server runs one configured model (IMAGE_MODEL_ID). A request's model_id cannot switch it, so
            # the job records the model that actually runs rather than the one the client asked for.
            model_id = getattr(self.engine, "model_id", None)
            # Distilled models (Turbo, Lightning) produce broken images outside their step range, so the
            # effective count is clamped and recorded on the job.
            steps = (
                get_model_profile(model_id).clamp_steps(request.steps)
                if model_id and is_known_model(model_id)
                else request.steps
            )
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
            raise AppError(501, "mode_not_available", "Image-to-video is not available in this phase.")
        else:
            raise AppError(501, "mode_not_available", "This mode is not available.")

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
            style_text=STYLE_PROMPTS.get(style),
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
        job = self.store.update(job_id, status=GenerationStatus.PROCESSING, started_at=_now(), queue_position=None)
        s = job.settings
        assert self.engine is not None and s.width and s.height and s.steps and s.seed is not None
        try:
            self._unload(self.video_engine)
            image, device = self.engine.generate(
                ImageParams(
                    prompt=s.prompt,
                    style=s.style,
                    width=s.width,
                    height=s.height,
                    steps=s.steps,
                    seed=s.seed,
                    negative_prompt=s.negative_prompt,
                    guidance_scale=s.guidance_scale,
                ),
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
            assert self.video_engine is not None
            assert s.width and s.height and s.steps and s.seed is not None and s.num_frames and s.fps
            try:
                # The image and video models do not fit in GPU memory (or comfortably in RAM) together.
                self._unload(self.engine)
                tmp = self.video_storage.temp_path(job_id)
                device = self.video_engine.generate(
                    VideoParams(
                        # The planner's scene description (user words first, then cast/place/camera/style).
                        prompt=(job.plan.model_prompt if job.plan and job.plan.model_prompt else s.prompt),
                        width=s.width,
                        height=s.height,
                        num_frames=s.num_frames,
                        num_inference_steps=s.steps,
                        seed=s.seed,
                        fps=s.fps,
                    ),
                    deadline=time.monotonic() + self.settings.video_timeout_seconds,
                    output_path=tmp,
                )
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
                                    # Distinct but reproducible noise per clip.
                                    seed=(s.seed + scene.index * 1000 + k) % (MAX_SEED + 1),
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
