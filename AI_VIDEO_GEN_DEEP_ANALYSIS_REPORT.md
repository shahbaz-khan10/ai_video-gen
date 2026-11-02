# AI Video Studio — Deep Architectural & Technical Analysis Report
**Generated on:** 2026-11-02  
**Project Location:** `C:\Users\jhone\OneDrive\Desktop\ai_video-gen`  
**Execution Environment:** Docker Desktop (Windows / WSL2)  
**Docker Status:** Fully Built & Actively Running

---

## 1. Executive Summary

**AI Video Studio** is a full-stack, production-grade local generative AI application designed for text-to-image and generative video workflows. The core differentiator of this architecture is **100% on-premise / local open-weight model execution** using Hugging Face Diffusers (`stabilityai/sd-turbo`). No third-party commercial APIs (like OpenAI DALL-E or Midjourney) are utilized, guaranteeing total data sovereignty, zero ongoing API billing, and private execution.

The project is structured as a two-tier microservice architecture:
1. **Frontend:** Modern Next.js 16 application leveraging Turbopack, App Router, React 19, Tailwind CSS v4, and Motion.
2. **Backend:** Asynchronous FastAPI service running on Python 3.12, paired with PyTorch, Diffusers, Hugging Face Hub, and Pillow.

Both components have been containerized, orchestrated via Docker Compose, built on Docker Desktop, and verified healthy.

---

## 2. High-Level System Architecture

```
                                  +-------------------------------------------------------+
                                  |                     Client Browser                    |
                                  |         (http://localhost:3001 - Studio UI)           |
                                  +---------------------------+---------------------------+
                                                              |
                                           HTTP / SSE         |
                                                              v
+-------------------------------------------------------------------------------------------------------------------------+
| Docker Engine (Docker Desktop)                                                                                          |
|                                                                                                                         |
|   +--------------------------------------+             +------------------------------------------------------------+   |
|   | Container: ai_video-gen-frontend-1   |             | Container: ai_video-gen-backend-1                          |   |
|   | Image: node:22-bookworm-slim         |             | Image: ai_video-gen-backend:latest                         |   |
|   | Port: 3001 -> 3000                   |             | Port: 8003 -> 8000                                         |   |
|   +--------------------------------------+             +------------------------------------------------------------+   |
|   | - Next.js 16 App Router              |   REST API  | - FastAPI (Uvicorn ASGI)                                   |   |
|   | - Turbopack Dev Engine               +------------>+ - Generation Service (ThreadPoolExecutor)                 |   |
|   | - Studio Workspace UI                | (Port 8003) | - DiffusersImageEngine (stabilityai/sd-turbo)              |   |
|   | - In-Memory Preferences Context      |             | - DisabledVideoEngine (Pluggable Protocol)                 |   |
|   +--------------------------------------+             +-----------------------------+------------------------------+   |
|                                                                                      |                                  |
|                                                                                      | Persistent Volumes               |
|                                                                                      v                                  |
|                                                        +-----------------------------+------------------------------+   |
|                                                        | Volumes Mounted:                                           |   |
|                                                        |  - backend-models: /app/models (~2.6GB FP16 weights)       |   |
|                                                        |  - backend-outputs: /app/outputs (Generated PNGs)          |   |
|                                                        +------------------------------------------------------------+   |
+-------------------------------------------------------------------------------------------------------------------------+
```

---

## 3. Frontend Architecture Analysis (Next.js 16)

### 3.1 Tech Stack & Dependencies
* **Core:** Next.js `16.4.3`, React `19`, React DOM `19`, TypeScript `5.x`.
* **Styling & Design System:** Tailwind CSS `v4` with native `@theme` tokens, Lucide React icons.
* **Animation & Interactivity:** `motion/react` (Framer Motion v12) with support for system-level reduced motion preferences.
* **Build System:** Turbopack with Cache Components and Partial Prefetching.

### 3.2 Directory Structure & Route Matrix
```
src/
├── app/
│   ├── (app)/                  # Studio App Shell route group (shared layout & sidebar)
│   │   ├── create/page.tsx     # Central Creation Workspace (prompt, style, aspect ratio)
│   │   ├── dashboard/page.tsx  # Studio Overview & recent projects summary
│   │   ├── explore/page.tsx    # Visual style presets & prompt inspirations
│   │   ├── projects/           # Media gallery & project detail views
│   │   └── settings/page.tsx   # Session preferences (theme, motion, defaults)
│   ├── layout.tsx              # Root HTML wrapper with fonts & metadata
│   └── page.tsx                # High-conversion public landing page
├── components/
│   ├── studio/                 # Create workspace components (PromptEditor, AspectRatio, Preview)
│   ├── layout/                 # AppShell, AppSidebar, AppHeader, NavItems
│   ├── motion/                 # Smooth transitions & MotionProvider
│   └── ui/                     # Atoms (Buttons, Tooltips, Modals, Switches)
├── lib/
│   ├── api/                    # Centralized, strongly-typed backend API client
│   └── generation/             # Job polling hooks (useImageJob) & state helpers
└── types/                      # Shared studio & API TypeScript contracts
```

