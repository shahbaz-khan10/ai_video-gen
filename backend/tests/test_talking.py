"""Talking videos: validation and orchestration with fake speech/lip-sync services (no real models here; Chatterbox and
MuseTalk are measured in docs/speech)."""

from __future__ import annotations

import io
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.core.config import Settings
from app.main import create_app
from tests.fakes import FakeImageEngine, FakeVideoEngine


@pytest.fixture
def vclient(settings: Settings, engine: FakeImageEngine) -> Iterator[TestClient]:
    settings = settings.model_copy(update={"speech_url": "http://127.0.0.1:9", "lipsync_url": "http://127.0.0.1:9"})
    with TestClient(create_app(settings, engine=engine, video_engine=FakeVideoEngine())) as client:
        yield client


def _photo(client: TestClient) -> str:
    buf = io.BytesIO()
    Image.new("RGB", (512, 512), (120, 120, 120)).save(buf, format="PNG")
    return client.post("/api/v1/uploads/images", content=buf.getvalue(), headers={"Content-Type": "image/png"}).json()["upload_id"]


def test_services_down_is_reported_not_crashed(vclient: TestClient) -> None:
    status = vclient.get("/api/v1/talking/status").json()
    assert status["speech"]["status"] == "unavailable" and status["lipsync"]["status"] == "unavailable"
    assert vclient.get("/api/v1/talking/voices").status_code == 503


@pytest.mark.parametrize("body", [
    {"text": "Hi"},  # no source
    {"text": "Hi", "source_job_id": "x", "upload_id": "y"},  # both
    {"text": "Hi", "source_job_id": "0b6f8a3e-1d2c-4f5a-9b7e-123456789abc"},  # unknown video
    {"text": "Hi", "upload_id": "0b6f8a3e-1d2c-4f5a-9b7e-123456789abc"},  # unknown photo
    {"text": "", "upload_id": "0b6f8a3e-1d2c-4f5a-9b7e-123456789abc"},
    {"text": "Hi", "language": "fr", "upload_id": "0b6f8a3e-1d2c-4f5a-9b7e-123456789abc"},
])
def test_bad_requests(vclient: TestClient, body: dict) -> None:
    assert vclient.post("/api/v1/talking", json=body).status_code == 422


def test_job_runs_speech_then_lipsync(vclient: TestClient, monkeypatch) -> None:
    svc = vclient.app.state.talking_service
    calls = []

    def fake_call(base, path, payload=None, **kw):
        if path == "/voices":
            return []
        calls.append((base, path, payload))
        if path == "/tts":
            audio = svc.outputs / "audio" / "a.wav"
            audio.parent.mkdir(parents=True, exist_ok=True)
            audio.write_bytes(b"RIFF")
            return {"path": "/outputs/audio/a.wav", "seconds": 2.5}
        # lip-sync: write a real tiny MP4 where the service would
        import numpy as np

        from app.services.video_engine import write_mp4

        out = svc.outputs / "talking" / "t.mp4"
        write_mp4([np.zeros((64, 64, 3), dtype=np.uint8)] * 10, out, fps=25)
        return {"path": "/outputs/talking/t.mp4", "seconds": 1.0}

    monkeypatch.setattr(svc, "_call", fake_call)
    uid = _photo(vclient)
    res = vclient.post("/api/v1/talking", json={"text": "Assalam o alaikum", "language": "ur", "upload_id": uid})
    assert res.status_code == 202
    job_id = res.json()["id"]
    import time

    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        job = vclient.get(f"/api/v1/talking/{job_id}").json()
        if job["status"] in ("completed", "failed"):
            break
        time.sleep(0.05)
    assert job["status"] == "completed", job
    assert job["audio_seconds"] == 2.5 and job["video_url"] == f"/api/v1/files/videos/{job_id}.mp4"
    assert [c[1] for c in calls] == ["/tts", "/lipsync"]
    assert calls[0][2]["language"] == "ur"
    assert calls[1][2]["video_path"].startswith("/outputs/uploads/") and calls[1][2]["audio_path"] == "/outputs/audio/a.wav"
    assert vclient.get(job["video_url"]).status_code == 200


@pytest.mark.parametrize(("text", "gender"), [
    ("A young woman with long black hair. She is wearing a blue saree. The background is green.", "female"),
    ("A young man with a beard and mustache. He is standing with his arms crossed.", "male"),
    ("The image shows the sea and the sky.", None),
])
def test_gender_from_description(text: str, gender) -> None:
    from app.services.talking_service import gender_from_text

    assert gender_from_text(text) == gender


def test_woman_is_not_given_the_male_builtin_voice(vclient: TestClient, monkeypatch) -> None:
    svc = vclient.app.state.talking_service
    monkeypatch.setattr(svc, "_speaker", lambda source: "female")
    monkeypatch.setattr(svc, "voices", lambda: [])
    calls = []
    monkeypatch.setattr(svc, "_call", lambda *a, **k: calls.append(a) or {})
    uid = _photo(vclient)
    job_id = vclient.post("/api/v1/talking", json={"text": "Hi", "upload_id": uid}).json()["id"]
    import time

    for _ in range(200):
        job = vclient.get(f"/api/v1/talking/{job_id}").json()
        if job["status"] in ("completed", "failed"):
            break
        time.sleep(0.05)
    assert job["status"] == "failed" and "woman" in job["error"] and job["speaker"] == "female"
    assert calls == []  # no speech was generated with the wrong voice


def test_matching_saved_voice_is_chosen(vclient: TestClient, monkeypatch) -> None:
    svc = vclient.app.state.talking_service
    monkeypatch.setattr(svc, "_speaker", lambda source: "female")
    monkeypatch.setattr(svc, "voices", lambda: [
        {"id": "a" * 32, "name": "Ali", "gender": "male", "seconds": 12},
        {"id": "b" * 32, "name": "Sara", "gender": "female", "seconds": 14},
    ])
    from app.services.talking_service import TalkRequest

    req = TalkRequest(text="Hi", upload_id=_photo(vclient))
    job = svc.create.__self__  # service instance
    job_id = "x"
    svc._jobs[job_id] = svc._jobs.get(job_id) or __import__("app.services.talking_service", fromlist=["TalkJob"]).TalkJob(
        id=job_id, request=req, created_at=__import__("datetime").datetime.now())
    assert svc._match_voice(job_id, req, svc._source(req)) == "b" * 32
    assert svc.get(job_id).voice_used == "Sara (female)"
