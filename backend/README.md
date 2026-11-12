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
| GET | `/health/ready` | API readiness, plus the image and video models' states reported separately (`checks.image_model`, `checks.video_model`). Never loads a model |
| GET | `/info` | Safe metadata: modes, sizes, steps, video durations, limits, model IDs and licenses, what is available now (`generation`, `video`) |
| POST | `/generations/validate` | Validates and normalizes a request without generating anything |
| POST | `/generations` | Queues a text-to-image or text-to-video job: `202` with `status: queued`. `503` if libraries/weights are missing, `429` if the queue is full, `501` for image-to-video |
| GET | `/generations/{id}` | Real status: `queued` → `processing` → `completed` (with `image` or `video`) or `failed` (with a safe error). `404` for unknown IDs |
| GET | `/models/image` | Model state: `unavailable`, `not_downloaded`, `not_loaded`, `loading`, `loaded`, `error`. Never loads the model |
| POST | `/models/image/load` | Starts loading the model in the background (optional; the first job also loads it) |
| GET | `/files/images/{uuid}.png` | Serves a generated image. Add `?download=true` for an attachment. Only `<uuid>.png` names from the output folder are reachable |
| GET | `/files/videos/{uuid}.mp4` | Serves a generated, validated MP4 (HTTP range requests supported for seeking). `?download=true` for an attachment. Temporary files are never reachable |

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

## Text to video (Phase 5)

Text-to-video runs **Wan2.1 T2V 1.3B** locally through Diffusers. No paid or remote API is used; a job only reports `completed` after a real MP4 was written **and decoded frame by frame**. Image-to-video is not implemented yet (returns `501`).

### Model and license

