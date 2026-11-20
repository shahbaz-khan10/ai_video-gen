"""Phase 2: ffmpeg Looks, the enhance pass and Ken Burns clips (real ffmpeg, no AI model)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.core.config import Settings
from app.main import create_app
from app.services import postprocess
from app.services.video_engine import write_mp4
from app.services.video_storage import probe_mp4
from tests.conftest import wait_for_status
from tests.fakes import FakeImageEngine, FakeVideoEngine
from tests.test_i2v import i2v, upload

CREATE = "/api/v1/generations"
VALIDATE = "/api/v1/generations/validate"


def clip(path: Path, frames: int = 17, size: tuple[int, int] = (96, 64)) -> Path:
    w, h = size
    write_mp4([np.full((h, w, 3), (i * 12) % 255, dtype=np.uint8) for i in range(frames)], path, fps=16)
    return path


@pytest.mark.parametrize("look", ["film", "documentary_bw", "sepia", "warm_commercial"])
def test_looks_keep_size_and_length(tmp_path: Path, look: str) -> None:
    path = clip(tmp_path / "a.mp4")
    assert postprocess.apply_look(path, look) >= 0
    w, h, n, _fps = probe_mp4(path)
    assert (w, h, n) == (96, 64, 17)


def test_documentary_look_is_grey(tmp_path: Path) -> None:
    import imageio.v3 as iio

    path = tmp_path / "c.mp4"
    write_mp4([np.full((64, 96, 3), (200, 40, 40), dtype=np.uint8)] * 9, path, fps=16)
    postprocess.apply_look(path, "documentary_bw")
    frame = iio.imread(path, index=4).astype(int)
    assert abs(frame[..., 0].mean() - frame[..., 2].mean()) < 4  # red and blue equal: no colour left


def test_no_look_does_nothing(tmp_path: Path) -> None:
    path = clip(tmp_path / "a.mp4")
    before = path.read_bytes()
    assert postprocess.apply_look(path, "none") == 0.0
    assert path.read_bytes() == before


def test_unknown_look_is_refused(tmp_path: Path) -> None:
    with pytest.raises(postprocess.PostprocessError):
        postprocess.apply_look(clip(tmp_path / "a.mp4"), "neon")


def test_enhance_doubles_the_size(tmp_path: Path) -> None:
    path = clip(tmp_path / "a.mp4")
    postprocess.enhance(path)
    w, h, n, _ = probe_mp4(path)
    assert (w, h, n) == (192, 128, 17)


@pytest.mark.parametrize("move", ["zoom_in", "zoom_out", "pan_left", "pan_right", "tilt_up", "orbit"])
def test_ken_burns_frames(tmp_path: Path, move: str) -> None:
    img = tmp_path / "p.png"
    Image.new("RGB", (320, 180), (10, 120, 200)).save(img)
    out = tmp_path / "kb.mp4"
    postprocess.ken_burns(img, out, 96, 64, 25, 24, move)
    w, h, n, fps = probe_mp4(out)
    assert (w, h, n, round(fps)) == (96, 64, 25, 24)


# --- through the API --------------------------------------------------------------------------------------------


@pytest.fixture
def video_engine() -> FakeVideoEngine:
    return FakeVideoEngine()


@pytest.fixture
def vclient(settings: Settings, engine: FakeImageEngine, video_engine: FakeVideoEngine) -> Iterator[TestClient]:
    with TestClient(create_app(settings, engine=engine, video_engine=video_engine)) as test_client:
        yield test_client


def test_ken_burns_settings(vclient: TestClient) -> None:
    uid = upload(vclient).json()["upload_id"]
    s = vclient.post(VALIDATE, json=i2v(uid, quality="kenburns", duration_seconds=5, camera="pan_left")).json()["settings"]
    assert (s["fps"], s["num_frames"], s["steps"]) == (24, 121, None)
    assert "no AI model" in s["model_id"] and s["camera"] == "pan_left"


def test_ken_burns_runs_without_the_video_model(vclient: TestClient, video_engine: FakeVideoEngine) -> None:
    video_engine.i2v_ready = False  # VACE weights missing: Ken Burns does not need them
    uid = upload(vclient).json()["upload_id"]
    res = vclient.post(CREATE, json=i2v(uid, quality="kenburns", duration_seconds=2, look="sepia"))
    assert res.status_code == 202, res.text
    job = wait_for_status(vclient, res.json()["id"], {"completed", "failed"}, timeout=30)
    assert job["status"] == "completed", job.get("error")
    assert job["video"]["num_frames"] == 49 and job["device"] == "cpu"
    assert not video_engine.calls


def test_look_and_enhance_reach_the_video(vclient: TestClient) -> None:
    res = vclient.post(CREATE, json={"mode": "text-to-video", "prompt": "Waves on a beach", "aspect_ratio": "16:9",
                                     "look": "film", "enhance": True})
    assert res.status_code == 202, res.text
    job = wait_for_status(vclient, res.json()["id"], {"completed", "failed"}, timeout=30)
    assert job["status"] == "completed", job.get("error")
    assert job["settings"]["look"] == "film" and job["settings"]["enhance"] is True
    assert (job["video"]["width"], job["video"]["height"]) == (192, 128)  # the fake's 96x64 frames, upscaled 2x
    assert job["notes"] == []


def test_failed_look_keeps_the_video_and_says_so(vclient: TestClient, monkeypatch) -> None:
    def broken(_path, _look):
        raise postprocess.PostprocessError("boom")

    monkeypatch.setattr(postprocess, "apply_look", broken)
    res = vclient.post(CREATE, json={"mode": "text-to-video", "prompt": "Waves", "aspect_ratio": "16:9", "look": "sepia"})
    job = wait_for_status(vclient, res.json()["id"], {"completed", "failed"}, timeout=30)
    assert job["status"] == "completed"
    assert job["notes"] and "sepia" in job["notes"][0]


def test_unknown_look_is_a_validation_error(vclient: TestClient) -> None:
    res = vclient.post(CREATE, json={"mode": "text-to-video", "prompt": "Waves", "aspect_ratio": "16:9", "look": "neon"})
    assert res.status_code == 422


def test_schema_looks_match_the_filters() -> None:
    from typing import get_args

    from app.schemas.generation import VideoLook

    assert set(get_args(VideoLook)) - {"none"} == set(postprocess.LOOK_FILTERS)
