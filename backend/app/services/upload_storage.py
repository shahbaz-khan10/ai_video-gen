"""Uploaded source images for image-to-video.

An upload is decoded with Pillow (the bytes decide the format, not the file name or the declared type), checked
for size and dimensions, rotated by its EXIF orientation, and re-encoded as a plain RGB PNG named ``<uuid>.png``.
Re-encoding drops metadata (GPS, camera data) and anything that is not pixels. Uploads older than
``MAX_AGE_SECONDS`` are deleted on the next upload.
"""

from __future__ import annotations

import io
import logging
import os
import re
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MIN_SIDE = 256
MAX_SIDE = 8192
# Pillow raises above 2x its MAX_IMAGE_PIXELS and warns above 1x; 40 MP covers phone photos.
MAX_PIXELS = 40_000_000
ACCEPTED_FORMATS = {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp"}
MAX_AGE_SECONDS = 24 * 3600
_NAME = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


class UploadError(Exception):
    """A rejected upload. The message is safe to show to the user."""

    def __init__(self, code: str, message: str, status: int = 422) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


@dataclass(frozen=True)
class StoredUpload:
    id: str
    width: int
    height: int
    size_bytes: int
    original_type: str


class UploadStorage:
    def __init__(self, directory: Path) -> None:
        self.directory = directory.resolve()

    def save(self, data: bytes) -> StoredUpload:
        from PIL import Image, ImageOps, UnidentifiedImageError

        if not data:
            raise UploadError("upload_empty", "The file is empty.")
        if len(data) > MAX_UPLOAD_BYTES:
            raise UploadError("upload_too_large", "The image is larger than 10 MB.", status=413)
        try:
            with Image.open(io.BytesIO(data)) as probe:
                fmt = probe.format
                width, height = probe.size
                if fmt not in ACCEPTED_FORMATS:
                    raise UploadError("upload_unsupported_type", "Only JPG, PNG and WebP images are supported.", status=415)
                if width * height > MAX_PIXELS:
                    raise UploadError("upload_too_many_pixels", f"The image is {width}x{height}; the limit is 40 megapixels.")
                probe.verify()  # structural check (truncated / corrupted files)
            with Image.open(io.BytesIO(data)) as img:
                img.load()  # full decode: catches corrupt pixel data that verify() misses
                img = ImageOps.exif_transpose(img)
                if img.mode in ("RGBA", "LA", "P"):
                    rgba = img.convert("RGBA")
                    background = Image.new("RGB", rgba.size, (255, 255, 255))
                    background.paste(rgba, mask=rgba.getchannel("A"))
                    img = background
                else:
                    img = img.convert("RGB")
        except UploadError:
            raise
        except (UnidentifiedImageError, Image.DecompressionBombError):
            raise UploadError("upload_invalid_image", "This file is not a readable JPG, PNG or WebP image.") from None
        except (OSError, SyntaxError, ValueError):
            raise UploadError("upload_corrupted", "The image is damaged or incomplete and could not be read.") from None
        width, height = img.size
        if min(width, height) < MIN_SIDE:
            raise UploadError("upload_too_small", f"The image is {width}x{height}; each side must be at least {MIN_SIDE} px.")
        if max(width, height) > MAX_SIDE:
            raise UploadError("upload_too_large_dimensions", f"The image is {width}x{height}; each side must be at most {MAX_SIDE} px.")

        self.sweep()
        upload_id = str(uuid.uuid4())
        self.directory.mkdir(parents=True, exist_ok=True)
        final = self.directory / f"{upload_id}.png"
        tmp = self.directory / f".{upload_id}.tmp"
        try:
            img.save(tmp, format="PNG")
            os.replace(tmp, final)
        except OSError:
            tmp.unlink(missing_ok=True)
            logger.exception("Saving upload failed")
            raise UploadError("upload_save_failed", "The image could not be saved on the server.", status=500) from None
        return StoredUpload(upload_id, width, height, final.stat().st_size, ACCEPTED_FORMATS[fmt])

    def resolve(self, upload_id: str) -> Path | None:
        """Path of a stored upload, or None for unknown, expired or malformed IDs."""
        if not _NAME.match(upload_id):
            return None
        path = (self.directory / f"{upload_id}.png").resolve()
        if path.parent != self.directory or not path.is_file():
            return None
        return path

    def sweep(self, now: float | None = None) -> int:
        """Deletes uploads older than MAX_AGE_SECONDS. Returns how many were removed."""
        if not self.directory.is_dir():
            return 0
        now = now or time.time()
        removed = 0
        for path in self.directory.iterdir():
            try:
                if path.is_file() and now - path.stat().st_mtime > MAX_AGE_SECONDS:
                    path.unlink()
                    removed += 1
            except OSError:
                pass
        return removed
