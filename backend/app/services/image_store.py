"""Storage for generated images.

Files are named by the server (``<32 hex chars>.png``), written atomically, and looked
up only through :meth:`ImageStore.resolve`, which rejects anything that is not such a
name inside the output directory. Client input never becomes a filesystem path.
"""

import os
import re
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PIL.Image import Image

FILES_ROUTE = "/api/v1/files/images"
FILENAME_PATTERN = r"^[0-9a-f]{32}\.png$"
_FILENAME = re.compile(FILENAME_PATTERN)


class ImageSaveError(Exception):
    pass


class ImageStore:
    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir

    def save(self, image: "Image", expected_size: tuple[int, int]) -> str:
        """Writes a PNG and returns its filename. Never overwrites an existing file."""
        if image.size != expected_size:
            raise ImageSaveError(f"model returned {image.size}, expected {expected_size}")
        filename = f"{uuid.uuid4().hex}.png"
        target = self.output_dir / filename
        tmp = self.output_dir / f".{filename}.tmp"
        try:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            image.save(tmp, format="PNG")
            if target.exists():  # astronomically unlikely with uuid4, but never overwrite
                raise ImageSaveError("filename collision")
            os.replace(tmp, target)
        except OSError as exc:
            raise ImageSaveError(str(exc)) from exc
        finally:
            tmp.unlink(missing_ok=True)
        return filename

    def resolve(self, filename: str) -> Path | None:
        if not _FILENAME.fullmatch(filename):
            return None
        root = self.output_dir.resolve()
        path = (root / filename).resolve()
        if path.parent != root or not path.is_file():
            return None
        return path

    @staticmethod
    def url_for(filename: str) -> str:
        return f"{FILES_ROUTE}/{filename}"
