"""Saves generated videos and resolves them safely for download.

The engine writes to a hidden temporary file; ``finalize`` decodes it and only then gives it its public
``<job uuid>.mp4`` name. A file that cannot be decoded never becomes downloadable.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path

from app.services.video_engine import VideoEngineError

logger = logging.getLogger(__name__)

_UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
FILENAME_PATTERN = re.compile(rf"^{_UUID}\.mp4$")
_JOB_ID = re.compile(rf"^{_UUID}$")


@dataclass(frozen=True)
class StoredVideo:
    filename: str
    width: int
    height: int
    size_bytes: int
    num_frames: int
    duration_seconds: float


def probe_mp4(path: Path) -> tuple[int, int, int, float]:
    """Decodes every frame. Returns (width, height, frame_count, fps). Raises if the file is not a valid video."""
    import imageio.v2 as imageio

    reader = imageio.get_reader(str(path), format="ffmpeg")
    try:
        fps = float(reader.get_meta_data().get("fps") or 0)
        count, width, height = 0, 0, 0
        for frame in reader:
            height, width = frame.shape[:2]
            count += 1
    finally:
        reader.close()
    if count == 0 or width == 0 or fps <= 0:
        raise ValueError("no decodable frames")
    return width, height, count, fps


class VideoStorage:
    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir.resolve()

    def sweep_temp(self) -> int:
        """Deletes half-written ``.<uuid>.part.mp4`` files left by a crash. Called at startup, when no job runs.
        Finished videos and long-video clip parts (kept for resume) are never touched."""
        removed = 0
        if not self.output_dir.is_dir():
            return 0
        for path in self.output_dir.glob(".*.part.mp4"):
            try:
                path.unlink()
                removed += 1
            except OSError:
                pass
        return removed

    def temp_path(self, job_id: str) -> Path:
        """Where the engine writes; hidden and not matching FILENAME_PATTERN, so it is never served."""
        if not _JOB_ID.match(job_id):
            raise ValueError("Job IDs must be UUIDs")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        return self.output_dir / f".{job_id}.part.mp4"

    def finalize(self, job_id: str, tmp: Path) -> StoredVideo:
        filename = f"{job_id}.mp4"
        final = self.output_dir / filename
        try:
            width, height, frames, fps = probe_mp4(tmp)
        except Exception:
            logger.exception("Generated video for job %s failed validation", job_id)
            tmp.unlink(missing_ok=True)
            raise VideoEngineError(
                "video_invalid", "The model ran, but the video file could not be decoded.", retryable=True
            ) from None
        try:
            os.replace(tmp, final)
        except OSError:
            logger.exception("Saving video for job %s failed", job_id)
            tmp.unlink(missing_ok=True)
            raise VideoEngineError(
                "video_save_failed", "The video was generated but couldn't be saved on the server.", retryable=True
            ) from None
        return StoredVideo(
            filename=filename,
            width=width,
            height=height,
            size_bytes=final.stat().st_size,
            num_frames=frames,
            duration_seconds=round(frames / fps, 2),
        )

    def parts_dir(self, job_id: str) -> Path:
        """Clips of a long video, kept until the final MP4 exists so a failed scene can be retried alone.
        Lives in a sub-folder, so ``resolve`` (top-level ``<uuid>.mp4`` only) never serves a part."""
        if not _JOB_ID.match(job_id):
            raise ValueError("Job IDs must be UUIDs")
        path = self.output_dir / "parts" / job_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def discard_parts(self, job_id: str) -> None:
        import shutil

        if _JOB_ID.match(job_id):
            shutil.rmtree(self.output_dir / "parts" / job_id, ignore_errors=True)

    def discard(self, job_id: str) -> None:
        """Removes a failed job's temporary file. Finished videos are never touched."""
        try:
            self.temp_path(job_id).unlink(missing_ok=True)
        except (OSError, ValueError):
            pass

    def resolve(self, filename: str) -> Path | None:
        if not FILENAME_PATTERN.match(filename):
            return None
        path = (self.output_dir / filename).resolve()
        if path.parent != self.output_dir or not path.is_file():
            return None
        return path