### 3.3 Key Frontend Mechanics
1. **Zero-Flicker Session Preferences (`PreferencesProvider`):** User preferences (aspect ratio, default style, sidebar state, motion reduction) are managed in-memory via React Context, avoiding unnecessary local storage synchronization issues while respecting accessibility flags (`prefers-reduced-motion`).
2. **Resilient API Client (`src/lib/api/client.ts`):** All HTTP communications pass through a unified client featuring:
   * Automatic backend detection (`NEXT_PUBLIC_API_BASE_URL` with fallback to `http://localhost:8000`).
   * Configured timeouts (8000ms) with `AbortController`.
   * Standardized error categorization (`unconfigured`, `network`, `timeout`, `validation`, `http`).
3. **Dynamic Polling & Job Tracking (`use-image-job.ts`):** Real-time asynchronous polling mechanism querying `/api/v1/generations/{id}` with state transitions: `queued` $\rightarrow$ `processing` $\rightarrow$ `completed` / `failed`.

---

## 4. Backend Architecture Analysis (FastAPI & PyTorch)

### 4.1 Tech Stack & Dependencies
* **Framework:** FastAPI `0.162.0`, Uvicorn `0.54.0`, Pydantic `2.14.1`, Pydantic-Settings `2.16.1`.
* **AI & Inference:** PyTorch (CPU/CUDA), Hugging Face Diffusers `0.42.0`, Transformers `5.21.0`, Accelerate `1.15.0`, Safetensors `0.8.0`, Pillow `13.0.0`.
* **Testing:** Pytest `9.1.1`, HTTPX `0.28.1`.

### 4.2 Endpoint Specification Matrix

| Method | Endpoint | Description | Request / Response Specs |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/health` | Process liveness check | Lightweight JSON timestamp & version |
| `GET` | `/api/v1/health/ready` | API Readiness + Model Cache state | Non-blocking model state check |
| `GET` | `/api/v1/info` | Generation metadata & limits | Supported modes, styles, aspect ratios |
| `POST` | `/api/v1/generations/validate` | Input sanity & prompt validator | Normalizes prompts without queueing |
| `POST` | `/api/v1/generations` | Submit generation job | Returns `202 Accepted` with Job ID |
| `GET` | `/api/v1/generations/{id}` | Poll generation status | Returns state (`queued`, `completed`, `failed`) |
| `GET` | `/api/v1/models/image` | Inspect Diffusers pipeline state | Reports memory, device & load progress |
| `POST` | `/api/v1/models/image/load` | Pre-warm model in memory | Asynchronous background pipeline initialization |
| `GET` | `/api/v1/files/images/{uuid}.png` | Serve generated artifact | Safe UUID file delivery (Cache-Control headers) |

### 4.3 AI Engine Architecture: `DiffusersImageEngine`
1. **Lazy Loading:** `torch` and `diffusers` are imported dynamically. The API starts in milliseconds without waiting for heavy multi-gigabyte models to hit memory.
2. **Model Weight Management (`download_model.py`):**
   * Downloads only FP16 safe-tensors (~2.58 GB) for `stabilityai/sd-turbo`.
   * Avoids duplicate checkpoints and full-precision FP32 weights.
   * `local_files_only=True` enforces zero network access during live user requests.
3. **Hardware Adaptation:**
   * **CUDA / GPU:** Runs in FP16. Automatically turns on attention slicing and VAE tiling if VRAM $\le$ 6 GB; engages CPU offloading if VRAM $<$ 4 GB.
   * **CPU Mode:** Runs in FP32 with single-thread/multi-core optimizations.
4. **Style Prompt Injection:** The engine injects curated stylistic tokens into user prompts (e.g., `cinematic` appends *"cinematic film still, anamorphic lens, dramatic motivated lighting, film grain"*).
5. **Pluggable Video Engine (`video_engine.py`):** Implements an extensible `VideoEngine` protocol currently aliased to `DisabledVideoEngine` for clear, predictable responses until local video diffusion weights (e.g. SVD) are enabled.

### 4.4 Job Store & Concurrency
* **Concurrency Model:** FastAPI's async event loop delegates CPU/GPU-bound model inference to a dedicated `ThreadPoolExecutor(max_workers=1)`.
* **Job Registry (`JobStore`):** Thread-safe in-memory `OrderedDict` storing up to 200 jobs with automated eviction of oldest completed tasks.

---

## 5. Docker Infrastructure & Orchestration Analysis

### 5.1 Docker Compose Specification (`docker-compose.yml`)

```yaml
services:
  backend:
    build:
      context: .
      dockerfile: docker/backend.Dockerfile
    environment:
      AVS_IMAGE_ENGINE: diffusers
      AVS_IMAGE_DEVICE: cpu
      AVS_IMAGE_MODEL_CACHE_DIR: /app/models
      AVS_VIDEO_ENGINE: none
      AVS_CORS_ORIGINS: http://localhost:3001,http://127.0.0.1:3001
    ports:
      - "8003:8000"
    volumes:
      - backend-models:/app/models
      - backend-outputs:/app/outputs
    command: sh -c "python scripts/download_model.py --yes && exec uvicorn app.main:app --host 0.0.0.0 --port 8000"

  frontend:
    image: node:22-bookworm-slim
    working_dir: /app
    command: sh -c "npm ci && npm run dev -- --hostname 0.0.0.0 --port 3000"
    environment:
      NEXT_PUBLIC_API_BASE_URL: http://localhost:8003
    ports:
      - "3001:3000"
    volumes:
      - .:/app:ro
      - frontend-node-modules:/app/node_modules
      - frontend-next-cache:/app/.next
