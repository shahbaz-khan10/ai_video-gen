"""High quality text-to-video (Wan2.2 TI2V-5B): request rules, settings and routing to the engine."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from tests.conftest import wait_for_status
from tests.fakes import FakeImageEngine, FakeVideoEngine

CREATE = "/api/v1/generations"
VALIDATE = "/api/v1/generations/validate"


@pytest.fixture
def video_engine() -> FakeVideoEngine:
    return FakeVideoEngine()


@pytest.fixture
def vclient(settings: Settings, engine: FakeImageEngine, video_engine: FakeVideoEngine) -> Iterator[TestClient]:
    with TestClient(create_app(settings, engine=engine, video_engine=video_engine)) as test_client:
        yield test_client


def hq(**overrides) -> dict:
    payload = {"mode": "text-to-video", "prompt": "A woman walks through a market", "aspect_ratio": "16:9",
               "quality": "high"}
    payload.update(overrides)
    return payload


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({}, (576, 320, 49, 25)),  # default 2 s at Wan2.2's 24 fps
        ({"duration_seconds": 3, "resolution": "large"}, (832, 480, 73, 25)),
        ({"duration_seconds": 5}, (576, 320, 121, 25)),  # 121 frames: above Wan2.1's 81 cap
        ({"steps": 40}, (576, 320, 49, 40)),
    ],
)
def test_high_quality_settings(vclient: TestClient, overrides: dict, expected: tuple) -> None:
    res = vclient.post(VALIDATE, json=hq(**overrides))
    assert res.status_code == 200, res.text
    s = res.json()["settings"]
    assert (s["width"], s["height"], s["num_frames"], s["steps"]) == expected
    assert s["fps"] == 24 and s["quality"] == "high"
    assert s["model_id"] == "Wan-AI/Wan2.2-TI2V-5B-Diffusers"


def test_fast_stays_the_default(vclient: TestClient) -> None:
    s = vclient.post(VALIDATE, json=hq(quality="fast")).json()["settings"]
    assert s["fps"] == 16 and s["model_id"] == "test/fake-video-model"


@pytest.mark.parametrize("overrides", [{"duration_seconds": 15}, {"num_frames": 49}, {"quality": "ultra"}])
def test_high_quality_rejects_what_it_cannot_make(vclient: TestClient, overrides: dict) -> None:
    assert vclient.post(CREATE, json=hq(**overrides)).status_code == 422


def test_high_quality_without_weights_is_refused(vclient: TestClient, video_engine: FakeVideoEngine) -> None:
    video_engine.hq_ready = False
    res = vclient.post(CREATE, json=hq())
    assert res.status_code == 503
    assert res.json()["error"]["code"] == "model_not_downloaded"
    assert not video_engine.calls


def test_high_quality_job_reaches_the_engine(vclient: TestClient, video_engine: FakeVideoEngine) -> None:
    res = vclient.post(CREATE, json=hq(seed=7))
    assert res.status_code == 202, res.text
    job = wait_for_status(vclient, res.json()["id"], {"completed", "failed"})
    assert job["status"] == "completed", job.get("error")
    params = video_engine.calls[-1]
    assert (params.quality, params.fps, params.num_frames, params.seed) == ("high", 24, 49, 7)


def test_info_reports_high_quality(vclient: TestClient, video_engine: FakeVideoEngine) -> None:
    assert vclient.get("/api/v1/info").json()["limits"]["video_hq_available"] is True
    video_engine.hq_ready = False
    limits = vclient.get("/api/v1/info").json()["limits"]
    assert limits["video_hq_available"] is False and "not downloaded" in limits["video_hq_detail"]
