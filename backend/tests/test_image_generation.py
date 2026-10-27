"""Text-to-image jobs, file delivery and engine status, all against a mocked engine (no GPU, no weights)."""

import io
import threading
import uuid

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.core.config import Settings
from app.main import create_app
from app.services.image_engine import DiffusersImageEngine, EngineError
from tests.conftest import FakeImageEngine, wait_for_job

CREATE = "/api/v1/generations"
FILES = "/api/v1/files/images"


def make_client(settings: Settings, engine: FakeImageEngine) -> TestClient:
    return TestClient(create_app(settings, engine=engine))


# --- validation -----------------------------------------------------------------


def test_validate_text_to_image_reports_size_steps_and_seed(gen_client: TestClient, image_request: dict) -> None:
    image_request.update(aspect_ratio="16:9", resolution=768, num_inference_steps=2, seed=42)
    res = gen_client.post(f"{CREATE}/validate", json=image_request)
    assert res.status_code == 200
    s = res.json()["settings"]
    assert (s["width"], s["height"], s["num_inference_steps"], s["seed"]) == (1024, 576, 2, 42)
    assert res.json()["generation_available"] is True


@pytest.mark.parametrize(
    ("ratio", "resolution", "size"),
    [("1:1", 512, (512, 512)), ("16:9", 512, (688, 384)), ("9:16", 512, (384, 688)), ("9:16", 768, (576, 1024))],
)
def test_sizes_follow_aspect_ratio_and_are_multiples_of_8(
    gen_client: TestClient, image_request: dict, ratio: str, resolution: int, size: tuple[int, int]
) -> None:
    image_request.update(aspect_ratio=ratio, resolution=resolution)
    s = gen_client.post(f"{CREATE}/validate", json=image_request).json()["settings"]
    assert (s["width"], s["height"]) == size
    assert s["width"] % 8 == 0 and s["height"] % 8 == 0


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("resolution", 1024),
        ("resolution", 256),
        ("resolution", "512px"),
        ("num_inference_steps", 0),
        ("num_inference_steps", 51),
        ("seed", -1),
        ("seed", 2**32),
        ("seed", "lucky"),
        ("width", 512),
        ("height", 512),
    ],
)
def test_invalid_image_settings_rejected(gen_client: TestClient, image_request: dict, field: str, value) -> None:
    image_request[field] = value
    res = gen_client.post(CREATE, json=image_request)
    assert res.status_code == 422
    assert field in {d["field"] for d in res.json()["error"]["details"]}


def test_steps_above_engine_limit_rejected(gen_client: TestClient, image_request: dict) -> None:
    image_request["num_inference_steps"] = 5  # schema allows it, IMAGE_MAX_STEPS (4) does not
    res = gen_client.post(CREATE, json=image_request)
    assert res.status_code == 422
    assert res.json()["error"]["details"][0]["field"] == "num_inference_steps"


def test_image_settings_not_allowed_on_video_modes(gen_client: TestClient, video_request: dict) -> None:
    video_request["seed"] = 1
    assert gen_client.post(CREATE, json=video_request).status_code == 422


@pytest.mark.parametrize("mode", ["text-to-video", "image-to-video"])
def test_video_modes_rejected_even_with_engine(gen_client: TestClient, fake_engine: FakeImageEngine, mode: str) -> None:
    payload = {"mode": mode, "prompt": "Waves", "duration_seconds": 4}
    if mode == "image-to-video":
        payload["source_image"] = {"content_type": "image/png", "size_bytes": 1000}
    res = gen_client.post(CREATE, json=payload)
    assert res.status_code == 501
    assert res.json()["error"]["code"] == "mode_not_supported"
    assert fake_engine.calls == []


# --- job lifecycle ----------------------------------------------------------------


