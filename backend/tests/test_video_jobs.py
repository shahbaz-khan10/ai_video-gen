"""Text-to-video: validation, job lifecycle, output validation and video serving.

All of these use FakeVideoEngine (a real but tiny MP4, no AI model). Real Wan2.1 inference is in
test_real_inference.py and runs only with `-m real_inference`.
"""

from __future__ import annotations

import threading
import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.services.video_engine import VideoEngineError
from tests.conftest import wait_for_status
from tests.fakes import FakeImageEngine, FakeVideoEngine

CREATE = "/api/v1/generations"
VALIDATE = "/api/v1/generations/validate"
VIDEOS = "/api/v1/files/videos"


@pytest.fixture
def video_engine() -> FakeVideoEngine:
    return FakeVideoEngine()


@pytest.fixture
def vclient(settings: Settings, engine: FakeImageEngine, video_engine: FakeVideoEngine) -> Iterator[TestClient]:
    with TestClient(create_app(settings, engine=engine, video_engine=video_engine)) as test_client:
        yield test_client


def video(**overrides) -> dict:
    payload = {"mode": "text-to-video", "prompt": "Waves rolling onto a beach at sunset", "aspect_ratio": "16:9"}
    payload.update(overrides)
    return payload


# --- validation -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({}, (576, 320, 33, 25)),
        ({"duration_seconds": 3}, (576, 320, 49, 25)),
        ({"duration_seconds": 5, "resolution": "large"}, (832, 480, 81, 25)),
        ({"aspect_ratio": "9:16", "resolution": "large", "steps": 40}, (480, 832, 33, 40)),
        ({"aspect_ratio": "1:1", "num_frames": 49}, (416, 416, 49, 25)),
    ],
)
def test_video_settings_follow_the_model(vclient: TestClient, overrides: dict, expected: tuple) -> None:
    res = vclient.post(VALIDATE, json=video(**overrides))
    assert res.status_code == 200, res.text
    s = res.json()["settings"]
    assert (s["width"], s["height"], s["num_frames"], s["steps"]) == expected
    assert s["fps"] == 16 and s["model_id"] == "test/fake-video-model"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("resolution", "high"),  # 720p is unstable on Wan 1.3B and not offered
        ("steps", 5),
        ("steps", 51),
        ("num_frames", 34),  # Wan needs 4k+1 frames
        ("num_frames", 85),  # more than the model's 81
        ("duration_seconds", 8),
        ("seed", -1),
    ],
)
def test_unsupported_video_settings_are_rejected(vclient: TestClient, field: str, value) -> None:
    res = vclient.post(CREATE, json=video(**{field: value}))
    assert res.status_code == 422
    assert field in {d["field"] for d in res.json()["error"]["details"]}


@pytest.mark.parametrize("field", ["motion", "fps", "camera", "guidance_scale", "negative_prompt"])
def test_settings_the_model_does_not_take_are_rejected(vclient: TestClient, field: str) -> None:
    assert vclient.post(CREATE, json=video(**{field: 1})).status_code == 422


def test_image_to_video_is_still_not_available(vclient: TestClient) -> None:
    payload = {
        "mode": "image-to-video",
        "prompt": "Make it move",
        "source_image": {"content_type": "image/png", "size_bytes": 1000},
    }
    assert vclient.post(CREATE, json=payload).status_code == 501


# --- job lifecycle ------------------------------------------------------------------


def test_video_job_completes_with_a_real_decoded_mp4(
    vclient: TestClient, video_engine: FakeVideoEngine, settings: Settings
) -> None:
    created = vclient.post(CREATE, json=video(seed=7))
    assert created.status_code == 202
    job = created.json()
    assert job["status"] in ("queued", "processing")
    assert job["video"] is None and job["output_url"] is None

    done = wait_for_status(vclient, job["id"], {"completed", "failed"})
    assert done["status"] == "completed", done["error"]
    v = done["video"]
    # Metadata comes from decoding the file, not from what was requested.
    assert (v["width"], v["height"], v["num_frames"]) == (96, 64, 33)
    assert v["duration_seconds"] == pytest.approx(33 / 16, abs=0.01)
    assert v["url"] == f"{VIDEOS}/{job['id']}.mp4" and done["output_url"] == v["url"]
    assert (settings.video_output_dir / f"{job['id']}.mp4").is_file()
    assert video_engine.calls[0].seed == 7

    res = vclient.get(v["url"])
    assert res.status_code == 200
    assert res.headers["content-type"] == "video/mp4"
    assert res.content[4:8] == b"ftyp"  # an MP4 container
    assert len(res.content) == v["size_bytes"]


