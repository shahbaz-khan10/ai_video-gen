"""The real DiffusersImageEngine's cheap paths and configuration. No model is loaded here."""

import importlib.util

import pytest
from fastapi.testclient import TestClient

from app.core.config import BACKEND_DIR, Settings
from app.main import create_app
from app.schemas.generation import VisualStyle
from app.services.image_engine import STYLE_PROMPTS, DiffusersImageEngine, EngineError, build_prompt

AI_LIBS_INSTALLED = DiffusersImageEngine.libraries_installed()


def test_every_style_has_a_prompt_suffix() -> None:
    assert set(STYLE_PROMPTS) == set(VisualStyle)
    assert build_prompt("A fox", VisualStyle.ANIME).startswith("A fox, anime")


def test_image_settings_read_plain_env_names(monkeypatch) -> None:
    monkeypatch.setenv("IMAGE_MODEL_ID", "someone/other-model")
    monkeypatch.setenv("IMAGE_DEVICE", "cpu")
    monkeypatch.setenv("IMAGE_MAX_CONCURRENT_JOBS", "2")
    monkeypatch.setenv("IMAGE_OUTPUT_DIR", "custom/out")
    s = Settings(_env_file=None)
    assert s.image_model_id == "someone/other-model"
    assert s.image_device == "cpu"
    assert s.image_max_concurrent_jobs == 2
    assert s.image_output_dir == (BACKEND_DIR / "custom" / "out").resolve()  # relative to backend/


def test_invalid_device_rejected(monkeypatch) -> None:
    monkeypatch.setenv("IMAGE_DEVICE", "tpu")
    with pytest.raises(ValueError):
        Settings(_env_file=None)


def test_status_without_weights_never_loads(settings: Settings) -> None:
    engine = DiffusersImageEngine(settings)  # empty tmp cache dir
    status = engine.status()
    assert status.state in ("unavailable", "not_downloaded")
    assert engine._pipe is None


def test_ensure_can_accept_explains_what_is_missing(settings: Settings) -> None:
    engine = DiffusersImageEngine(settings)
    with pytest.raises(EngineError) as err:
        engine.ensure_can_accept()
    assert err.value.code in ("ai_libraries_missing", "model_not_downloaded")
    assert str(settings.image_model_cache_dir) not in err.value.message  # no local paths leak


def test_default_app_rejects_jobs_honestly_without_model(settings: Settings) -> None:
    with TestClient(create_app(settings)) as client:  # real engine, empty cache
        res = client.post("/api/v1/generations", json={"mode": "text-to-image", "prompt": "A fox"})
        ready = client.get("/api/v1/health/ready").json()
    assert res.status_code == 503
    assert res.json()["error"]["code"] in ("ai_libraries_missing", "model_not_downloaded")
    assert ready["checks"]["image_model"]["status"] in ("unavailable", "not_downloaded")


@pytest.mark.skipif(AI_LIBS_INSTALLED, reason="only meaningful when PyTorch/Diffusers are absent")
def test_reports_missing_libraries_when_torch_absent(settings: Settings) -> None:
    assert importlib.util.find_spec("torch") is None or importlib.util.find_spec("diffusers") is None
    assert DiffusersImageEngine(settings).status().state == "unavailable"


def _fake_hf_cache(cache_dir, model_id: str, files: dict[str, str]) -> None:
    """Lay out files the way huggingface_hub's cache does (refs/main -> snapshots/<rev>/...)."""
    repo = cache_dir / ("models--" + model_id.replace("/", "--"))
    (repo / "refs").mkdir(parents=True)
    (repo / "refs" / "main").write_text("abc123")
    for name, content in files.items():
        path = repo / "snapshots" / "abc123" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)


SD_INDEX = (
    '{"_class_name": "StableDiffusionPipeline", "safety_checker": [null, null],'
    ' "scheduler": ["diffusers", "EulerDiscreteScheduler"], "text_encoder": ["transformers", "CLIPTextModel"],'
    ' "tokenizer": ["transformers", "CLIPTokenizer"], "unet": ["diffusers", "UNet2DConditionModel"],'
    ' "vae": ["diffusers", "AutoencoderKL"]}'
)


@pytest.mark.skipif(importlib.util.find_spec("huggingface_hub") is None, reason="needs huggingface_hub")
def test_partial_download_is_not_reported_as_downloaded(settings: Settings) -> None:
    # model_index.json arrives first; the big weight files are still missing.
    _fake_hf_cache(settings.image_model_cache_dir, settings.image_model_id, {
        "model_index.json": SD_INDEX,
        "text_encoder/model.fp16.safetensors": "x",
        "vae/diffusion_pytorch_model.fp16.safetensors": "x",
    })
    assert DiffusersImageEngine(settings).weights_present() is False


@pytest.mark.skipif(importlib.util.find_spec("huggingface_hub") is None, reason="needs huggingface_hub")
def test_complete_download_is_reported_as_downloaded(settings: Settings) -> None:
    _fake_hf_cache(settings.image_model_cache_dir, settings.image_model_id, {
        "model_index.json": SD_INDEX,
        "text_encoder/model.fp16.safetensors": "x",
        "vae/diffusion_pytorch_model.fp16.safetensors": "x",
        "unet/diffusion_pytorch_model.fp16.safetensors": "x",
    })
    assert DiffusersImageEngine(settings).weights_present() is True
