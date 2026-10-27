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


def test_ready_reports_model_separately_without_loading_it(client: TestClient, engine) -> None:
    res = client.get("/api/v1/health/ready")
    assert res.status_code == 200
    body = res.json()
    assert body["ready"] is True
    assert body["model_ready"] is False
    assert body["checks"]["api"]["status"] == "ok"
    assert body["checks"]["image_model"]["status"] == "not_loaded"
    assert engine.loaded is False  # a health check must never load the model


def test_ready_reports_missing_weights(client: TestClient, engine) -> None:
    from app.services.image_engine import EngineError

    engine.can_accept_error = EngineError("model_not_downloaded", "Model weights have not been downloaded yet.")
    body = client.get("/api/v1/health/ready").json()
    assert body["ready"] is True  # the API still works
    assert body["checks"]["image_model"]["status"] == "not_downloaded"


def test_ready_with_generation_disabled(settings: Settings) -> None:
    with TestClient(create_app(settings, engine=None)) as client:
        body = client.get("/api/v1/health/ready").json()
    assert body["checks"]["image_model"]["status"] == "not_configured"
    assert body["model_ready"] is False


def test_info_lists_modes_and_text_to_image_availability(client: TestClient) -> None:
    res = client.get("/api/v1/info")
    assert res.status_code == 200
    body = res.json()
    assert body["api_version"] == "v1"
    assert body["modes"] == ["text-to-image", "text-to-video", "image-to-video"]
    assert body["aspect_ratios"] == ["16:9", "9:16", "1:1"]
    assert "cinematic" in body["styles"]
    limits = body["limits"]
    assert limits["prompt_max_chars"] == 1000
    assert limits["duration_options_seconds"] == [4, 6, 8]
    assert limits["source_image_types"] == ["image/png", "image/jpeg", "image/webp"]
    assert limits["image_steps"] == [1, 2, 4]
    assert {"resolution": "standard", "aspect_ratio": "1:1", "width": 512, "height": 512} in limits["image_sizes"]
    for size in limits["image_sizes"]:
        assert size["width"] % 8 == 0 and size["height"] % 8 == 0
    gen = body["generation"]
    assert gen["available"] is True
    assert gen["modes_available"] == ["text-to-image"]  # video is not claimed
    assert gen["engine"] == "fake"


def test_info_reports_sd_turbo_license(settings: Settings) -> None:
    from app.services.image_engine import DiffusersImageEngine

    with TestClient(create_app(settings, engine=DiffusersImageEngine(settings))) as client:
        gen = client.get("/api/v1/info").json()["generation"]
    assert gen["model_id"] == "stabilityai/sd-turbo"
    assert gen["license"]["name"] == "Stability AI Community License"
    assert gen["license"]["attribution"] == "Powered by Stability AI"


def test_info_when_generation_unavailable(client: TestClient, engine) -> None:
    from app.services.image_engine import EngineError

    engine.can_accept_error = EngineError("ai_libraries_missing", "AI libraries are not installed.")
    gen = client.get("/api/v1/info").json()["generation"]
    assert gen["available"] is False
    assert gen["modes_available"] == []


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
    client = TestClient(create_app(settings.model_copy(update={"docs_enabled": False}), engine=None))
    assert client.get("/docs").status_code == 404
    assert client.get("/api/v1/openapi.json").status_code == 404


def test_openapi_available_by_default(client: TestClient) -> None:
    res = client.get("/api/v1/openapi.json")
    assert res.status_code == 200
    assert "/api/v1/generations/validate" in res.json()["paths"]