def test_video_supports_range_requests_for_seeking(vclient: TestClient) -> None:
    job = wait_for_status(vclient, vclient.post(CREATE, json=video()).json()["id"], {"completed"})
    res = vclient.get(job["video"]["url"], headers={"Range": "bytes=0-99"})
    assert res.status_code == 206
    assert len(res.content) == 100


def test_video_download_is_an_attachment(vclient: TestClient) -> None:
    job = wait_for_status(vclient, vclient.post(CREATE, json=video()).json()["id"], {"completed"})
    res = vclient.get(job["video"]["download_url"])
    assert res.status_code == 200
    assert res.headers["content-disposition"].startswith("attachment")


def test_status_moves_from_processing_to_completed(vclient: TestClient, video_engine: FakeVideoEngine) -> None:
    video_engine.gate = threading.Event()
    job_id = vclient.post(CREATE, json=video()).json()["id"]
    assert video_engine.started.wait(timeout=5)
    processing = vclient.get(f"{CREATE}/{job_id}").json()
    assert processing["status"] == "processing"
    assert processing["video"] is None and processing["output_url"] is None
    video_engine.gate.set()
    assert wait_for_status(vclient, job_id, {"completed"})["video"] is not None


def test_engine_failure_fails_the_job_without_a_file(
    vclient: TestClient, video_engine: FakeVideoEngine, settings: Settings
) -> None:
    video_engine.generate_error = VideoEngineError("gpu_out_of_memory", "The GPU ran out of memory.", retryable=True)
    job = wait_for_status(vclient, vclient.post(CREATE, json=video()).json()["id"], {"completed", "failed"})
    assert job["status"] == "failed"
    assert job["error"] == {"code": "gpu_out_of_memory", "message": "The GPU ran out of memory.", "retryable": True}
    assert job["video"] is None and job["output_url"] is None
    assert not settings.video_output_dir.exists() or not any(settings.video_output_dir.iterdir())


def test_undecodable_output_is_never_reported_as_success(
    vclient: TestClient, video_engine: FakeVideoEngine, settings: Settings
) -> None:
    video_engine.output = "garbage"
    job = wait_for_status(vclient, vclient.post(CREATE, json=video()).json()["id"], {"completed", "failed"})
    assert job["status"] == "failed"
    assert job["error"]["code"] == "video_invalid"
    assert vclient.get(f"{VIDEOS}/{job['id']}.mp4").status_code == 404
    assert not any(settings.video_output_dir.iterdir())  # the temporary file was removed


def test_unexpected_errors_hide_internals(vclient: TestClient, video_engine: FakeVideoEngine) -> None:
    video_engine.generate_error = RuntimeError("/app/models/secret/path exploded")
    job = wait_for_status(vclient, vclient.post(CREATE, json=video()).json()["id"], {"failed"})
    assert job["error"]["code"] == "generation_failed"
    assert "/app" not in job["error"]["message"]


def test_missing_weights_refuse_without_queuing(vclient: TestClient, video_engine: FakeVideoEngine) -> None:
    video_engine.can_accept_error = VideoEngineError("model_not_downloaded", "Video weights are not downloaded.")
    res = vclient.post(CREATE, json=video())
    assert res.status_code == 503
    assert res.json()["error"]["code"] == "model_not_downloaded"
    assert video_engine.calls == []


def test_unknown_video_job_returns_404(vclient: TestClient) -> None:
    res = vclient.get(f"{CREATE}/{uuid.uuid4()}")
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "generation_not_found"