def test_job_completes_with_real_saved_image(gen_client: TestClient, image_request: dict, settings: Settings) -> None:
    created = gen_client.post(CREATE, json=image_request)
    assert created.status_code == 202
    job = created.json()
    assert job["status"] in ("queued", "processing", "completed")
    assert isinstance(job["settings"]["seed"], int)  # a random seed is chosen and reported

    done = wait_for_job(gen_client, job["id"])
    assert done["status"] == "completed"
    assert done["error"] is None
    assert done["output_url"].startswith(f"{FILES}/") and done["output_url"].endswith(".png")
    assert done["result"]["width"] == 512 and done["result"]["seed"] == job["settings"]["seed"]
    assert done["started_at"] and done["completed_at"]

    filename = done["output_url"].rsplit("/", 1)[1]
    assert (settings.image_output_dir / filename).is_file()
    img = gen_client.get(done["output_url"])
    assert img.status_code == 200
    assert img.headers["content-type"] == "image/png"
    assert img.headers["x-content-type-options"] == "nosniff"
    assert Image.open(io.BytesIO(img.content)).size == (512, 512)


def test_status_moves_queued_to_processing_to_completed(
    settings: Settings, fake_engine: FakeImageEngine, image_request: dict
) -> None:
    fake_engine.gate = threading.Event()
    client = make_client(settings, fake_engine)
    job_id = client.post(CREATE, json=image_request).json()["id"]

    assert fake_engine.started.wait(timeout=5)
    processing = client.get(f"{CREATE}/{job_id}").json()
    assert processing["status"] == "processing"
    assert processing["output_url"] is None  # no URL before the image exists

    fake_engine.gate.set()
    assert wait_for_job(client, job_id)["status"] == "completed"


def test_second_job_waits_in_queue_while_first_runs(
    settings: Settings, fake_engine: FakeImageEngine, image_request: dict
) -> None:
    fake_engine.gate = threading.Event()
    client = make_client(settings, fake_engine)
    first = client.post(CREATE, json=image_request).json()["id"]
    assert fake_engine.started.wait(timeout=5)
    second = client.post(CREATE, json=image_request).json()["id"]
    # One worker (IMAGE_MAX_CONCURRENT_JOBS=1): the second job stays queued.
    assert client.get(f"{CREATE}/{second}").json()["status"] == "queued"
    fake_engine.gate.set()
    assert wait_for_job(client, first)["status"] == "completed"
    assert wait_for_job(client, second)["status"] == "completed"


def test_every_job_gets_a_unique_file(gen_client: TestClient, image_request: dict, settings: Settings) -> None:
    image_request["seed"] = 7
    urls = {wait_for_job(gen_client, gen_client.post(CREATE, json=image_request).json()["id"])["output_url"] for _ in range(3)}
    assert len(urls) == 3
    assert len(list(settings.image_output_dir.glob("*.png"))) == 3


def test_seed_steps_and_style_reach_the_engine(gen_client: TestClient, fake_engine: FakeImageEngine, image_request: dict) -> None:
    image_request.update(seed=1234, num_inference_steps=3, style="anime", resolution=768, aspect_ratio="9:16")
    wait_for_job(gen_client, gen_client.post(CREATE, json=image_request).json()["id"])
    params = fake_engine.calls[0]
    assert (params.seed, params.num_inference_steps, params.width, params.height) == (1234, 3, 576, 1024)
    assert params.prompt.startswith("anime illustration") and params.prompt.endswith("A red fox in fresh snow")


@pytest.mark.parametrize(
    ("error", "code"),
    [
        (EngineError("gpu_out_of_memory", "The GPU ran out of memory."), "gpu_out_of_memory"),
        (EngineError("model_unavailable", "The model weights are missing."), "model_unavailable"),
        (EngineError("cuda_unavailable", "No CUDA GPU."), "cuda_unavailable"),
        (EngineError("generation_timeout", "Too slow."), "generation_timeout"),
    ],
)
def test_engine_errors_fail_the_job_honestly(
    settings: Settings, image_request: dict, error: EngineError, code: str
) -> None:
    client = make_client(settings, FakeImageEngine(fail=error))
    job = wait_for_job(client, client.post(CREATE, json=image_request).json()["id"])
    assert job["status"] == "failed"
    assert job["error_code"] == code
    assert job["error"] == error.message
    assert job["output_url"] is None and job["result"] is None
    assert not settings.image_output_dir.exists() or not any(settings.image_output_dir.iterdir())


def test_unexpected_exception_hides_internals(settings: Settings, image_request: dict) -> None:
    secret = r"C:\Users\someone\.cache\huggingface\token=abc"
    client = make_client(settings, FakeImageEngine(fail=RuntimeError(secret)))
    job = wait_for_job(client, client.post(CREATE, json=image_request).json()["id"])
    assert job["status"] == "failed"
    assert job["error_code"] == "generation_failed"
    assert "huggingface" not in str(job) and "Traceback" not in str(job)


