"""Text-to-image jobs and file delivery, using the MOCKED engine (tests/fakes.py).

These prove the API, queue and storage logic. They do not run a real model; see
tests/test_real_inference.py for that.
"""

import threading
import uuid

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.core.config import Settings
from app.main import create_app
from app.services.image_engine import EngineError
from tests.conftest import wait_for_status
from tests.fakes import FakeImageEngine

CREATE = "/api/v1/generations"


# --- creation and status transitions -------------------------------------------------


def test_create_returns_202_queued_job(client: TestClient, engine: FakeImageEngine, image_request: dict) -> None:
    engine.gate = threading.Event()  # hold the worker so the initial state is observable
    res = client.post(CREATE, json=image_request)
    assert res.status_code == 202
    job = res.json()
    uuid.UUID(job["id"])
    assert job["status"] in ("queued", "processing")
    assert job["image"] is None and job["error"] is None
    assert job["model_id"] == "test/fake-model"
    engine.gate.set()


def test_job_goes_queued_processing_completed(client: TestClient, engine: FakeImageEngine, image_request: dict) -> None:
    engine.gate = threading.Event()
    job_id = client.post(CREATE, json=image_request).json()["id"]

    assert engine.started.wait(5)
    processing = client.get(f"{CREATE}/{job_id}").json()
    assert processing["status"] == "processing"
    assert processing["started_at"] is not None
    assert processing["image"] is None  # no URL before the file exists

    engine.gate.set()
    done = wait_for_status(client, job_id, {"completed"})
    assert done["finished_at"] is not None
    assert done["device"] == "cpu"
    image = done["image"]
    assert image["url"] == f"/api/v1/files/images/{job_id}.png"
    assert image["download_url"].endswith("?download=true")
    assert (image["width"], image["height"]) == (512, 512)
    assert image["size_bytes"] > 0


def test_completed_image_exists_and_opens(client: TestClient, image_request: dict, settings: Settings) -> None:
    job_id = client.post(CREATE, json=image_request).json()["id"]
    done = wait_for_status(client, job_id, {"completed"})
    path = settings.image_output_dir / f"{job_id}.png"
    assert path.is_file()
    with Image.open(path) as img:
        assert img.format == "PNG"
        assert img.size == (done["image"]["width"], done["image"]["height"])


def test_random_seed_is_assigned_and_reported(client: TestClient, engine: FakeImageEngine, image_request: dict) -> None:
    job = client.post(CREATE, json=image_request).json()
    assert isinstance(job["settings"]["seed"], int)
    wait_for_status(client, job["id"], {"completed"})
    assert engine.calls[0].seed == job["settings"]["seed"]


def test_explicit_settings_reach_the_engine(client: TestClient, engine: FakeImageEngine) -> None:
    payload = {
        "mode": "text-to-image",
        "prompt": "A neon alley in the rain",
        "aspect_ratio": "16:9",
        "style": "neon-noir",
        "resolution": "large",
        "steps": 4,
        "seed": 1234,
    }
    job_id = client.post(CREATE, json=payload).json()["id"]
    wait_for_status(client, job_id, {"completed"})
    params = engine.calls[0]
    assert (params.width, params.height, params.steps, params.seed) == (1024, 576, 4, 1234)
    assert params.style == "neon-noir"


@pytest.mark.parametrize(
    ("ratio", "resolution", "size"),
    [("1:1", "standard", (512, 512)), ("16:9", "standard", (680, 384)), ("9:16", "large", (576, 1024))],
)
def test_validate_reports_server_chosen_dimensions(client: TestClient, ratio: str, resolution: str, size) -> None:
    payload = {"mode": "text-to-image", "prompt": "A fox", "aspect_ratio": ratio, "resolution": resolution}
    settings = client.post(f"{CREATE}/validate", json=payload).json()["settings"]
    assert (settings["width"], settings["height"]) == size


