"""Mocked image and video engines for automated tests. No AI model is involved."""

from __future__ import annotations

import threading

from PIL import Image

from app.services.image_engine import EngineError, EngineStatus, ImageParams


class FakeImageEngine:
    name = "fake"
    model_id = "test/fake-model"

    def __init__(self) -> None:
        self.can_accept_error: EngineError | None = None
        self.generate_error: Exception | None = None
        # When set, generate() waits until the test releases it, so "processing" is observable.
        self.gate: threading.Event | None = None
        self.started = threading.Event()
        self.calls: list[ImageParams] = []
        self.loaded = False
        self.unloads = 0

    def status(self) -> EngineStatus:
        if self.can_accept_error is not None:
            state = "not_downloaded" if self.can_accept_error.code == "model_not_downloaded" else "unavailable"
            return EngineStatus(state, self.can_accept_error.message, self.model_id)
        if self.loaded:
            return EngineStatus("loaded", "Loaded on cpu.", self.model_id, device="cpu")
        return EngineStatus("not_loaded", "Weights are downloaded; the model loads on first use.", self.model_id)

    def ensure_can_accept(self) -> None:
        if self.can_accept_error is not None:
            raise self.can_accept_error

    def load(self) -> None:
        self.loaded = True

    def unload(self) -> None:
        self.unloads += 1
        self.loaded = False

    def generate(self, params: ImageParams, deadline: float) -> tuple[Image.Image, str]:
        self.calls.append(params)
        self.started.set()
        if self.gate is not None:
            self.gate.wait(timeout=10)
        if self.generate_error is not None:
            raise self.generate_error
        self.loaded = True
        return Image.new("RGB", (params.width, params.height), (40, 30, 90)), "cpu"


class FakeVideoEngine:
    """A mocked video engine. Writes a tiny real MP4 (solid frames); no AI model is involved."""

    name = "fake-video"
    model_id = "test/fake-video-model"

    def __init__(self) -> None:
        from app.services.video_engine import VideoEngineError, VideoParams

        self.can_accept_error: VideoEngineError | None = None
        self.generate_error: Exception | None = None
        # "garbage" writes bytes that are not a video, to exercise output validation.
        self.output: str = "mp4"
        self.gate: threading.Event | None = None
        self.started = threading.Event()
        self.calls: list[VideoParams] = []
        self.unloads = 0

    def status(self):
        from app.services.video_engine import VideoEngineStatus

        if self.can_accept_error is not None:
            return VideoEngineStatus("not_downloaded", self.can_accept_error.message, self.model_id)
        return VideoEngineStatus("not_loaded", "Weights are downloaded; the video model loads on first use.", self.model_id)

    def ensure_can_accept(self) -> None:
        if self.can_accept_error is not None:
            raise self.can_accept_error

    def unload(self) -> None:
        self.unloads += 1

    def i2v_status(self) -> tuple[bool, str]:
        return self.i2v_ready, "fake image-to-video"

    i2v_ready = True
    hq_ready = True

    def hq_status(self) -> tuple[bool, str]:
        return self.hq_ready, "fake Wan2.2" if self.hq_ready else "The high quality model is not downloaded."

    def generate_from_image(self, params, deadline: float, output_path, cancel=None) -> str:
        return self.generate(params, deadline, output_path, cancel)

    def generate(self, params, deadline: float, output_path, cancel=None) -> str:
        import numpy as np

        from app.services.video_engine import VideoEngineError, write_mp4

        self.calls.append(params)
        self.started.set()
        if self.gate is not None:
            self.gate.wait(timeout=10)
        if cancel is not None and cancel.is_set():
            raise VideoEngineError("cancelled", "The generation was cancelled.", retryable=True)
        if self.generate_error is not None:
            raise self.generate_error
        if self.output == "garbage":
            output_path.write_bytes(b"this is not an mp4")
            return "cpu"
        # Small frames keep the test fast; the storage layer reports what it actually decodes.
        frames = [np.full((64, 96, 3), (i * 10) % 255, dtype=np.uint8) for i in range(params.num_frames)]
        write_mp4(frames, output_path, fps=params.fps)
        return "cpu"