| | |
| --- | --- |
| Model | [`Wan-AI/Wan2.1-T2V-1.3B-Diffusers`](https://huggingface.co/Wan-AI/Wan2.1-T2V-1.3B-Diffusers) |
| License | **Apache 2.0**: commercial use allowed. Not gated, no account needed |
| Download | **28.9 GB**: UMT5-XXL text encoder 22.7 GB (stored in fp32), transformer 5.7 GB, VAE 0.5 GB. Loaded in bf16 (~14.5 GB of RAM) |
| Why not LTX-Video 0.9 | Its Diffusers checkpoint is licensed for research and academic use only (RAIL-M, commercial use excluded) |

### Hardware results (RTX 3050 8 GB, Ryzen 5 7500F, 32 GB RAM, Docker Desktop)

| Setting | Measured |
| --- | --- |
| Model load (first job) | ~37 s |
| Draft 576×320, 2 s (33 frames), 25 steps | **~2 min**, 4.5 GB peak VRAM |
| 480p 832×480, 2 s (33 frames), 25 steps | **~5.5 min** through the API (incl. model load), 1.5 MB MP4 |
| RAM in the backend container while generating | ~15 GB |

How it fits an 8 GB GPU: the 11 GB text encoder runs **on the CPU** once per job (`VIDEO_TEXT_ENCODER_ON_CPU`, the approach of Wan's own `--t5_cpu`); the transformer (bf16) and VAE (fp32, as Wan recommends) stay on the GPU; VAE tiling keeps decoding within memory. Image and video models never share memory: the service unloads one before running the other, and only one GPU job runs at a time.

Expect minutes, not seconds. Time grows roughly with frames × pixels × steps: 5 s at 480p is about 2.5× the frames and 2.2× the pixels of a 2 s draft. Quality is below commercial services; motion and faces are best at 480p.

### Setup

Docker (recommended on this machine; Windows Smart App Control blocks PyTorch outside it):

```powershell
# 1. Give Docker Desktop enough RAM (once). In %USERPROFILE%.wslconfig:
#      [wsl2]
#      memory=24GB
#    then: wsl --shutdown   (restarts Docker Desktop and all containers)

# 2. Build and start (the image installs requirements-video.txt; imageio-ffmpeg bundles ffmpeg)
docker compose up -d --build

# 3. Download the weights into the models volume (~29 GB, once, needs internet)
docker run --rm -v ai_video-gen_backend-models:/app/models --entrypoint python ai_video-gen-backend -c "from huggingface_hub import snapshot_download; snapshot_download('Wan-AI/Wan2.1-T2V-1.3B-Diffusers', cache_dir='/app/models', allow_patterns=['model_index.json','scheduler/*','text_encoder/*','tokenizer/*','transformer/*','vae/*'])"

# 4. Real smoke test (not mocked): generates and decodes one draft clip
docker run --rm --gpus all -v ai_video-gen_backend-models:/app/models -v ai_video-gen_backend-outputs:/app/outputs --entrypoint python ai_video-gen-backend scripts/smoke_test_video.py --size standard --seconds 2
```

Without Docker: `python -m pip install -r requirements-video.txt` after `requirements-ai.txt`, download the weights the same way (`cache_dir` = `IMAGE_MODEL_CACHE_DIR`), then `python scripts/smoke_test_video.py`.

Generate the first video: open http://localhost:3001/create (Docker) or http://localhost:3000/create, pick **Text to Video**, write the scene and its motion, keep **Draft** and **2s**, press **Generate video**. The clip plays in the preview; **Download MP4** saves it.

### Request

```json
{ "mode": "text-to-video", "prompt": "A golden retriever running along a beach at sunset", "aspect_ratio": "16:9",
  "duration_seconds": 2, "resolution": "standard", "steps": 25, "seed": 11 }
```

| Field | Rules |
| --- | --- |
| `duration_seconds` | `2`, `3` or `5` (default 2). Becomes 33, 49 or 81 frames at 16 fps |
| `num_frames` | Optional override: 4k+1 between 5 and 81 (e.g. 17, 33, 49, 81) |
| `resolution` | `standard` (draft: 576×320, 320×576, 416×416) or `large` (480p: 832×480, 480×832, 624×624). `high`/720p is rejected: unstable on the 1.3B model |
| `steps` | 10-50 (default `VIDEO_DEFAULT_STEPS`, 25). The UI offers 15 / 25 / 40 |
| `seed` | Optional, 0 to 2³²-1 |

Anything else (`fps`, `guidance_scale`, `negative_prompt`, motion or camera fields) is rejected with `422` rather than silently ignored; guidance and Wan's negative prompt are fixed server-side.

A completed job has `video`: `url`, `download_url`, `width`, `height`, `num_frames`, `duration_seconds` and `size_bytes`, all read back from the decoded file. Failure codes: `gpu_out_of_memory`, `out_of_memory`, `model_not_downloaded`, `ai_libraries_missing`, `model_load_failed`, `generation_timeout`, `video_invalid`, `video_save_failed`, `generation_failed`.

Jobs are in memory and are lost on a backend restart. Finished MP4s stay in `VIDEO_OUTPUT_DIR` (the `backend-outputs` volume in Docker).

### Video settings

| Variable | Default | Notes |
| --- | --- | --- |
| `VIDEO_ENGINE` | `wan` | `none` turns video off |
| `VIDEO_MODEL_ID` | `Wan-AI/Wan2.1-T2V-1.3B-Diffusers` | |
| `VIDEO_MODEL_CACHE_DIR` | *(empty)* | Empty shares `IMAGE_MODEL_CACHE_DIR` |
| `VIDEO_OUTPUT_DIR` | `outputs/videos` | |
| `VIDEO_DEVICE` | `auto` | `cuda`, `cpu` (CPU works but takes hours) |
| `VIDEO_FPS` | `16` | Wan's native rate |
| `VIDEO_DEFAULT_STEPS` | `25` | |
| `VIDEO_GUIDANCE_SCALE` / `VIDEO_FLOW_SHIFT` | `5.0` / `3.0` | Wan's recommendations for 480p and below |
| `VIDEO_TEXT_ENCODER_ON_CPU` | `true` | Set false only with a GPU of 16 GB+ |
| `VIDEO_ENABLE_VAE_TILING` | `true` | |
| `VIDEO_TIMEOUT_SECONDS` | `3600` | Checked between denoising steps |
| `VIDEO_MAX_QUEUED_JOBS` | `2` | |

### Troubleshooting

- **`model_not_downloaded`**: the weights are missing or a shard is incomplete; re-run the download in step 3 (it resumes).
- **`ai_libraries_missing`**: install `requirements-video.txt` (`sentencepiece`, `ftfy`, `imageio`, `imageio-ffmpeg`), or rebuild the Docker image.
- **`gpu_out_of_memory`**: use Draft, 2 s, fewer steps; close other GPU-heavy apps (games, other AI tools).
- **`out_of_memory` or the container restarts while loading**: the text encoder needs ~15 GB of free RAM. Raise `memory` in `.wslconfig` or stop other containers.
- **CUDA not visible in Docker**: update the NVIDIA driver; check `docker run --rm --gpus all ai_video-gen-backend nvidia-smi` or `python -c "import torch; print(torch.cuda.is_available())"` inside the container.
- **MP4 won't play**: files are H.264/yuv420p with faststart; if a job reports `video_invalid`, the encoder output failed validation and nothing was published.

## Adding another engine

Routes only talk to `GenerationService`. A new image engine implements the `ImageEngine` protocol in `app/services/image_engine.py` (`status`, `ensure_can_accept`, `load`, `generate`) and is passed to `create_app(engine=...)`. `tests/fakes.py::FakeImageEngine` shows the shape.