def test_jobs_run_one_at_a_time_by_default(client: TestClient, engine: FakeImageEngine, image_request: dict) -> None:
    engine.gate = threading.Event()
    first = client.post(CREATE, json=image_request).json()["id"]
    assert engine.started.wait(5)
    second = client.post(CREATE, json=image_request).json()["id"]

    waiting = client.get(f"{CREATE}/{second}").json()
    assert waiting["status"] == "queued"
    assert waiting["queue_position"] == 1
    assert len(engine.calls) == 1  # the second job has not started

    engine.gate.set()
    wait_for_status(client, first, {"completed"})
    wait_for_status(client, second, {"completed"})
    assert len(engine.calls) == 2


def test_queue_full_returns_429(settings: Settings, image_request: dict) -> None:
    engine = FakeImageEngine()
    engine.gate = threading.Event()
    app = create_app(settings.model_copy(update={"image_max_queued_jobs": 1}), engine=engine)
    with TestClient(app) as client:
        assert client.post(CREATE, json=image_request).status_code == 202  # running
        assert client.post(CREATE, json=image_request).status_code == 202  # queued
        res = client.post(CREATE, json=image_request)
        assert res.status_code == 429
        assert res.json()["error"]["code"] == "queue_full"
        engine.gate.set()


# --- unsupported modes and unavailable engine ------------------------------------------


def test_image_to_video_returns_501(client: TestClient) -> None:
    payload = {
        "mode": "image-to-video",
        "prompt": "Make it move",
        "source_image": {"content_type": "image/png", "size_bytes": 1000},
    }
    res = client.post(CREATE, json=payload)
    assert res.status_code == 501
    assert res.json()["error"]["code"] == "mode_not_available"


@pytest.mark.parametrize(
    ("code", "message"),
    [
        ("ai_libraries_missing", "The server is missing the AI libraries."),
        ("model_not_downloaded", "The model weights are not downloaded yet."),
    ],
)
def test_missing_libraries_or_weights_return_503_without_queuing(
    client: TestClient, engine: FakeImageEngine, image_request: dict, code: str, message: str
) -> None:
    engine.can_accept_error = EngineError(code, message)
    res = client.post(CREATE, json=image_request)
    assert res.status_code == 503
    assert res.json()["error"] == {"code": code, "message": message}
    assert engine.calls == []


def test_generation_disabled_returns_501(settings: Settings, image_request: dict) -> None:
    with TestClient(create_app(settings, engine=None)) as client:
        res = client.post(CREATE, json=image_request)
    assert res.status_code == 501
    assert res.json()["error"]["code"] == "engine_not_configured"


def test_unsupported_image_settings_rejected(client: TestClient, image_request: dict) -> None:
    for field, value in [("steps", 3), ("steps", 50), ("resolution", "4k"), ("seed", -1), ("seed", 2**32)]:
        res = client.post(CREATE, json={**image_request, field: value})
        assert res.status_code == 422, (field, value)
        assert field in {d["field"] for d in res.json()["error"]["details"]}


def test_client_cannot_set_pixel_dimensions(client: TestClient, image_request: dict) -> None:
    res = client.post(CREATE, json={**image_request, "width": 4096, "height": 4096})
    assert res.status_code == 422


# --- failures ------------------------------------------------------------------------


@pytest.mark.parametrize(
    "error",
    [
        EngineError("gpu_out_of_memory", "The GPU ran out of memory.", retryable=True),
        EngineError("cuda_unavailable", "PyTorch cannot see a CUDA GPU."),
        EngineError("model_load_failed", "The image model failed to load.", retryable=True),
        EngineError("generation_timeout", "Generation took too long and was stopped.", retryable=True),
    ],
)
def test_engine_errors_fail_the_job_with_safe_message(
    client: TestClient, engine: FakeImageEngine, image_request: dict, error: EngineError
) -> None:
    engine.generate_error = error
    job_id = client.post(CREATE, json=image_request).json()["id"]
    failed = wait_for_status(client, job_id, {"failed"})
    assert failed["error"] == {"code": error.code, "message": error.message, "retryable": error.retryable}
    assert failed["image"] is None


def test_unexpected_exception_hides_internals(
    client: TestClient, engine: FakeImageEngine, image_request: dict, settings: Settings
) -> None:
    engine.generate_error = RuntimeError(f"boom at {settings.image_model_cache_dir}\\secret.safetensors")
    job_id = client.post(CREATE, json=image_request).json()["id"]
    failed = wait_for_status(client, job_id, {"failed"})
    assert failed["error"]["code"] == "generation_failed"
    text = client.get(f"{CREATE}/{job_id}").text
    assert "boom" not in text and "safetensors" not in text and "Traceback" not in text


