"""REAL model inference (not mocked). Skipped by default.

Run with:  python -m pytest -m real_inference
Requires PyTorch, Diffusers and downloaded weights.
"""

import time

import pytest
from PIL import Image

from app.core.config import Settings
from app.services.image_engine import DiffusersImageEngine, ImageParams
from app.services.image_store import ImageStore

pytestmark = pytest.mark.real_inference


def test_real_model_generates_a_valid_png(tmp_path) -> None:
    settings = Settings(image_output_dir=tmp_path)  # reads IMAGE_* from the environment/.env
    engine = DiffusersImageEngine(settings)
    status = engine.status()
    if not status.accepts_jobs:
        pytest.skip(f"model not usable here: {status.state}: {status.detail}")

    params = ImageParams(prompt="a red fox in fresh snow, photo", width=512, height=512, num_inference_steps=1, seed=1)
    generated = engine.generate(params, deadline=time.monotonic() + settings.image_generation_timeout_seconds)
    store = ImageStore(tmp_path)
    path = store.resolve(store.save(generated.image, (512, 512)))
    assert path is not None
    with Image.open(path) as img:
        assert img.format == "PNG" and img.size == (512, 512)
        low, high = img.convert("L").getextrema()
    assert low != high, "image is a single flat colour"
