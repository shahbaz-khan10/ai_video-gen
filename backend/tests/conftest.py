"""Shared fixtures. Ordinary tests never load a real model: they use IMAGE_ENGINE=none or a fake engine."""

import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.core.config import Settings
from app.main import create_app
from app.services.image_engine import EngineError, EngineStatus, GeneratedImage, ImageParams


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    # _env_file=None keeps a developer's local .env from affecting tests.
    return Settings(
        _env_file=None,
        environment="test",
        cors_origins=["http://localhost:3000"],
        image_engine="none",
        image_output_dir=tmp_path / "images",
        # Pinned SD-Turbo-like options so tests don't depend on the default model's settings.
        image_resolutions=[512, 768],
        image_default_resolution=512,
        image_max_steps=4,
        image_step_presets=[1, 2, 4],
        image_default_steps=1,
        image_guidance_scale=0.0,
    )


@pytest.fixture
def client(settings: Settings) -> TestClient:
    return TestClient(create_app(settings))


@pytest.fixture
def video_request() -> dict:
    return {
        "mode": "text-to-video",
        "prompt": "A lighthouse at blue hour, waves in slow motion",
        "aspect_ratio": "16:9",
        "style": "cinematic",
        "duration_seconds": 6,
    }


@pytest.fixture
def image_request() -> dict:
    return {"mode": "text-to-image", "prompt": "A red fox in fresh snow", "aspect_ratio": "1:1", "style": "cinematic"}


class FakeImageEngine:
    """Mocked engine: returns a solid-colour image of the requested size. No GPU, no weights."""

    name = "fake"

    def __init__(self, state: str = "ready", fail: Exception | None = None, size: tuple[int, int] | None = None):
        self.state = state
        self.fail = fail
        self.size = size
        self.calls: list[ImageParams] = []
        # Set `gate` to hold a job in "processing" until the test releases it.
        self.gate: threading.Event | None = None
        self.started = threading.Event()

    def status(self) -> EngineStatus:
        return EngineStatus(state=self.state, model_id="fake/model", detail="fake", device="cpu", cuda_available=False)

    def generate(self, params: ImageParams, deadline: float) -> GeneratedImage:
        self.calls.append(params)
        self.started.set()
        if self.gate is not None:
            self.gate.wait(timeout=5)
        if self.fail is not None:
            raise self.fail
        size = self.size or (params.width, params.height)
        return GeneratedImage(image=Image.new("RGB", size, (200, 80, 40)), device="cpu", model_id="fake/model")


@pytest.fixture
def fake_engine() -> FakeImageEngine:
    return FakeImageEngine()


@pytest.fixture
def gen_client(settings: Settings, fake_engine: FakeImageEngine) -> TestClient:
    return TestClient(create_app(settings, engine=fake_engine))


def wait_for_job(client: TestClient, job_id: str, timeout: float = 5.0) -> dict:
    """Polls like the frontend does until the job is completed or failed."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = client.get(f"/api/v1/generations/{job_id}").json()
        if job["status"] in ("completed", "failed"):
            return job
        time.sleep(0.01)
    raise AssertionError(f"job {job_id} did not finish")


__all__ = ["EngineError", "FakeImageEngine", "wait_for_job"]
