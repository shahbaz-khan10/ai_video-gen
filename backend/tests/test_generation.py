import uuid

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app

VALIDATE = "/api/v1/generations/validate"
CREATE = "/api/v1/generations"


def error_fields(res) -> set[str]:
    return {d["field"] for d in res.json()["error"]["details"]}


# --- valid requests -----------------------------------------------------------


def test_validate_text_to_video_returns_normalized_settings(client: TestClient, video_request: dict) -> None:
    res = client.post(VALIDATE, json=video_request)
    assert res.status_code == 200
    body = res.json()
    assert body["valid"] is True
    assert body["generation_available"] is False
    settings = body["settings"]
    assert settings["mode"] == "text-to-video"
    assert settings["duration_seconds"] == 2
    # 2 s at 16 fps, rounded up to Wan's 4k+1 frame rule; 576x320 is the draft 16:9 size.
    assert (settings["num_frames"], settings["fps"], settings["width"], settings["height"]) == (33, 16, 576, 320)
    assert settings["prompt_length"] == len(video_request["prompt"])
    assert settings["source_image"] is None


def test_validate_text_to_image_has_no_duration(client: TestClient) -> None:
    res = client.post(VALIDATE, json={"mode": "text-to-image", "prompt": "A red fox in snow", "aspect_ratio": "1:1"})
    assert res.status_code == 200
    settings = res.json()["settings"]
    assert settings["duration_seconds"] is None
    assert settings["style"] == "cinematic"  # default applied


def test_validate_image_to_video_with_image_metadata(client: TestClient) -> None:
    payload = {
        "mode": "image-to-video",
        "prompt": "Petals drift upward",
        "aspect_ratio": "9:16",
        "style": "dreamlike",
        "duration_seconds": 4,
        "source_image": {"content_type": "image/png", "size_bytes": 120_000},
    }
    res = client.post(VALIDATE, json=payload)
    assert res.status_code == 200
    assert res.json()["settings"]["source_image"] == {"content_type": "image/png", "size_bytes": 120_000}


def test_video_duration_defaults_when_omitted(client: TestClient, video_request: dict) -> None:
    del video_request["duration_seconds"]
    res = client.post(VALIDATE, json=video_request)
    assert res.status_code == 200
    assert res.json()["settings"]["duration_seconds"] == 2


def test_prompt_is_trimmed_and_whitespace_normalized(client: TestClient, video_request: dict) -> None:
    video_request["prompt"] = "   A  lighthouse\t at dusk \r\n  slow   waves\x07  "
    res = client.post(VALIDATE, json=video_request)
    assert res.status_code == 200
    assert res.json()["settings"]["prompt"] == "A lighthouse at dusk\nslow waves"


# --- invalid requests ---------------------------------------------------------


@pytest.mark.parametrize("prompt", ["", "   ", "\n\t \x00"])
def test_empty_prompt_rejected(client: TestClient, video_request: dict, prompt: str) -> None:
    video_request["prompt"] = prompt
    res = client.post(VALIDATE, json=video_request)
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "validation_error"
    assert "prompt" in error_fields(res)


def test_overlong_prompt_rejected(client: TestClient, video_request: dict) -> None:
    video_request["prompt"] = "a" * 4001
    res = client.post(VALIDATE, json=video_request)
    assert res.status_code == 422
    assert "prompt" in error_fields(res)


def test_prompt_at_limit_accepted(client: TestClient, video_request: dict) -> None:
    video_request["prompt"] = "a" * 4000
    assert client.post(VALIDATE, json=video_request).status_code == 200


def test_validation_errors_do_not_echo_prompt(client: TestClient, video_request: dict) -> None:
    video_request["prompt"] = "PRIVATE-" + "x" * 4000
    res = client.post(VALIDATE, json=video_request)
    assert res.status_code == 422
    assert "PRIVATE" not in res.text


def test_unsupported_mode_rejected(client: TestClient, video_request: dict) -> None:
    video_request["mode"] = "text-to-audio"
    res = client.post(VALIDATE, json=video_request)
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "validation_error"


def test_missing_mode_rejected(client: TestClient, video_request: dict) -> None:
    del video_request["mode"]
    assert client.post(VALIDATE, json=video_request).status_code == 422


@pytest.mark.parametrize("ratio", ["4:3", "21:9", "16x9", ""])
def test_unsupported_aspect_ratio_rejected(client: TestClient, video_request: dict, ratio: str) -> None:
    video_request["aspect_ratio"] = ratio
    res = client.post(VALIDATE, json=video_request)
    assert res.status_code == 422
    assert "aspect_ratio" in error_fields(res)


def test_unknown_style_rejected(client: TestClient, video_request: dict) -> None:
    video_request["style"] = "vaporwave"
    res = client.post(VALIDATE, json=video_request)
    assert res.status_code == 422
    assert "style" in error_fields(res)


