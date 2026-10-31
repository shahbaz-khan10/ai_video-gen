# AI Video Studio API

FastAPI backend for AI Video Studio. **Text to image runs on a real, local, open-weight model** (default `stabilityai/sd-turbo`, via Hugging Face Diffusers). No paid or remote inference API is used, and nothing is ever faked: a job is only `completed` once a real PNG is saved and verified.

- Python 3.12
- FastAPI, Uvicorn, Pydantic v2, pydantic-settings, Pillow
- Optional AI stack: PyTorch + Diffusers (`requirements-ai.txt`)
- Pytest + HTTPX for tests (mocked model: no GPU, weights or internet needed)

> **Jobs live in memory.** Restarting the backend loses the job list (generated PNGs stay on disk in `outputs/images/`).

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
| GET | `/health/ready` | API readiness, plus the image model's state reported separately (`model_ready`). Never loads the model |
| GET | `/info` | Safe metadata: modes, sizes, steps, limits, model ID and license, what is available now |
| POST | `/generations/validate` | Validates and normalizes a request without generating anything |
| POST | `/generations` | Queues a text-to-image job: `202` with `status: queued`. `503` if libraries/weights are missing, `429` if the queue is full |
| GET | `/generations/{id}` | Real status: `queued` → `processing` → `completed` (with image URL) or `failed` (with a safe error). `404` for unknown IDs |
| GET | `/models/image` | Model state: `unavailable`, `not_downloaded`, `not_loaded`, `loading`, `loaded`, `error`. Never loads the model |
| POST | `/models/image/load` | Starts loading the model in the background (optional; the first job also loads it) |
| GET | `/files/images/{uuid}.png` | Serves a generated image. Add `?download=true` for an attachment. Only `<uuid>.png` names from the output folder are reachable |

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

## Text to image: installing the model (Phase 4)

The API runs without any of this. It then reports the model as `unavailable` and refuses jobs with `503`. To generate real images:

**1. Install PyTorch for your machine** (pick one, inside the activated venv):

```powershell
# NVIDIA GPU (check with `nvidia-smi`; needs a recent driver):
python -m pip install torch --index-url https://download.pytorch.org/whl/cu126
# No NVIDIA GPU (CPU only; much slower, about 5 GB RAM for sd-turbo):
python -m pip install torch
```

Verify: `python -c "import torch; print(torch.__version__, torch.cuda.is_available())"`

**2. Install the Diffusers stack:** `python -m pip install -r requirements-ai.txt`

**3. Download the weights once (needs internet):** `python scripts/download_model.py`

It shows the size first (about **2.6 GB** for sd-turbo's FP16 files), checks free disk space, and asks before downloading. Weights go to `backend/models/` (git-ignored). The API never downloads at request time; it only reads this folder (`local_files_only`).

**4. Start the API** as usual. The first image also loads the model (slower). Later images reuse it.

**Real inference smoke test** (not mocked; runs the actual model):

```powershell
$env:AVS_RUN_REAL_INFERENCE = "1"; python -m pytest tests/test_real_inference.py -s
```

### Hardware notes

- GPU: FP16. On GPUs with ≤6 GB VRAM, attention slicing and VAE tiling are enabled automatically; below 4 GB, model CPU offload. Override with `IMAGE_ATTENTION_SLICING` / `IMAGE_CPU_OFFLOAD`.
- CPU: FP32 (FP16 is slow or unsupported on CPUs). Expect tens of seconds per 512×512 image.
- One job runs at a time (`IMAGE_MAX_CONCURRENT_JOBS=1`); others wait in a queue (`IMAGE_MAX_QUEUED_JOBS`).
- GPU out-of-memory, timeouts and load failures mark the job `failed` with a readable message; the browser never sees stack traces or local paths.

### Model and license

`stabilityai/sd-turbo` is released under the **Stability AI Community License** (July 2024). It is free for research and non-commercial use, and for commercial use by organizations with under US $1M annual revenue. Commercial users must register with Stability AI. You must follow Stability's Acceptable Use Policy and show "Powered by Stability AI" (the Create page shows it under each image). Read the full text at https://huggingface.co/stabilityai/sd-turbo/blob/main/LICENSE.md.

### Image settings

| Variable | Default | Notes |
| --- | --- | --- |
| `IMAGE_ENGINE` | `diffusers` | `none` turns generation off |
| `IMAGE_MODEL_ID` | `stabilityai/sd-turbo` | Any Diffusers text-to-image repo with cached weights |
| `IMAGE_MODEL_CACHE_DIR` | `models` | Relative to `backend/` |
| `IMAGE_OUTPUT_DIR` | `outputs/images` | Relative to `backend/` |
| `IMAGE_DEVICE` | `auto` | `auto`, `cuda` or `cpu` |
| `IMAGE_MAX_CONCURRENT_JOBS` | `1` | 1–4 |
| `IMAGE_MAX_QUEUED_JOBS` | `8` | Beyond this, `429 queue_full` |
| `IMAGE_TIMEOUT_SECONDS` | `600` | Checked between denoising steps |

## Adding another engine

Routes only talk to `GenerationService`. A new image engine implements the `ImageEngine` protocol in `app/services/image_engine.py` (`status`, `ensure_can_accept`, `load`, `generate`) and is passed to `create_app(engine=...)`. `tests/fakes.py::FakeImageEngine` shows the shape.
