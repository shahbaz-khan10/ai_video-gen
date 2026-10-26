import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


@pytest.fixture
def settings() -> Settings:
    # _env_file=None keeps a developer's local .env from affecting tests.
    return Settings(_env_file=None, environment="test", cors_origins=["http://localhost:3000"])


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