def test_save_failure_fails_job_and_leaves_no_file(
    client: TestClient, image_request: dict, settings: Settings, monkeypatch
) -> None:
    def broken_save(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(Image.Image, "save", broken_save)
    job_id = client.post(CREATE, json=image_request).json()["id"]
    failed = wait_for_status(client, job_id, {"failed"})
    assert failed["error"]["code"] == "image_save_failed"
    assert failed["image"] is None
    assert not list(settings.image_output_dir.glob("*")) if settings.image_output_dir.exists() else True


def test_unknown_job_returns_404(client: TestClient) -> None:
    res = client.get(f"{CREATE}/{uuid.uuid4()}")
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "generation_not_found"


# --- file delivery and path safety ---------------------------------------------------


def test_generated_image_is_served_inline_and_as_download(client: TestClient, image_request: dict) -> None:
    job_id = client.post(CREATE, json=image_request).json()["id"]
    image = wait_for_status(client, job_id, {"completed"})["image"]

    inline = client.get(image["url"])
    assert inline.status_code == 200
    assert inline.headers["content-type"] == "image/png"
    assert inline.headers["x-content-type-options"] == "nosniff"
    assert inline.content.startswith(b"\x89PNG")

    download = client.get(image["download_url"])
    assert download.status_code == 200
    assert download.headers["content-disposition"].startswith("attachment;")


@pytest.mark.parametrize(
    "name",
    [
        "..%2F..%2F.env",
        "..%5C..%5Capp%5Cmain.py",
        "%2E%2E%2Frequirements.txt",
        "not-a-uuid.png",
        f"{uuid.uuid4()}.jpg",
        f"{uuid.uuid4()}.png.exe",
        f"{str(uuid.uuid4()).upper()}.png",
        ".env",
    ],
)
def test_file_route_rejects_anything_but_generated_names(client: TestClient, name: str) -> None:
    res = client.get(f"/api/v1/files/images/{name}")
    assert res.status_code == 404
    assert "error" in res.json()


def test_file_route_404s_for_valid_name_that_does_not_exist(client: TestClient) -> None:
    res = client.get(f"/api/v1/files/images/{uuid.uuid4()}.png")
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "file_not_found"


def test_file_route_cannot_reach_files_outside_output_dir(client: TestClient, settings: Settings) -> None:
    # A real PNG with a valid-looking name, but next to (not inside) the output directory.
    outside = settings.image_output_dir.parent / f"{uuid.uuid4()}.png"
    outside.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (8, 8)).save(outside)
    res = client.get(f"/api/v1/files/images/..%2F{outside.name}")
    assert res.status_code == 404


# --- model status and preloading -----------------------------------------------------


def test_model_status_does_not_load(client: TestClient, engine: FakeImageEngine) -> None:
    body = client.get("/api/v1/models/image").json()
    assert body["state"] == "not_loaded"
    assert body["can_generate"] is True
    assert engine.loaded is False


def test_preload_loads_model_in_background(client: TestClient, engine: FakeImageEngine) -> None:
    assert client.post("/api/v1/models/image/load").status_code == 202
    for _ in range(200):
        if client.get("/api/v1/models/image").json()["state"] == "loaded":
            break
        threading.Event().wait(0.02)
    assert engine.loaded is True


def test_preload_without_weights_returns_503(client: TestClient, engine: FakeImageEngine) -> None:
    engine.can_accept_error = EngineError("model_not_downloaded", "Weights missing.")
    res = client.post("/api/v1/models/image/load")
    assert res.status_code == 503
    assert res.json()["error"]["code"] == "model_not_downloaded"


def test_job_records_the_model_that_actually_runs(client: TestClient, engine: FakeImageEngine) -> None:
    payload = {"mode": "text-to-image", "prompt": "a red fox in snow", "model_id": "stabilityai/sd-turbo"}
    job = client.post(CREATE, json=payload).json()
    assert job["settings"]["model_id"] == engine.model_id