def test_image_and_video_models_take_turns_in_memory(
    vclient: TestClient, engine: FakeImageEngine, video_engine: FakeVideoEngine
) -> None:
    wait_for_status(vclient, vclient.post(CREATE, json=video()).json()["id"], {"completed"})
    assert engine.unloads == 1  # the image model was freed before the video job
    image = {"mode": "text-to-image", "prompt": "A red fox in snow"}
    wait_for_status(vclient, vclient.post(CREATE, json=image).json()["id"], {"completed"})
    assert video_engine.unloads == 1  # and the video model before the image job


# --- serving security ------------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    [
        "..%2F..%2F.env",
        "..%2Fimages%2Fx.png",
        f"{uuid.uuid4()}.png",
        f"{uuid.uuid4()}.MP4",
        f".{uuid.uuid4()}.part.mp4",  # an unfinished/unvalidated temporary file
        "model_index.json",
        "%2Fetc%2Fpasswd",
    ],
)
def test_video_route_serves_only_finished_uuid_mp4s(vclient: TestClient, name: str) -> None:
    res = vclient.get(f"{VIDEOS}/{name}")
    assert res.status_code in (404, 422)
    assert res.headers["content-type"].startswith("application/json")


def test_temporary_file_is_not_served_while_processing(
    vclient: TestClient, video_engine: FakeVideoEngine, settings: Settings
) -> None:
    video_engine.gate = threading.Event()
    job_id = vclient.post(CREATE, json=video()).json()["id"]
    assert video_engine.started.wait(timeout=5)
    (settings.video_output_dir / f".{job_id}.part.mp4").write_bytes(b"partial")
    assert vclient.get(f"{VIDEOS}/{job_id}.mp4").status_code == 404
    video_engine.gate.set()
    wait_for_status(vclient, job_id, {"completed", "failed"})


# --- status endpoints -------------------------------------------------------------------


def test_info_reports_video_limits_and_availability(vclient: TestClient) -> None:
    body = vclient.get("/api/v1/info").json()
    assert body["video"]["available"] is True
    assert body["video"]["model_id"] == "test/fake-video-model"
    assert "text-to-video" in body["generation"]["modes_available"]
    limits = body["limits"]
    assert limits["video_duration_options_seconds"] == [2, 3, 5, 15, 30, 60, 90, 120]
    assert limits["video_max_frames"] == 81 and limits["video_fps"] == 16
    assert {"resolution": "large", "aspect_ratio": "16:9", "width": 832, "height": 480} in limits["video_sizes"]


def test_ready_reports_video_model_separately(vclient: TestClient, video_engine: FakeVideoEngine) -> None:
    video_engine.can_accept_error = VideoEngineError("model_not_downloaded", "Video weights are not downloaded.")
    body = vclient.get("/api/v1/health/ready").json()
    assert body["ready"] is True  # the API itself is fine
    assert body["checks"]["video_model"]["status"] == "not_downloaded"
    info = vclient.get("/api/v1/info").json()
    assert info["video"]["available"] is False
    assert "text-to-video" not in info["generation"]["modes_available"]


def test_fastwan_license_and_fixed_steps_are_reported(settings: Settings, engine: FakeImageEngine) -> None:
    with TestClient(create_app(settings, engine=engine)) as client:  # the real (unloaded) Wan engine
        body = client.get("/api/v1/info").json()
    info = body["video"]
    assert info["model_id"] == "FastVideo/FastWan2.1-T2V-1.3B-Diffusers"  # the default sampler
    assert body["limits"]["video_sampler"] == "fastwan" and body["limits"]["video_steps"] == [3]
    assert info["license"]["name"] == "Apache License 2.0"
    assert info["available"] is False  # no weights in the test cache


# --- long videos (15-120 s) ------------------------------------------------------------------


