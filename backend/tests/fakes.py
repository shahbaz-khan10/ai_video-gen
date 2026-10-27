"""A mocked image engine for automated tests. It draws a flat PNG; no AI model is involved."""

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

    def generate(self, params: ImageParams, deadline: float) -> tuple[Image.Image, str]:
        self.calls.append(params)
        self.started.set()
        if self.gate is not None:
            self.gate.wait(timeout=10)
        if self.generate_error is not None:
            raise self.generate_error
        self.loaded = True
        return Image.new("RGB", (params.width, params.height), (40, 30, 90)), "cpu"
