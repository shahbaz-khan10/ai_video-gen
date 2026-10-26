# AI Video Studio API

FastAPI backend for AI Video Studio. It validates generation requests and reports its own health. **No AI model is connected**: `POST /api/v1/generations` returns `501 engine_not_configured`, and no media is ever generated or faked.

- Python 3.12
- FastAPI, Uvicorn, Pydantic v2, pydantic-settings
- Pytest + HTTPX for tests (no GPU or internet needed)

## Setup (Windows PowerShell)

Run these from the repository root.

```powershell
# 1. Create a virtual environment
cd backend
py -3.12 -m venv .venv

# 2. Activate it
.\.venv\Scripts\Activate.ps1
# If PowerShell blocks the script, allow local scripts for your user once:
#   Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned

# 3. Install dependencies
python -m pip install -r requirements.txt

# 4. (Optional) create local config from the safe example
Copy-Item .env.example .env

# 5. Start the API with auto-reload
uvicorn app.main:app --reload --port 8000
```

Then open the API documentation in a browser:

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
- OpenAPI schema: http://localhost:8000/api/v1/openapi.json

## Run the tests

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python -m pytest
```

## Endpoints

All routes are under `/api/v1`.

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/health` | Liveness: the API process is running |
| GET | `/health/ready` | Readiness of the API itself. The AI engine is reported as `not_configured`, never assumed ready |
| GET | `/info` | Safe metadata: version, modes, aspect ratios, styles, limits, generation availability |
| POST | `/generations/validate` | Validates and normalizes a request without generating anything |
| POST | `/generations` | Validates, then returns `501 engine_not_configured` |
| GET | `/generations/{id}` | Status of a stored job. No jobs exist yet, so a valid UUID returns `404 generation_not_found` |

### Request shape

`mode` selects the schema:

```json
{
  "mode": "text-to-video",
  "prompt": "A lighthouse at blue hour, waves in slow motion",
  "aspect_ratio": "16:9",
  "style": "cinematic",
  "duration_seconds": 6
}
```

| Field | Rules |
| --- | --- |
| `mode` | `text-to-image`, `text-to-video` or `image-to-video` |
| `prompt` | 1–1000 characters after trimming. Control characters are removed and runs of spaces collapsed |
| `aspect_ratio` | `16:9` (default), `9:16` or `1:1` |
| `style` | `cinematic` (default), `dreamlike`, `neon-noir`, `documentary`, `anime`, `golden-hour` |
| `duration_seconds` | Video modes only: `4`, `6` (default) or `8`. Rejected for `text-to-image` |
| `source_image` | Required for `image-to-video`: `{ "content_type": "image/png" \| "image/jpeg" \| "image/webp", "size_bytes": 1..10485760 }`. Metadata only; image bytes, file names and paths are not accepted |

Unknown fields are rejected, so arbitrary paths or URLs can't be smuggled in.

### Errors

Every error uses one envelope:

```json
{ "error": { "code": "validation_error", "message": "The request is invalid.", "details": [{ "field": "prompt", "message": "..." }] } }
```

| Status | `code` |
| --- | --- |
| 404 | `not_found`, `generation_not_found` |
| 405 | `method_not_allowed` |
| 413 | `payload_too_large` (body over `AVS_MAX_REQUEST_BYTES`) |
| 422 | `validation_error` (submitted values are never echoed back) |
| 500 | `internal_error` (details only in server logs) |
| 501 | `engine_not_configured` |

## Configuration

Set via environment variables or `backend/.env` (see `.env.example`):

| Variable | Default | Notes |
| --- | --- | --- |
| `AVS_ENVIRONMENT` | `development` | `development`, `test` or `production` |
| `AVS_CORS_ORIGINS` | `http://localhost:3000,http://127.0.0.1:3000` | Comma-separated. `*` is refused in production |
| `AVS_DOCS_ENABLED` | `true` | Disable to hide `/docs` and the schema |
| `AVS_MAX_REQUEST_BYTES` | `65536` | Request body limit |

## Structure

```
app/
  main.py                     app factory: middleware, error handlers, routers
  core/config.py              settings (AVS_* env vars)
  core/errors.py              JSON error envelope and handlers
  core/limits.py              request body size limit
  api/deps.py                 dependencies (settings, generation service)
  api/routes/health.py        /health, /health/ready, /info
  api/routes/generation.py    /generations…
  schemas/                    Pydantic request/response models
  services/generation_service.py
tests/                        pytest suite
```

## Adding a real model later

Routes only talk to `GenerationService`. To connect a model, implement the `GenerationEngine` protocol in `app/services/generation_service.py` (a `name`, a `configured` property and `submit(settings) -> GenerationJob`). Then pass it to `create_app(engine=...)`. `tests/test_generation.py::FakeEngine` shows the shape.