class FlakyVideoEngine(FakeVideoEngine):
    """Fails exactly once on one clip, to test that a retry regenerates only what is missing."""

    def __init__(self, fail_on_call: int) -> None:
        super().__init__()
        self.fail_on_call = fail_on_call

    def generate(self, params, deadline, output_path):
        if len(self.calls) + 1 == self.fail_on_call:
            self.fail_on_call = -1
            self.calls.append(params)
            raise VideoEngineError("gpu_out_of_memory", "The GPU ran out of memory.", retryable=True)
        return super().generate(params, deadline, output_path)


def test_long_video_is_assembled_from_real_clips_with_exact_duration(
    vclient: TestClient, video_engine: FakeVideoEngine, settings: Settings
) -> None:
    created = vclient.post(CREATE, json=video(duration_seconds=15))
    assert created.status_code == 202, created.text
    job = created.json()
    assert job["clips_total"] >= 3 and job["clips_completed"] == 0
    assert all(s["status"] == "queued" for s in job["scenes"])

    done = wait_for_status(vclient, job["id"], {"completed", "failed"}, timeout=60)
    assert done["status"] == "completed", done["error"]
    assert done["video"]["num_frames"] == 15 * 16 and done["video"]["duration_seconds"] == 15.0
    assert done["clips_completed"] == done["clips_total"] == len(video_engine.calls)
    assert all(s["status"] == "completed" for s in done["scenes"])
    # Each clip is its own generation, never a repeated or looped clip: within a scene seeds differ, and every
    # scene uses its own prompt. Scenes share a starting seed so the character stays more alike.
    calls = [(c.prompt, c.seed) for c in video_engine.calls]
    assert len(set(calls)) == len(calls)
    assert len({c.seed for c in video_engine.calls}) < len(video_engine.calls) or len(done["scenes"]) == 1
    assert all(c.num_frames <= 81 for c in video_engine.calls)
    parts = settings.video_output_dir / "parts"
    assert not parts.exists() or not any(parts.iterdir())  # temporary clips cleaned up


def test_user_scenes_and_durations_are_used(vclient: TestClient, video_engine: FakeVideoEngine) -> None:
    scenes = [
        {"description": "A young man walks through a village", "duration_seconds": 10},
        {"description": "He meets an old farmer", "duration_seconds": 20},
    ]
    job = vclient.post(CREATE, json=video(duration_seconds=30, scenes=scenes, style="documentary")).json()
    assert [s["duration_seconds"] for s in job["scenes"]] == [10, 20]
    assert job["scenes"][1]["prompt"].startswith("He meets an old farmer.")
    done = wait_for_status(vclient, job["id"], {"completed", "failed"}, timeout=60)
    assert done["video"]["num_frames"] == 30 * 16
    assert video_engine.calls[-1].prompt.startswith("He meets an old farmer.")


def test_failed_scene_can_be_retried_without_regenerating_finished_clips(settings: Settings, engine: FakeImageEngine) -> None:
    flaky = FlakyVideoEngine(fail_on_call=3)
    with TestClient(create_app(settings, engine=engine, video_engine=flaky)) as client:
        job = client.post(CREATE, json=video(duration_seconds=15)).json()
        failed = wait_for_status(client, job["id"], {"completed", "failed"}, timeout=60)
        assert failed["status"] == "failed" and failed["error"]["code"] == "gpu_out_of_memory"
        bad = [s for s in failed["scenes"] if s["status"] == "failed"]
        assert len(bad) == 1 and failed["video"] is None
        calls_before = len(flaky.calls)

        retried = client.post(f"{CREATE}/{job['id']}/scenes/{bad[0]['index']}/retry")
        assert retried.status_code == 202
        done = wait_for_status(client, job["id"], {"completed", "failed"}, timeout=60)
        assert done["status"] == "completed"
        # Only the failed clip and the ones after it were generated again.
        assert len(flaky.calls) - calls_before == done["clips_total"] - 2