# Text-to-video allows 2, 3, 5 s (one clip) and 15, 30, 60, 90, 120 s (assembled from scene clips).
@pytest.mark.parametrize("duration", [0, 4, 6, 8, 10, 45, 150, -6, "six"])
def test_unsupported_duration_rejected(client: TestClient, video_request: dict, duration) -> None:
    video_request["duration_seconds"] = duration
    res = client.post(VALIDATE, json=video_request)
    assert res.status_code == 422
    assert "duration_seconds" in error_fields(res)


def test_duration_not_allowed_for_images(client: TestClient) -> None:
    payload = {"mode": "text-to-image", "prompt": "A red fox", "duration_seconds": 6}
    assert client.post(VALIDATE, json=payload).status_code == 422


def test_image_to_video_requires_source_image(client: TestClient) -> None:
    payload = {"mode": "image-to-video", "prompt": "Make it move"}
    res = client.post(VALIDATE, json=payload)
    assert res.status_code == 422
    assert "source_image" in error_fields(res)


@pytest.mark.parametrize(
    "image",
    [
        {"content_type": "image/gif", "size_bytes": 1000},
        {"content_type": "application/pdf", "size_bytes": 1000},
        {"content_type": "image/png", "size_bytes": 0},
        {"content_type": "image/png", "size_bytes": 10 * 1024 * 1024 + 1},
    ],
)
def test_invalid_source_image_rejected(client: TestClient, image: dict) -> None:
    payload = {"mode": "image-to-video", "prompt": "Make it move", "source_image": image}
    assert client.post(VALIDATE, json=payload).status_code == 422


@pytest.mark.parametrize("field", ["path", "file_path", "output_path", "image_url"])
def test_unknown_fields_such_as_paths_rejected(client: TestClient, video_request: dict, field: str) -> None:
    video_request[field] = "C:\\Windows\\System32\\config"
    res = client.post(VALIDATE, json=video_request)
    assert res.status_code == 422
    assert field in error_fields(res)


def test_source_image_rejects_filename_or_path(client: TestClient) -> None:
    payload = {
        "mode": "image-to-video",
        "prompt": "Make it move",
        "source_image": {"content_type": "image/png", "size_bytes": 1000, "filename": "../../etc/passwd"},
    }
    assert client.post(VALIDATE, json=payload).status_code == 422


def test_wrong_prompt_type_rejected(client: TestClient, video_request: dict) -> None:
    video_request["prompt"] = ["not", "a", "string"]
    assert client.post(VALIDATE, json=video_request).status_code == 422


def test_malformed_json_rejected(client: TestClient) -> None:
    res = client.post(VALIDATE, content=b"{not json", headers={"Content-Type": "application/json"})
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "validation_error"


def test_oversized_body_rejected_with_413(settings: Settings, video_request: dict) -> None:
    client = TestClient(create_app(settings.model_copy(update={"max_request_bytes": 512})))
    video_request["prompt"] = "a" * 900
    res = client.post(VALIDATE, json=video_request)
    assert res.status_code == 413
    assert res.json()["error"]["code"] == "payload_too_large"


# --- creation and lookup ------------------------------------------------------


def test_create_video_without_video_engine_is_refused_honestly(client: TestClient, video_request: dict) -> None:
    # Text-to-video is routed to the video engine (added after Phase 4). Without its
    # libraries/weights it must refuse with a clear reason, never queue a fake job.
    res = client.post(CREATE, json=video_request)
    assert res.status_code in (501, 503)
    body = res.json()
    assert body["error"]["code"] in ("engine_not_configured", "ai_libraries_missing", "model_not_downloaded")
    assert "id" not in body and "image" not in body and "video" not in body


def test_create_still_validates_before_501(client: TestClient, video_request: dict) -> None:
    video_request["aspect_ratio"] = "4:3"
    assert client.post(CREATE, json=video_request).status_code == 422


def test_rejected_video_request_does_not_store_a_job(client: TestClient, video_request: dict) -> None:
    client.post(CREATE, json=video_request)
    service = client.app.state.generation_service
    assert service.store._jobs == {}


def test_unknown_generation_id_returns_404(client: TestClient) -> None:
    res = client.get(f"{CREATE}/{uuid.uuid4()}")
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "generation_not_found"


@pytest.mark.parametrize("bad_id", ["not-a-uuid", "123"])
def test_malformed_generation_id_returns_422(client: TestClient, bad_id: str) -> None:
    res = client.get(f"{CREATE}/{bad_id}")
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "validation_error"


@pytest.mark.parametrize("bad_id", ["..%2F..%2Fetc%2Fpasswd", "..%5C..%5Cwindows"])
def test_path_traversal_in_id_is_rejected(client: TestClient, bad_id: str) -> None:
    res = client.get(f"{CREATE}/{bad_id}")
    # Either no route matches (404) or the UUID check fails (422); never a success or a crash.
    assert res.status_code in (404, 422)
    assert "error" in res.json()