```

### 5.2 Storage & Volumes
* `backend-models`: Houses the ~2.6 GB Hugging Face cache so model weights survive container restarts.
* `backend-outputs`: Stores rendered `.png` outputs.
* `frontend-node-modules` & `frontend-next-cache`: Separates Linux container dependencies from Windows host filesystem, preventing lock conflicts and filesystem latency.

---

## 6. Live Execution Verification & Status

During analysis, the containers were built and brought up on Docker Desktop:

```
[+] Running 2/2
 ✔ Container ai_video-gen-backend-1   Started (Healthy, Uvicorn on 0.0.0.0:8000 -> Host:8003)
 ✔ Container ai_video-gen-frontend-1  Started (Ready, Next.js on 0.0.0.0:3000 -> Host:3001)
```

### Health Check Results
* **Backend Probe (`http://localhost:8003/api/v1/health`):**
  ```json
  {
    "status": "ok",
    "service": "AI Video Studio API",
    "version": "0.3.0",
    "timestamp": "2026-11-02T07:09:31.523840Z"
  }
  ```
* **Frontend Probe (`http://localhost:3001`):**
  ```http
  HTTP/1.1 200 OK
  X-Powered-By: Next.js
  Content-Type: text/html; charset=utf-8
  ```

---

## 7. Security, Reliability & Quality Audit

| Domain | Implemented Safeguards | Assessment |
| :--- | :--- | :--- |
| **Path Traversal Protection** | The files route (`/files/images/{uuid}.png`) strictly validates that requests conform to UUIDv4 hex strings. Arbitrary file path resolution is impossible. | **High** |
| **Payload Size Protection** | Requests are capped at 64 KB (`AVS_MAX_REQUEST_BYTES`) via custom middleware before reading into memory. | **High** |
| **Prompt Sanitization** | Control characters are stripped and multi-space sequences are collapsed before reaching tokenizers. | **High** |
| **CORS Isolation** | Restricted specifically to frontend host origins (`http://localhost:3001,http://127.0.0.1:3001`). Wildcards are forbidden in production. | **High** |
| **Model Weight Isolation** | Model execution never pulls network weights during inference; only cached weights are read. | **High** |
| **Error Masking** | System exceptions, Python stack traces, and filesystem paths are intercepted and masked into generic error codes. | **High** |

---

## 8. Strategic Recommendations & Future Roadmap

1. **Persistent Job Database (PostgreSQL / SQLite):**
   * *Current state:* Jobs reside in Python in-memory `JobStore` (lost on container restart).
   * *Recommendation:* Add SQLite or PostgreSQL via SQLAlchemy/SQLModel to preserve history across restarts.
2. **Distributed Queue System (Redis + Celery / ARQ):**
   * *Current state:* Single-worker `ThreadPoolExecutor`.
   * *Recommendation:* Separate web API from worker containers using Redis for robust multi-GPU queueing.
3. **GPU Acceleration on Docker Desktop:**
   * *Current state:* Set to `AVS_IMAGE_DEVICE=cpu`.
   * *Recommendation:* If an NVIDIA GPU is available, enable NVIDIA Container Toolkit (`--gpus all`) and switch Dockerfile PyTorch index to `cu126` for 10x-20x faster inference.
4. **Video Generation Model Integration:**
   * Implement Stable Video Diffusion (SVD) or AnimateDiff inside `video_engine.py` by replacing the `DisabledVideoEngine` stub.

---
*Report successfully compiled and saved to Desktop.*

