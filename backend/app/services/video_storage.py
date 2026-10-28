"""Saves generated videos and resolves them safely for download."""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path

from app.services.video_engine import VideoEngineError

logger = logging.getLogger(__name__)

FILENAME_PATTERN = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\.mp4$")


@dataclass(frozen=True)
class StoredVideo:
    filename: str
    width: int
    height: int
    size_bytes: int
    num_frames: int | None = None
    duration_seconds: float | None = None


class VideoStorage:
    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir.resolve()

    def save(self, job_id: str, video_bytes: bytes) -> StoredVideo:
        filename = f"{job_id}.mp4"
        if not FILENAME_PATTERN.match(filename):
            raise ValueError("Job IDs must be UUIDs")
        final = self.output_dir / filename
        tmp = self.output_dir / f".{job_id}.tmp"
        try:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            with open(tmp, "wb") as f:
                f.write(video_bytes)
            os.replace(tmp, final)
            size = final.stat().st_size
            return StoredVideo(filename, width=0, height=0, size_bytes=size)
        except Exception:
            logger.exception("Saving video for job %s failed", job_id)
            try:
                tmp.unlink(missing_ok=True)
            except Exception:
                pass
            raise VideoEngineError("video_save_failed", "The video was generated but couldn't be saved on the server.", retryable=True) from None

    def resolve(self, filename: str) -> Path | None:
        if not FILENAME_PATTERN.match(filename):
            return None
        path = (self.output_dir / filename).resolve()
        if path.parent != self.output_dir or not path.is_file():
            return None
        return path
