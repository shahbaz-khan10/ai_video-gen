"""Image-to-video: upload validation, request settings, job lifecycle, cancel and retry.

The video engine is FakeVideoEngine (a tiny real MP4, no AI model). Real VACE inference is measured by
scripts/benchmark_i2v.py and the Phase K report.
"""

from __future__ import annotations

import io
import threading
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.core.config import Settings
from app.main import create_app
from app.schemas.generation import ImageToVideoRequest
from app.services.generation_service import GenerationService
from app.services.upload_storage import UploadStorage
from tests.conftest import wait_for_status
from tests.fakes import FakeImageEngine, FakeVideoEngine

CREATE = "/api/v1/generations"
VALIDATE = "/api/v1/generations/validate"
UPLOAD = "/api/v1/uploads/images"


def image_bytes(fmt: str = "PNG", size: tuple[int, int] = (640, 360), mode: str = "RGB", exif_rotate: bool = False) -> bytes:
    img = Image.new(mode, size, (200, 30, 30) if mode == "RGB" else None)
    buf = io.BytesIO()
    if exif_rotate:
        exif = Image.Exif()
        exif[0x0112] = 6  # rotate 90° clockwise when displayed
        img.save(buf, format=fmt, exif=exif)
    else:
        img.save(buf, format=fmt)
    return buf.getvalue()


@pytest.fixture
def video_engine() -> FakeVideoEngine:
    return FakeVideoEngine()


@pytest.fixture
def vclient(settings: Settings, engine: FakeImageEngine, video_engine: FakeVideoEngine) -> Iterator[TestClient]:
    with TestClient(create_app(settings, engine=engine, video_engine=video_engine)) as test_client:
        yield test_client


def upload(client: TestClient, data: bytes | None = None, content_type: str = "image/png"):
    return client.post(UPLOAD, content=image_bytes() if data is None else data, headers={"Content-Type": content_type})


def i2v(upload_id: str, **overrides) -> dict:
    payload = {
        "mode": "image-to-video",
        "prompt": "The woman slowly turns her head and smiles",
        "aspect_ratio": "16:9",
        "source_image": {"upload_id": upload_id},
    }
    payload.update(overrides)
    return payload


# --- uploads --------------------------------------------------------------------------


@pytest.mark.parametrize("fmt,ctype", [("PNG", "image/png"), ("JPEG", "image/jpeg"), ("WEBP", "image/webp")])
def test_upload_accepts_png_jpeg_webp(vclient: TestClient, fmt: str, ctype: str) -> None:
    res = upload(vclient, image_bytes(fmt), ctype)
    assert res.status_code == 201, res.text
    body = res.json()
    assert (body["width"], body["height"], body["content_type"]) == (640, 360, ctype)


def test_upload_type_comes_from_the_bytes_not_the_header(vclient: TestClient) -> None:
    res = upload(vclient, image_bytes("JPEG"), "image/png")
    assert res.status_code == 201 and res.json()["content_type"] == "image/jpeg"


def test_upload_applies_exif_rotation_and_drops_metadata(vclient: TestClient, settings: Settings) -> None:
    res = upload(vclient, image_bytes("JPEG", (640, 360), exif_rotate=True), "image/jpeg")
    assert res.status_code == 201
    assert (res.json()["width"], res.json()["height"]) == (360, 640)
    with Image.open(settings.upload_dir / f"{res.json()['upload_id']}.png") as stored:
        assert stored.format == "PNG" and stored.mode == "RGB" and not stored.getexif()


def test_upload_flattens_transparency(vclient: TestClient) -> None:
    assert upload(vclient, image_bytes("PNG", (400, 400), mode="RGBA")).status_code == 201


@pytest.mark.parametrize(
    ("data", "status", "code"),
    [
        (b"", 422, "upload_empty"),
        (b"%PDF-1.4 not an image", 422, "upload_invalid_image"),
        (b"GIF89a" + b"\x00" * 100, 422, "upload_invalid_image"),
        (image_bytes("PNG")[:200], 422, "upload_corrupted"),
        (image_bytes("PNG", (200, 120)), 422, "upload_too_small"),
    ],
)
def test_upload_rejects_bad_files(vclient: TestClient, data: bytes, status: int, code: str) -> None:
    res = upload(vclient, data)
    assert res.status_code == status, res.text
    assert res.json()["error"]["code"] == code


