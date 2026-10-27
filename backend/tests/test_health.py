from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def test_health_ok(client: TestClient) -> None:
    res = client.get("/api/v1/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert body["version"]
    assert body["service"] == "AI Video Studio API"
    assert "timestamp" in body


def test_ready_reports_api_ready_but_engine_not_configured(client: TestClient) -> None:
    res = client.get("/api/v1/health/ready")
    assert res.status_code == 200
    body = res.json()
    assert body["ready"] is True
    assert body["checks"]["api"]["status"] == "ok"
    # Must not claim an AI engine is ready when none is connected.
    assert body["checks"]["generation_engine"]["status"] == "not_configured"


def test_info_lists_modes_and_states_generation_unavailable(client: TestClient) -> None:
    res = client.get("/api/v1/info")
    assert res.status_code == 200
    body = res.json()
    assert body["api_version"] == "v1"
    assert body["modes"] == ["text-to-image", "text-to-video", "image-to-video"]
    assert body["aspect_ratios"] == ["16:9", "9:16", "1:1"]
    assert "cinematic" in body["styles"]
    assert body["limits"]["prompt_max_chars"] == 1000
    assert body["limits"]["duration_options_seconds"] == [4, 6, 8]
    assert body["limits"]["source_image_types"] == ["image/png", "image/jpeg", "image/webp"]
    assert body["generation"]["available"] is False
    assert body["generation"]["engine"] == "none"


def test_info_exposes_no_secrets_or_cors_config(client: TestClient) -> None:
    text = client.get("/api/v1/info").text.lower()
    for word in ("cors", "secret", "key", "token", "password"):
        assert word not in text


def test_unknown_route_returns_json_404(client: TestClient) -> None:
    res = client.get("/api/v1/does-not-exist")
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "not_found"


def test_wrong_method_returns_405(client: TestClient) -> None:
    res = client.delete("/api/v1/health")
    assert res.status_code == 405
    assert res.json()["error"]["code"] == "method_not_allowed"


def test_cors_allows_configured_origin_only(client: TestClient) -> None:
    allowed = client.get("/api/v1/health", headers={"Origin": "http://localhost:3000"})
    assert allowed.headers.get("access-control-allow-origin") == "http://localhost:3000"

    blocked = client.get("/api/v1/health", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in blocked.headers


def test_cors_origins_parse_from_comma_separated_env(monkeypatch) -> None:
    monkeypatch.setenv("AVS_CORS_ORIGINS", "http://localhost:3000, https://studio.example.com/")
    settings = Settings(_env_file=None)
    assert settings.cors_origins == ["http://localhost:3000", "https://studio.example.com"]


def test_wildcard_cors_rejected_in_production() -> None:
    import pytest

    with pytest.raises(ValueError):
        Settings(_env_file=None, environment="production", cors_origins=["*"])


def test_docs_can_be_disabled(settings: Settings) -> None:
    client = TestClient(create_app(settings.model_copy(update={"docs_enabled": False})))
    assert client.get("/docs").status_code == 404
    assert client.get("/api/v1/openapi.json").status_code == 404


def test_openapi_available_by_default(client: TestClient) -> None:
    res = client.get("/api/v1/openapi.json")
    assert res.status_code == 200
    assert "/api/v1/generations/validate" in res.json()["paths"]


def test_image_settings_read_plain_env_names(monkeypatch) -> None:
    monkeypatch.setenv("IMAGE_MODEL_ID", "some/model")
    monkeypatch.setenv("IMAGE_MAX_CONCURRENT_JOBS", "2")
    monkeypatch.setenv("IMAGE_MODEL_CACHE_DIR", "")
    settings = Settings(_env_file=None)
    assert settings.image_model_id == "some/model"
    assert settings.image_max_concurrent_jobs == 2
    assert settings.image_model_cache_dir is None
    assert settings.image_output_dir.is_absolute()
