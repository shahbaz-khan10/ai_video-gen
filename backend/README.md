# AI Video Studio API

FastAPI backend for AI Video Studio. **Text-to-image runs on a real, locally hosted open-weight model** ([`stabilityai/sd-turbo`](https://huggingface.co/stabilityai/sd-turbo) by default) through Hugging Face Diffusers. No paid or remote inference API is used, and failures are reported as failures: no placeholder or stock image is ever returned. Text-to-video and image-to-video are **not connected yet** and return `501 mode_not_supported`.

- Python 3.12
- FastAPI, Uvicorn, Pydantic v2, pydantic-settings, Pillow
- PyTorch (CUDA build), Diffusers, Transformers, Accelerate for inference
- Pytest + HTTPX for tests (the normal suite uses a mocked engine: no GPU, weights or internet needed)

## Setup (Windows PowerShell)

Tested on Windows 11 with an NVIDIA GeForce RTX 3050 (8 GB VRAM, driver 591.86 / CUDA 13.1) and Python 3.12.

**Prerequisite:** PyTorch on Windows needs the [Microsoft Visual C++ Redistributable (x64)](https://aka.ms/vs/17/release/vc_redist.x64.exe). Without it, `import torch` fails with `WinError 126 … c10.dll`, and `/health/ready` reports the model as `not_installed` with that hint. Install it once (it needs administrator rights), e.g. `winget install Microsoft.VCRedist.2015+.x64`.

```powershell
cd backend

# 1. Virtual environment (pick one)
uv venv --python 3.12 .venv          # with uv
# py -3.12 -m venv .venv             # with the python.org launcher
.\.venv\Scripts\Activate.ps1
# If PowerShell blocks the script:  Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned

# 2. API dependencies
python -m pip install -r requirements.txt

# 3. PyTorch with CUDA (~2 GB download). Use the wheel that matches your driver:
#    nvidia-smi shows "CUDA Version: 13.1" here, so the cu130 build is the right one.
python -m pip install torch==2.14.1 --index-url https://download.pytorch.org/whl/cu130
#    No NVIDIA GPU? Install the CPU build instead (generation works, but slowly):
#    python -m pip install torch==2.14.1 --index-url https://download.pytorch.org/whl/cpu

# 4. Diffusers and friends
python -m pip install -r requirements-ai.txt

# 5. Check that PyTorch sees the GPU (should print True and the GPU name)
python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"

# 6. Optional local config
Copy-Item .env.example .env

# 7. Download the model weights ONCE (internet required, ~2.6 GB for sd-turbo fp16)
python scripts/download_model.py

# 8. Start the API
uvicorn app.main:app --reload --port 8000
```

PyTorch isn't in `requirements*.txt` on purpose: the right wheel depends on the GPU and driver, and reinstalling it blindly can replace a working CUDA build with a CPU one. If PyTorch is already installed and `torch.cuda.is_available()` is `True`, skip step 3.

Docs: http://localhost:8000/docs · ReDoc: http://localhost:8000/redoc · Schema: http://localhost:8000/api/v1/openapi.json

## The model

| | |
| --- | --- |
| Model | `stabilityai/sd-turbo` (distilled Stable Diffusion 2.1, 1–4 steps, no guidance) |
| License | [Stability AI Community License](https://huggingface.co/stabilityai/sd-turbo/blob/main/LICENSE.md): free for research, personal and non-commercial use, and for commercial use by individuals/organizations under US $1M annual revenue after registering with Stability AI. Also bound by Stability's Acceptable Use Policy. Not gated |
| Download | ~2.6 GB with `IMAGE_MODEL_VARIANT=fp16` (UNet 1.73 GB, text encoder 0.68 GB, VAE 0.17 GB). The 5.2 GB single-file checkpoint in the repo is not needed or downloaded |
| VRAM | About 3 GB in FP16 at 512×512, so it fits an 8 GB card comfortably |
| Native size | 512×512. The 768 tier works but is slower and softer |

The API **never downloads weights by itself** (`IMAGE_ALLOW_DOWNLOAD=false`). Until `scripts/download_model.py` has run, `/health/ready` reports `weights_missing` and text-to-image requests get `503 model_not_downloaded`. After that, everything runs offline.

The model loads lazily on the first generation (the first image takes longer) and then stays in memory. Starting the API and calling health endpoints never loads it or uses VRAM.

## Tests

```powershell
python -m pytest                      # mocked engine; no GPU or weights needed
python -m pytest -m real_inference    # REAL inference: needs PyTorch + downloaded weights
python scripts/smoke_test.py          # REAL inference smoke test with timing and VRAM report
```

The normal suite replaces the model with `FakeImageEngine` (in `tests/conftest.py`), which returns a flat-colour image. Only `-m real_inference` and `scripts/smoke_test.py` run the real model.

## Endpoints

All routes are under `/api/v1`.

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/health` | Liveness: the API process is running |
| GET | `/health/ready` | API readiness, plus a separate `model` object (`state`, `device`, `cuda_available`…). Never loads the model |
| GET | `/info` | Version, modes, limits, and which modes can generate right now |
| POST | `/generations/validate` | Validates and normalizes a request without generating anything |
| POST | `/generations` | Queues a text-to-image job and returns `202` with the job (`status: queued`) |
| GET | `/generations/{id}` | Job status: `queued`, `processing`, `completed` or `failed` |
| GET | `/files/images/{name}.png` | A generated image. `?download=true` sends it as an attachment |

### Text-to-image request

```json
{
  "mode": "text-to-image",
  "prompt": "A red fox in fresh snow, morning light",
  "aspect_ratio": "16:9",
  "style": "cinematic",
  "resolution": 512,
  "num_inference_steps": 1,
  "seed": 1234
}
```

| Field | Rules |
| --- | --- |
| `prompt` | 1–1000 characters after trimming. Control characters are removed. CLIP reads about the first 77 tokens |
| `aspect_ratio` | `16:9` (default), `9:16` or `1:1` |
| `style` | `cinematic` (default), `dreamlike`, `neon-noir`, `documentary`, `anime`, `golden-hour`. Added as a short cue before the prompt |
| `resolution` | `512` (default) or `768`. Size: 512 → 512×512, 688×384, 384×688; 768 → 768×768, 1024×576, 576×1024 |
| `num_inference_steps` | 1 (default) up to `IMAGE_MAX_STEPS` (4) |
| `seed` | Optional, 0–4294967295. Omitted → random; the seed used is returned |

Video modes keep the Phase 3 schema (`duration_seconds`, `source_image` metadata) and are accepted by `/validate` but refused by `POST /generations`.

### Job lifecycle

```
POST /generations ──► queued ──► processing ──► completed (output_url + result)
                                       └──────► failed (error_code + error)
```

`output_url` is set only after the PNG is written and verified. Completed jobs include `result` with width, height, seed, steps, model ID, device and duration.

**Jobs are kept in memory only and are lost when the backend restarts.** Polling a lost job returns `404 generation_not_found`. Images already written stay in `IMAGE_OUTPUT_DIR`. At most 200 finished jobs are remembered.

One job runs at a time (`IMAGE_MAX_CONCURRENT_JOBS=1`) on a worker thread, so inference never blocks the event loop. Up to `IMAGE_MAX_QUEUED_JOBS` (8) can wait or run; more get `429 queue_full`.

### Errors

Every error uses one envelope, with no stack traces or file paths:

```json
{ "error": { "code": "validation_error", "message": "The request is invalid.", "details": [{ "field": "prompt", "message": "..." }] } }
```

| Status | `code` | When |
| --- | --- | --- |
| 404 | `not_found`, `generation_not_found`, `image_not_found` | Unknown route, job or image |
| 413 | `payload_too_large` | Body over `AVS_MAX_REQUEST_BYTES` |
| 422 | `validation_error` | Invalid settings (submitted values are never echoed) |
| 429 | `queue_full` | Too many jobs waiting |
| 501 | `mode_not_supported` | Text-to-video / image-to-video |
| 501 | `engine_not_configured` | `IMAGE_ENGINE=none` |
| 503 | `engine_not_installed`, `model_not_downloaded` | Libraries or weights missing |

A failed **job** (HTTP 200 on poll, `status: failed`) carries one of: `gpu_out_of_memory`, `model_unavailable`, `model_download_failed`, `cuda_unavailable`, `generation_timeout`, `image_save_failed`, `generation_failed`.

### File safety

Images are named by the server (`<32 hex chars>.png`, uuid4) and written atomically (temp file, then rename), so nothing is overwritten. The file route accepts only that exact pattern, resolves it inside `IMAGE_OUTPUT_DIR`, and serves `image/png` with `nosniff`. Client input never becomes a filesystem path, so `.env`, model weights and other local files can't be reached. `outputs/` and `models/` are git-ignored.

## Configuration

Set via environment variables or `backend/.env` (see `.env.example`). No API keys are needed.

| Variable | Default | Notes |
| --- | --- | --- |
| `AVS_ENVIRONMENT` | `development` | `development`, `test` or `production` |
| `AVS_CORS_ORIGINS` | `http://localhost:3000,http://127.0.0.1:3000` | Comma-separated. `*` is refused in production |
| `AVS_DOCS_ENABLED` | `true` | Disable to hide `/docs` and the schema |
| `AVS_MAX_REQUEST_BYTES` | `65536` | Request body limit |
| `IMAGE_ENGINE` | `diffusers` | `none` disables generation |
| `IMAGE_MODEL_ID` | `stabilityai/sd-turbo` | Any Diffusers text-to-image model ID, or a local folder |
| `IMAGE_MODEL_VARIANT` | `fp16` | Empty for the default weights |
| `IMAGE_OUTPUT_DIR` | `outputs/images` | Relative to `backend/` |
| `IMAGE_MODEL_CACHE_DIR` | *(HF default)* | Empty uses `~/.cache/huggingface` |
| `IMAGE_ALLOW_DOWNLOAD` | `false` | Let the API download missing weights itself |
| `IMAGE_DEVICE` | `auto` | `auto`, `cuda` or `cpu` |
| `IMAGE_MAX_CONCURRENT_JOBS` | `1` | Inference on one pipeline is serialized either way |
| `IMAGE_MAX_QUEUED_JOBS` | `8` | |
| `IMAGE_MAX_STEPS` | `4` | Raise for non-turbo models |
| `IMAGE_GUIDANCE_SCALE` | `0.0` | SD-Turbo needs 0.0. Non-turbo models typically use ~7 |
| `IMAGE_GENERATION_TIMEOUT_SECONDS` | `300` | Checked between denoising steps |
| `IMAGE_ATTENTION_SLICING` | `false` | Saves VRAM, slower |
| `IMAGE_CPU_OFFLOAD` | `false` | Keeps only the active sub-model on the GPU (needs `accelerate`) |

Each `IMAGE_*` variable also works with an `AVS_` prefix.

## Structure

```
app/
  main.py                       app factory: middleware, error handlers, routers, engine wiring
  core/config.py                settings (AVS_* and IMAGE_* env vars)
  core/errors.py, limits.py     error envelope, body size limit
  api/routes/health.py          /health, /health/ready, /info
  api/routes/generation.py      /generations…
  api/routes/files.py           /files/images/{name}
  schemas/                      Pydantic request/response models, image size table
  services/image_engine.py      DiffusersImageEngine (lazy, FP16, OOM handling), DisabledEngine
  services/image_store.py       safe PNG storage and lookup
  services/generation_service.py  job registry, worker pool, error mapping
scripts/download_model.py       one-time weight download
scripts/smoke_test.py           real inference check
tests/                          pytest (mocked engine) + opt-in real inference test
```