def test_upload_rejects_gif_even_when_valid(vclient: TestClient) -> None:
    buf = io.BytesIO()
    Image.new("RGB", (400, 400)).save(buf, format="GIF")
    res = upload(vclient, buf.getvalue(), "image/gif")
    assert res.status_code == 415 and res.json()["error"]["code"] == "upload_unsupported_type"


def test_upload_over_10_mb_is_rejected_before_decoding(vclient: TestClient) -> None:
    res = upload(vclient, b"\x89PNG" + b"\x00" * (10 * 1024 * 1024 + 10))
    assert res.status_code == 413


def test_json_endpoints_keep_the_small_body_limit(vclient: TestClient) -> None:
    res = vclient.post(VALIDATE, content=b"{" + b" " * (70 * 1024) + b"}", headers={"Content-Type": "application/json"})
    assert res.status_code == 413


def test_old_uploads_are_swept(tmp_path) -> None:
    store = UploadStorage(tmp_path)
    stored = store.save(image_bytes())
    assert store.resolve(stored.id) is not None
    import time

    assert store.sweep(now=time.time() + 25 * 3600) == 1
    assert store.resolve(stored.id) is None
    assert store.resolve("../../etc/passwd") is None


# --- request settings ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({}, (576, 320, 49, 3, "draft")),
        ({"duration_seconds": 5, "resolution": "large"}, (832, 480, 81, 3, "draft")),
        ({"aspect_ratio": "9:16", "quality": "quality", "duration_seconds": 2}, (320, 576, 33, 20, "quality")),
    ],
)
def test_i2v_settings(vclient: TestClient, overrides: dict, expected: tuple) -> None:
    uid = upload(vclient).json()["upload_id"]
    res = vclient.post(VALIDATE, json=i2v(uid, **overrides))
    assert res.status_code == 200, res.text
    s = res.json()["settings"]
    assert (s["width"], s["height"], s["num_frames"], s["steps"], s["quality"]) == expected
    assert res.json()["generation_available"] is True


@pytest.mark.parametrize(
    ("field", "value"),
    [("duration_seconds", 8), ("resolution", "high"), ("quality", "ultra"), ("camera", "spin"), ("motion", "max"), ("steps", 20)],
)
def test_i2v_rejects_unsupported_settings(vclient: TestClient, field: str, value: object) -> None:
    res = vclient.post(VALIDATE, json=i2v("0b6f8a3e-1d2c-4f5a-9b7e-123456789abc", **{field: value}))
    assert res.status_code == 422


def test_i2v_prompt_adds_only_requested_motion_and_camera() -> None:
    base = dict(mode="image-to-video", prompt="Clouds drift across the sky", source_image={"upload_id": "0b6f8a3e-1d2c-4f5a-9b7e-123456789abc"})
    plain = GenerationService.i2v_prompt(ImageToVideoRequest(**base))
    assert plain.startswith("Clouds drift across the sky.")
    assert "camera" not in plain.lower()  # camera "none": no camera movement is invented
    assert "cinematic" not in plain and "film" not in plain  # style words would repaint the image
    zoom = GenerationService.i2v_prompt(ImageToVideoRequest(**base, camera="zoom_in", motion="subtle"))
    assert "zooms in" in zoom and "Subtle" in zoom
    assert "Keep the same people" in zoom


# --- jobs -------------------------------------------------------------------------------


def test_i2v_job_completes_with_the_uploaded_image(vclient: TestClient, video_engine: FakeVideoEngine, settings: Settings) -> None:
    uid = upload(vclient).json()["upload_id"]
    res = vclient.post(CREATE, json=i2v(uid, seed=7, camera="static"))
    assert res.status_code == 202, res.text
    job = wait_for_status(vclient, res.json()["id"], {"completed", "failed"})
    assert job["status"] == "completed", job
    assert job["video"]["num_frames"] == 49
    params = video_engine.calls[0]
    assert params.image_path == settings.upload_dir.resolve() / f"{uid}.png"
    assert params.seed == 7 and params.quality == "draft"
    assert "Static camera" in params.prompt
    assert job["plan"]["model_prompt"] == params.prompt


