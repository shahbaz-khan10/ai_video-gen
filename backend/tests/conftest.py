"""Shared fixtures. All of these use the mocked engine: no GPU, model or network needed."""

import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from tests.fakes import FakeImageEngine


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    # _env_file=None keeps a developer's local .env from affecting tests.
    return Settings(
        _env_file=None,
        environment="test",
        cors_origins=["http://localhost:3000"],
        image_output_dir=tmp_path / "outputs",
        image_model_cache_dir=tmp_path / "models",
        video_output_dir=tmp_path / "videos",
        upload_dir=tmp_path / "uploads",
    )


@pytest.fixture
def engine() -> FakeImageEngine:
    return FakeImageEngine()


@pytest.fixture
def client(settings: Settings, engine: FakeImageEngine) -> Iterator[TestClient]:
    with TestClient(create_app(settings, engine=engine)) as test_client:
        yield test_client


@pytest.fixture
def video_request() -> dict:
    return {
        "mode": "text-to-video",
        "prompt": "A lighthouse at blue hour, waves in slow motion",
        "aspect_ratio": "16:9",
        "style": "cinematic",
        "duration_seconds": 2,
    }


@pytest.fixture
def image_request() -> dict:
    return {"mode": "text-to-image", "prompt": "A red fox in fresh snow", "aspect_ratio": "1:1", "style": "documentary"}


def wait_for_status(client: TestClient, job_id: str, statuses: set[str], timeout: float = 5.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = client.get(f"/api/v1/generations/{job_id}").json()
        if job["status"] in statuses:
            return job
        time.sleep(0.02)
    raise AssertionError(f"job {job_id} never reached {statuses}; last status {job['status']}")