def test_wrong_image_size_is_not_saved(settings: Settings, image_request: dict) -> None:
    client = make_client(settings, FakeImageEngine(size=(64, 64)))
    job = wait_for_job(client, client.post(CREATE, json=image_request).json()["id"])
    assert job["status"] == "failed"
    assert job["error_code"] == "image_save_failed"
    assert job["output_url"] is None


def test_save_failure_reports_image_save_failed(tmp_path, image_request: dict) -> None:
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("x")
    settings = Settings(_env_file=None, environment="test", image_engine="none", image_output_dir=blocker)
    client = make_client(settings, FakeImageEngine())
    job = wait_for_job(client, client.post(CREATE, json=image_request).json()["id"])
    assert job["error_code"] == "image_save_failed"
    assert str(tmp_path) not in job["error"]


def test_queue_limit_returns_429(settings: Settings, fake_engine: FakeImageEngine, image_request: dict) -> None:
    fake_engine.gate = threading.Event()
    client = make_client(settings.model_copy(update={"image_max_queued_jobs": 2}), fake_engine)
    assert client.post(CREATE, json=image_request).status_code == 202
    assert client.post(CREATE, json=image_request).status_code == 202
    res = client.post(CREATE, json=image_request)
    assert res.status_code == 429
    assert res.json()["error"]["code"] == "queue_full"
    fake_engine.gate.set()


@pytest.mark.parametrize(
    ("state", "status", "code"),
    [
        ("weights_missing", 503, "model_not_downloaded"),
        ("not_installed", 503, "engine_not_installed"),
        ("disabled", 501, "engine_not_configured"),
    ],
)
def test_unavailable_engine_rejects_before_queueing(
    settings: Settings, image_request: dict, state: str, status: int, code: str
) -> None:
    engine = FakeImageEngine(state=state)
    client = make_client(settings, engine)
    res = client.post(CREATE, json=image_request)
    assert res.status_code == status
    assert res.json()["error"]["code"] == code
    assert engine.calls == []


def test_unknown_job_404_mentions_restart(gen_client: TestClient) -> None:
    res = gen_client.get(f"{CREATE}/{uuid.uuid4()}")
    assert res.status_code == 404
    assert "restart" in res.json()["error"]["message"]


# --- file delivery and path safety -------------------------------------------------


def test_download_flag_sets_attachment(gen_client: TestClient, image_request: dict) -> None:
    url = wait_for_job(gen_client, gen_client.post(CREATE, json=image_request).json()["id"])["output_url"]
    res = gen_client.get(f"{url}?download=true")
    assert res.status_code == 200
    assert res.headers["content-disposition"].startswith("attachment")


@pytest.mark.parametrize(
    "name",
    [
        "..%2F..%2F.env",
        "..%5C..%5C.env",
        "%2E%2E%2Fapp%2Fmain.py",
        ".env",
        "model_index.json",
        "0123456789abcdef0123456789abcdef.jpg",
        "0123456789ABCDEF0123456789ABCDEF.png",
        "0123456789abcdef0123456789abcdef.png.tmp",
        "C:%5CWindows%5Cwin.ini",
    ],
)
def test_file_route_rejects_anything_but_generated_names(gen_client: TestClient, name: str) -> None:
    res = gen_client.get(f"{FILES}/{name}")
    assert res.status_code in (404, 422)
    assert res.headers["content-type"].startswith("application/json")


def test_well_formed_but_missing_image_is_404(gen_client: TestClient) -> None:
    res = gen_client.get(f"{FILES}/{uuid.uuid4().hex}.png")
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "image_not_found"


def test_files_outside_output_dir_are_never_served(gen_client: TestClient, settings: Settings) -> None:
    outside = settings.image_output_dir.parent / f"{uuid.uuid4().hex}.png"
    Image.new("RGB", (8, 8)).save(outside)
    assert gen_client.get(f"{FILES}/{outside.name}").status_code == 404
    assert gen_client.get(f"{FILES}/..%2F{outside.name}").status_code in (404, 422)


# --- readiness and engine status ----------------------------------------------------