def test_i2v_unknown_upload_is_a_field_error(vclient: TestClient) -> None:
    res = vclient.post(CREATE, json=i2v("0b6f8a3e-1d2c-4f5a-9b7e-123456789abc"))
    assert res.status_code == 422
    assert res.json()["error"]["details"][0]["field"] == "source_image.upload_id"


def test_i2v_unavailable_when_vace_is_missing(vclient: TestClient, video_engine: FakeVideoEngine) -> None:
    video_engine.i2v_ready = False
    uid = upload(vclient).json()["upload_id"]
    assert vclient.post(CREATE, json=i2v(uid)).status_code == 503


def test_cancel_a_running_job_then_retry(vclient: TestClient, video_engine: FakeVideoEngine) -> None:
    video_engine.gate = threading.Event()
    uid = upload(vclient).json()["upload_id"]
    job_id = vclient.post(CREATE, json=i2v(uid)).json()["id"]
    assert video_engine.started.wait(5)
    res = vclient.post(f"{CREATE}/{job_id}/cancel")
    assert res.status_code == 200
    video_engine.gate.set()
    job = wait_for_status(vclient, job_id, {"completed", "failed"})
    assert job["status"] == "failed" and job["error"]["code"] == "cancelled"
    assert vclient.post(f"{CREATE}/{job_id}/cancel").status_code == 409  # already finished

    video_engine.gate = None
    res = vclient.post(f"{CREATE}/{job_id}/retry")
    assert res.status_code == 202, res.text
    job = wait_for_status(vclient, job_id, {"completed", "failed"})
    assert job["status"] == "completed" and job["error"] is None
    assert len(video_engine.calls) == 2 and video_engine.calls[0].seed == video_engine.calls[1].seed


def test_cancel_a_queued_job(vclient: TestClient, video_engine: FakeVideoEngine) -> None:
    video_engine.gate = threading.Event()
    uid = upload(vclient).json()["upload_id"]
    first = vclient.post(CREATE, json=i2v(uid)).json()["id"]
    assert video_engine.started.wait(5)
    second = vclient.post(CREATE, json=i2v(uid)).json()["id"]
    res = vclient.post(f"{CREATE}/{second}/cancel")
    assert res.json()["status"] == "failed" and res.json()["error"]["code"] == "cancelled"
    video_engine.gate.set()
    assert wait_for_status(vclient, first, {"completed", "failed"})["status"] == "completed"
    assert len(video_engine.calls) == 1  # the cancelled job never ran


def test_retry_only_failed_jobs(vclient: TestClient) -> None:
    uid = upload(vclient).json()["upload_id"]
    job_id = vclient.post(CREATE, json=i2v(uid)).json()["id"]
    wait_for_status(vclient, job_id, {"completed"})
    assert vclient.post(f"{CREATE}/{job_id}/retry").status_code == 409


def test_text_to_video_can_be_cancelled(vclient: TestClient, video_engine: FakeVideoEngine) -> None:
    video_engine.gate = threading.Event()
    job_id = vclient.post(CREATE, json={"mode": "text-to-video", "prompt": "Waves at sunset"}).json()["id"]
    assert video_engine.started.wait(5)
    vclient.post(f"{CREATE}/{job_id}/cancel")
    video_engine.gate.set()
    job = wait_for_status(vclient, job_id, {"completed", "failed"})
    assert job["error"]["code"] == "cancelled"


def test_cancel_cannot_be_overwritten_by_a_starting_worker(vclient: TestClient, video_engine: FakeVideoEngine) -> None:
    """Regression (browser test): a job cancelled while queued must never run afterwards."""
    from app.schemas.generation import GenerationStatus

    service = vclient.app.state.generation_service
    video_engine.gate = threading.Event()
    uid = upload(vclient).json()["upload_id"]
    first = vclient.post(CREATE, json=i2v(uid)).json()["id"]
    assert video_engine.started.wait(5)
    second = vclient.post(CREATE, json=i2v(uid)).json()["id"]
    vclient.post(f"{CREATE}/{second}/cancel")
    # The worker's start is a transition from "queued": it must refuse a cancelled job.
    assert service.store.transition(second, GenerationStatus.QUEUED, status=GenerationStatus.PROCESSING) is None
    video_engine.gate.set()
    wait_for_status(vclient, first, {"completed"})
    assert vclient.get(f"{CREATE}/{second}").json()["error"]["code"] == "cancelled"
