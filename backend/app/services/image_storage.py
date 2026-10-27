"""Saves generated images and resolves them safely for download.

Files are named ``<job uuid>.png``, so they never collide or overwrite each other.
Only names matching that exact pattern are ever served, and only from the
configured output directory.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from app.services.image_engine import EngineError

if TYPE_CHECKING:
    from PIL.Image import Image

logger = logging.getLogger(__name__)

FILENAME_PATTERN = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\.png$")


@dataclass(frozen=True)
class StoredImage:
    filename: str
    width: int
    height: int
    size_bytes: int


class ImageStorage:
    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir.resolve()

    def save(self, job_id: str, image: Image) -> StoredImage:
        from PIL import Image as PILImage

        filename = f"{job_id}.png"
        if not FILENAME_PATTERN.match(filename):
            raise ValueError("Job IDs must be UUIDs")
        final = self.output_dir / filename
        tmp = self.output_dir / f".{job_id}.tmp"
        try:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            image.save(tmp, format="PNG")
            # Re-open to prove a complete, decodable PNG was written before publishing it.
            with PILImage.open(tmp) as check:
                check.verify()
            os.replace(tmp, final)  # atomic: readers never see a partial file
            return StoredImage(filename, image.width, image.height, final.stat().st_size)
        except Exception:
            logger.exception("Saving image for job %s failed", job_id)
            tmp.unlink(missing_ok=True)
            raise EngineError(
                "image_save_failed", "The image was generated but couldn't be saved on the server.", retryable=True
            ) from None

    def resolve(self, filename: str) -> Path | None:
        """Path for a served filename, or None. Rejects anything but ``<uuid>.png`` in the output dir."""
        if not FILENAME_PATTERN.match(filename):
            return None
        path = (self.output_dir / filename).resolve()
        if path.parent != self.output_dir or not path.is_file():
            return None
        return path