def test_ready_reports_model_separately(gen_client: TestClient, fake_engine: FakeImageEngine) -> None:
    body = gen_client.get("/api/v1/health/ready").json()
    assert body["ready"] is True
    assert body["model"]["state"] == "ready"
    assert body["model"]["model_id"] == "fake/model"
    assert body["checks"]["generation_engine"]["status"] == "ok"
    assert fake_engine.calls == []  # readiness never runs the model


def test_ready_and_info_when_weights_missing(settings: Settings) -> None:
    client = make_client(settings, FakeImageEngine(state="weights_missing"))
    ready = client.get("/api/v1/health/ready").json()
    assert ready["ready"] is True  # the API itself is fine
    assert ready["model"]["accepts_jobs"] is False
    assert ready["checks"]["generation_engine"]["status"] == "not_configured"
    info = client.get("/api/v1/info").json()
    assert info["generation"]["available"] is False
    assert info["generation"]["available_modes"] == []


def test_info_lists_image_limits(gen_client: TestClient) -> None:
    info = gen_client.get("/api/v1/info").json()
    assert info["generation"]["available_modes"] == ["text-to-image"]
    assert info["limits"]["image_resolutions"] == [512, 768]
    assert info["limits"]["image_max_steps"] == 4


def _engine(settings: Settings, monkeypatch, *, installed: bool, device: str | None, cached: bool) -> DiffusersImageEngine:
    engine = DiffusersImageEngine(settings.model_copy(update={"image_engine": "diffusers"}))
    monkeypatch.setattr(engine, "_probe", lambda: (installed, device))
    monkeypatch.setattr(engine, "weights_cached", lambda: cached)
    return engine


def test_diffusers_engine_status_without_libraries(settings: Settings, monkeypatch) -> None:
    assert _engine(settings, monkeypatch, installed=False, device=None, cached=False).status().state == "not_installed"


def test_diffusers_engine_status_without_weights(settings: Settings, monkeypatch) -> None:
    status = _engine(settings, monkeypatch, installed=True, device="cuda", cached=False).status()
    assert status.state == "weights_missing"
    assert not status.accepts_jobs


def test_diffusers_engine_status_cuda_requested_but_missing(settings: Settings, monkeypatch) -> None:
    status = _engine(settings, monkeypatch, installed=True, device=None, cached=True).status()
    assert status.state == "error"
    assert "CUDA" in status.detail


def test_diffusers_engine_is_lazy(settings: Settings, monkeypatch) -> None:
    engine = _engine(settings, monkeypatch, installed=True, device="cuda", cached=True)
    client = make_client(settings, engine)
    assert client.get("/api/v1/health/ready").json()["model"]["state"] == "not_loaded"
    assert engine._pipe is None  # health checks and app start-up never load the model


def test_diffusers_engine_load_failure_is_reported(settings: Settings, monkeypatch, image_request: dict) -> None:
    engine = _engine(settings, monkeypatch, installed=True, device="cuda", cached=True)

    def broken_build(device: str):
        raise EngineError("model_unavailable", "The model weights are missing or incomplete.")

    monkeypatch.setattr(engine, "_build_pipeline", broken_build)
    client = make_client(settings, engine)
    job = wait_for_job(client, client.post(CREATE, json=image_request).json()["id"])
    assert job["error_code"] == "model_unavailable"
    assert client.get("/api/v1/health/ready").json()["model"]["state"] == "error"


def test_torch_that_fails_to_load_is_reported_not_crashing(settings: Settings, monkeypatch, image_request: dict) -> None:
    import builtins

    import app.services.image_engine as image_engine

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "torch":
            raise OSError("[WinError 126] Error loading c10.dll or one of its dependencies.")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(image_engine, "_deps_installed", lambda: True)
    monkeypatch.setattr(builtins, "__import__", fake_import)
    engine = DiffusersImageEngine(settings.model_copy(update={"image_engine": "diffusers"}))
    client = make_client(settings, engine)

    ready = client.get("/api/v1/health/ready")
    assert ready.status_code == 200
    model = ready.json()["model"]
    assert model["state"] == "not_installed"
    assert "Visual C++" in model["detail"]
    assert "c10.dll" not in ready.text  # the raw error stays in the server log
    assert client.post(CREATE, json=image_request).json()["error"]["code"] == "engine_not_installed"
