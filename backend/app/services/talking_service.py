"""Talking videos: text -> speech (Chatterbox, speech container) -> lip-sync (MuseTalk, lipsync container).

The source is a finished video job or an uploaded photo. The GPU is shared: the job takes the video lock, unloads the
image/video models and the prompt agent, and each service frees its GPU memory after its step. Files move through the
shared outputs volume (/app/outputs here, /outputs in the services). Jobs live in memory, like generation jobs.
"""

from __future__ import annotations

import json
import logging
import threading
import time
import urllib.error
import urllib.request
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from app.core.errors import AppError

logger = logging.getLogger(__name__)

TalkStatus = Literal["queued", "speaking", "lip_syncing", "completed", "failed"]


class TalkRequest(BaseModel):
    text: str = Field(min_length=1, max_length=600)
    language: Literal["en", "hi", "ur"] = "en"
    voice_id: str | None = Field(None, pattern=r"^[0-9a-f]{32}$")
    source_job_id: str | None = Field(None, description="A finished video job to make talk.")
    upload_id: str | None = Field(None, description="Or an uploaded photo (a talking photo).")
    exaggeration: float = Field(0.5, ge=0.25, le=1.0)


class TalkJob(BaseModel):
    id: str
    status: TalkStatus = "queued"
    request: TalkRequest
    created_at: datetime
    finished_at: datetime | None = None
    audio_seconds: float | None = None
    speech_seconds: float | None = None
    lipsync_seconds: float | None = None
    video_url: str | None = None
    audio_url: str | None = None
    error: str | None = None


def _now() -> datetime:
    return datetime.now(UTC)


class TalkingService:
    def __init__(self, generation, speech_url: str, lipsync_url: str) -> None:
        self.gen = generation
        self.speech_url = speech_url.rstrip("/")
        self.lipsync_url = lipsync_url.rstrip("/")
        self.outputs = Path(generation.settings.video_output_dir).parent.resolve()
        self._jobs: dict[str, TalkJob] = {}
        self._lock = threading.Lock()

    # --- service calls ---------------------------------------------------------------------

    def _call(self, base: str, path: str, payload: dict | bytes | None = None, *, timeout: float = 30,
              content_type: str = "application/json", method: str | None = None) -> dict | list:
        data = payload if isinstance(payload, bytes) else (json.dumps(payload).encode() if payload is not None else None)
        req = urllib.request.Request(base + path, data=data, method=method or ("POST" if data is not None else "GET"),
                                     headers={"Content-Type": content_type})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as res:
                return json.load(res)
        except urllib.error.HTTPError as err:
            detail = err.read().decode(errors="replace")
            try:
                detail = json.loads(detail).get("detail", detail)
            except ValueError:
                pass
            raise AppError(err.code if err.code < 500 else 502, "speech_service_error", str(detail)[:500]) from None
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            raise AppError(503, "speech_service_unavailable",
                           "The speech/lip-sync service is not running (docker compose up speech lipsync).") from None

    def status(self) -> dict:
        out = {}
        for name, base in (("speech", self.speech_url), ("lipsync", self.lipsync_url)):
            try:
                out[name] = self._call(base, "/health", timeout=3)
            except AppError as err:
                out[name] = {"status": "unavailable", "detail": err.message}
        return out

    def voices(self) -> list:
        return self._call(self.speech_url, "/voices")  # type: ignore[return-value]

    def add_voice(self, data: bytes, name: str, gender: str) -> dict:
        from urllib.parse import quote

        return self._call(self.speech_url, f"/voices?name={quote(name)}&gender={quote(gender)}", data,
                          content_type="application/octet-stream", timeout=60)  # type: ignore[return-value]

    # --- jobs ------------------------------------------------------------------------------

    def _source(self, req: TalkRequest) -> Path:
        if bool(req.source_job_id) == bool(req.upload_id):
            raise AppError(422, "validation_error", "Give either a finished video (source_job_id) or a photo (upload_id).")
        if req.upload_id:
            path = self.gen.uploads.resolve(req.upload_id)
            if path is None:
                raise AppError(422, "upload_expired", "The uploaded photo was not found or has expired.")
            return path
        path = self.gen.video_storage.resolve(f"{req.source_job_id}.mp4")
        if path is None:
            raise AppError(422, "video_not_found", "That video was not found. Generate it first.")
        return path

    def create(self, req: TalkRequest) -> TalkJob:
        self._source(req)
        job = TalkJob(id=str(uuid.uuid4()), request=req, created_at=_now())
        with self._lock:
            self._jobs[job.id] = job
        threading.Thread(target=self._run, args=(job.id,), daemon=True, name="talking").start()
        return job

    def get(self, job_id: str) -> TalkJob:
        with self._lock:
            job = self._jobs.get(job_id)
        if job is None:
            raise AppError(404, "talk_not_found", "No talking-video job with this ID.")
        return job

    def _update(self, job_id: str, **changes) -> None:
        with self._lock:
            self._jobs[job_id] = self._jobs[job_id].model_copy(update=changes)

    def _to_service(self, path: Path) -> str:
        return "/outputs/" + str(path.resolve().relative_to(self.outputs)).replace("\\", "/")

    def _from_service(self, path: str) -> Path:
        return self.outputs / path.removeprefix("/outputs/")

    def _run(self, job_id: str) -> None:
        job = self.get(job_id)
        req = job.request
        with self.gen._video_lock:  # one GPU job at a time, shared with image/video generation
            try:
                source = self._source(req)
                self.gen._unload(self.gen.engine)
                self.gen._unload(self.gen.video_engine)
                self.gen.agent.unload()
                self._update(job_id, status="speaking")
                t = time.perf_counter()
                speech = self._call(self.speech_url, "/tts", {
                    "text": req.text, "language": req.language, "voice_id": req.voice_id,
                    "exaggeration": req.exaggeration,
                }, timeout=900)
                audio = self._from_service(speech["path"])
                self._update(job_id, status="lip_syncing", audio_seconds=speech["seconds"],
                             speech_seconds=round(time.perf_counter() - t, 1))
                t = time.perf_counter()
                result = self._call(self.lipsync_url, "/lipsync", {
                    "video_path": self._to_service(source), "audio_path": self._to_service(audio),
                }, timeout=3600)
                produced = self._from_service(result["path"])
                tmp = self.gen.video_storage.temp_path(job_id)
                produced.replace(tmp)
                stored = self.gen.video_storage.finalize(job_id, tmp)
                self._update(job_id, status="completed", finished_at=_now(),
                             lipsync_seconds=round(time.perf_counter() - t, 1),
                             video_url=f"/api/v1/files/videos/{stored.filename}")
            except AppError as err:
                logger.warning("talking job %s failed: %s", job_id, err.message)
                self._update(job_id, status="failed", finished_at=_now(), error=err.message)
            except Exception as exc:
                logger.exception("talking job %s failed", job_id)
                message = getattr(exc, "message", None) or "The talking video could not be made."
                self._update(job_id, status="failed", finished_at=_now(), error=message)
