"""REAL model smoke test: runs the actual open-weight model. Not mocked.

Skipped by default. Run it explicitly once weights are downloaded:

    $env:AVS_RUN_REAL_INFERENCE = "1"; python -m pytest tests/test_real_inference.py -s

It uses the configured IMAGE_MODEL_ID / IMAGE_MODEL_CACHE_DIR / IMAGE_DEVICE.
"""

import os
import time

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageStat

from app.core.config import Settings
from app.main import create_app
from app.services.image_engine import DiffusersImageEngine

pytestmark = pytest.mark.skipif(
    os.environ.get("AVS_RUN_REAL_INFERENCE") != "1", reason="set AVS_RUN_REAL_INFERENCE=1 to run the real model"
)


def test_real_text_to_image_end_to_end(tmp_path) -> None:
    settings = Settings(image_output_dir=tmp_path / "outputs")  # real model config, temp outputs
    engine = DiffusersImageEngine(settings)
    engine.ensure_can_accept()  # fails clearly if libraries or weights are missing

    with TestClient(create_app(settings, engine=engine)) as client:
        payload = {"mode": "text-to-image", "prompt": "a red fox sitting in fresh snow", "aspect_ratio": "1:1", "seed": 42}
        res = client.post("/api/v1/generations", json=payload)
        assert res.status_code == 202, res.text
        job_id = res.json()["id"]

        started = time.monotonic()
        while True:
            job = client.get(f"/api/v1/generations/{job_id}").json()
            if job["status"] in ("completed", "failed"):
                break
            assert time.monotonic() - started < settings.image_timeout_seconds + 60, "real inference timed out"
            time.sleep(1)

        assert job["status"] == "completed", job["error"]
        elapsed = time.monotonic() - started
        png = client.get(job["image"]["url"])
        assert png.status_code == 200

    path = settings.image_output_dir / f"{job_id}.png"
    with Image.open(path) as img:
        img.load()
        assert img.size == (512, 512)
        # A real render has texture; a blank or failed image would have near-zero variance.
        assert max(ImageStat.Stat(img.convert("RGB")).stddev) > 5
    print(f"\nREAL inference OK on {job['device']} in {elapsed:.1f}s -> {path}")


def test_real_text_to_video_end_to_end(tmp_path) -> None:
    """Runs Wan2.1 for real (several minutes on an 8 GB GPU) at the smallest supported settings."""
    from app.services.video_engine import WanVideoEngine
    from app.services.video_storage import probe_mp4

    settings = Settings(image_output_dir=tmp_path / "outputs", video_output_dir=tmp_path / "videos")
    video_engine = WanVideoEngine(settings)
    video_engine.ensure_can_accept()  # fails clearly if libraries or weights are missing

    with TestClient(create_app(settings, video_engine=video_engine)) as client:
        payload = {"mode": "text-to-video", "prompt": "a cat walking across a sunny garden path", "seed": 42, "steps": 15}
        res = client.post("/api/v1/generations", json=payload)
        assert res.status_code == 202, res.text
        job_id = res.json()["id"]

        started = time.monotonic()
        while True:
            job = client.get(f"/api/v1/generations/{job_id}").json()
            if job["status"] in ("completed", "failed"):
                break
            assert time.monotonic() - started < settings.video_timeout_seconds, "video job did not finish"
            time.sleep(5)

        assert job["status"] == "completed", job["error"]
        video = job["video"]
        assert video["url"].endswith(".mp4") and video["num_frames"] == 33
        data = client.get(video["url"]).content
        assert len(data) == video["size_bytes"]

    path = settings.video_output_dir / f"{job_id}.mp4"
    width, height, frames, fps = probe_mp4(path)
    assert (width, height, frames, fps) == (576, 320, 33, 16.0)
