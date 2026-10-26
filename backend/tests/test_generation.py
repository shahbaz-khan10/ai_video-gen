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
    assert settings["duration_seconds"] == 6
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
    assert res.json()["settings"]["duration_seconds"] == 6


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
    video_request["prompt"] = "a" * 1001
    res = client.post(VALIDATE, json=video_request)
    assert res.status_code == 422
    assert "prompt" in error_fields(res)


def test_prompt_at_limit_accepted(client: TestClient, video_request: dict) -> None:
    video_request["prompt"] = "a" * 1000
    assert client.post(VALIDATE, json=video_request).status_code == 200


def test_validation_errors_do_not_echo_prompt(client: TestClient, video_request: dict) -> None:
    video_request["prompt"] = "PRIVATE-" + "x" * 1000
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


@pytest.mark.parametrize("duration", [0, 3, 5, 10, 60, -6, "six"])
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


def test_create_returns_501_engine_not_configured(client: TestClient, video_request: dict) -> None:
    res = client.post(CREATE, json=video_request)
    assert res.status_code == 501
    body = res.json()
    assert body["error"]["code"] == "engine_not_configured"
    # No fabricated job or output.
    assert "id" not in body and "output_url" not in body


def test_create_still_validates_before_501(client: TestClient, video_request: dict) -> None:
    video_request["aspect_ratio"] = "4:3"
    assert client.post(CREATE, json=video_request).status_code == 422


def test_create_does_not_store_a_job(client: TestClient, video_request: dict) -> None:
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


# --- engine seam --------------------------------------------------------------


class FakeEngine:
    """Stands in for a future real engine; proves routes need no changes."""

    name = "fake"
    configured = True

    def submit(self, settings):
        from datetime import UTC, datetime

        from app.schemas.generation import GenerationJob, GenerationStatus

        return GenerationJob(
            id=str(uuid.uuid4()), status=GenerationStatus.QUEUED, settings=settings, created_at=datetime.now(UTC)
        )


def test_configured_engine_creates_and_returns_real_job(settings: Settings, video_request: dict) -> None:
    client = TestClient(create_app(settings, engine=FakeEngine()))
    created = client.post(CREATE, json=video_request)
    assert created.status_code == 202
    job = created.json()
    assert job["status"] == "queued"
    assert job["output_url"] is None

    fetched = client.get(f"{CREATE}/{job['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == job["id"]

    ready = client.get("/api/v1/health/ready").json()
    assert ready["checks"]["generation_engine"]["status"] == "ok"
    assert client.get("/api/v1/info").json()["generation"]["available"] is True


def test_empty_prompt_message_is_readable(client: TestClient, video_request: dict) -> None:
    video_request["prompt"] = "  \x07 "
    details = client.post(VALIDATE, json=video_request).json()["error"]["details"]
    assert details == [{"field": "prompt", "message": "Prompt is empty. Describe what you want to create."}]


def test_openapi_documents_prompt_min_length(client: TestClient) -> None:
    schema = client.get("/api/v1/openapi.json").json()["components"]["schemas"]["TextToVideoRequest"]
    assert schema["properties"]["prompt"]["minLength"] == 1