def test_after_a_restart_the_same_request_reuses_finished_clips(settings: Settings, engine: FakeImageEngine) -> None:
    # Jobs live in memory; a CUDA driver error needs a new backend process. Clips are kept by content.
    request = video(duration_seconds=15, seed=99)
    flaky = FlakyVideoEngine(fail_on_call=3)
    with TestClient(create_app(settings, engine=engine, video_engine=flaky)) as client:
        job = client.post(CREATE, json=request).json()
        assert wait_for_status(client, job["id"], {"completed", "failed"}, timeout=60)["status"] == "failed"

    fresh = FakeVideoEngine()  # "restarted" backend
    with TestClient(create_app(settings, engine=engine, video_engine=fresh)) as client:
        job = client.post(CREATE, json=request).json()
        done = wait_for_status(client, job["id"], {"completed", "failed"}, timeout=60)
        assert done["status"] == "completed"
        assert len(fresh.calls) == done["clips_total"] - 2  # the two finished clips were not generated again


def test_retry_is_refused_for_unfailed_or_unknown_scenes(vclient: TestClient) -> None:
    job = vclient.post(CREATE, json=video(duration_seconds=15)).json()
    wait_for_status(vclient, job["id"], {"completed"}, timeout=60)
    assert vclient.post(f"{CREATE}/{job['id']}/scenes/1/retry").status_code == 409
    assert vclient.post(f"{CREATE}/{uuid.uuid4()}/scenes/1/retry").status_code == 404


@pytest.mark.parametrize(
    "payload",
    [
        {"duration_seconds": 5, "scenes": [{"description": "x"}]},  # scenes only for long videos
        {"duration_seconds": 30, "num_frames": 33},
        {"duration_seconds": 45},  # not an offered duration
        {"duration_seconds": 15, "scenes": [{"description": f"s{i}"} for i in range(10)]},  # < 2 s per scene
    ],
)
def test_invalid_long_video_requests_are_rejected(vclient: TestClient, payload: dict) -> None:
    assert vclient.post(CREATE, json=video(**payload)).status_code == 422


def test_last_frame_continuity_is_reported_unavailable(vclient: TestClient) -> None:
    res = vclient.post(CREATE, json=video(duration_seconds=15, continuity="last_frame"))
    assert res.status_code == 501 and res.json()["error"]["code"] == "continuity_not_available"


def test_scene_plan_endpoint_reports_coverage_and_limitations(vclient: TestClient) -> None:
    prompt = (
        "A realistic school classroom. One male teacher wearing a white shirt and black trousers stands at the "
        "front beside a blackboard, teaching ten students sitting at separate desks."
    )
    plan = vclient.post(f"{CREATE}/scene-plan", json={"mode": "text-to-image", "prompt": prompt}).json()
    assert plan["original_prompt"] == prompt and plan["people_count"] == 11
    assert all(i["status"] == "included" for i in plan["instructions"]), plan["instructions"]
    assert any("10 students" in note for note in plan["limitations"])
    image = plan["compiled"][0]
    assert image["target"] == "image" and image["tokens"] <= image["budget"]
    assert "teaching ten students" in image["text"] and "classroom" in image["text"]


def test_video_jobs_carry_the_exact_model_prompt(vclient: TestClient, video_engine: FakeVideoEngine) -> None:
    job = vclient.post(CREATE, json=video(style="anime")).json()
    wait_for_status(vclient, job["id"], {"completed"})
    sent = video_engine.calls[0].prompt
    assert sent == job["plan"]["model_prompt"]
    assert sent.startswith("Waves rolling onto a beach at sunset.") and "anime" in sent  # style now reaches video


def test_startup_removes_half_written_videos_but_keeps_finished_ones(settings: Settings, engine: FakeImageEngine) -> None:
    out = settings.video_output_dir
    out.mkdir(parents=True, exist_ok=True)
    orphan = out / ".11111111-1111-4111-8111-111111111111.part.mp4"
    orphan.write_bytes(b"partial")
    finished = out / "22222222-2222-4222-8222-222222222222.mp4"
    finished.write_bytes(b"done")
    with TestClient(create_app(settings, engine=engine, video_engine=FakeVideoEngine())):
        pass
    assert not orphan.exists() and finished.exists()
