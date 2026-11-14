# AI Video Studio — Quality Roadmap

Date: 2026-11-14 · Branch `shahbaz_ai_vdeo` @ `5dc5170` · Hardware: RTX 3050 **8 GB**, Ryzen 5 7500F, 32 GB RAM, Docker Desktop (WSL2 VM 23.5 GiB).

This is an assessment, not a feature list. Every statement below is backed by a real run on this machine; anything not yet measured is marked **unmeasured**. Evidence: `docs/PHASE_A_GENERATION_AUDIT.md`, `docs/verification/PHASE_I_REAL_WORLD_VERIFICATION.md`, `docs/PROMPT_COMPILER_FIX_REPORT.md`, `docs/benchmarks/`, `docs/prompt_compiler/`, `docs/speed/`.

---

## 1. Current quality assessment

| # | Priority | Status | Evidence (real runs) |
| --- | --- | --- | --- |
| 1 | Prompt understanding & instruction preservation | **Mostly working** | Prompt compiler: every instruction gets an exact status; per-scene prompts measured with the real tokenizers (UMT5 57–125 / 511 tokens, CLIP ≤ 75). Phase 4 meadow test: 5/5 instructions included, scenes correct. Rule-based English parsing can still misread unusual grammar. |
| 2 | Photorealistic images | **Not acceptable** | "Teacher in front of 10 students": 0, 1 and 3 students in three runs; default 680×384 is far below SDXL's native 1024 px, giving an over-sharpened look. Single subjects look good. |
| 3 | Consistent characters across scenes | **Not achieved** | Fisherman 30 s: raincoat/beard kept, but "blue wool hat" became a black hat in every scene, face changed in scene 5. Girl story: different girl per scene. Wolf/sheep (user): sheep size/face changed. Each clip is generated from text only — nothing ties identity together. |
| 4 | Accurate scene actions & environments | **Partly** | Meadow test: environment, colours and "wolf appears from behind a tree" correct. Fisherman: "pushes his boat" shown sitting in the boat; "harbor" shown as open water; edited "seagulls" not drawn. |
| 5 | Smooth, coherent video | **Partly** | Single clips are smooth (16 fps). Inside a scene, independently generated clips are crossfaded → ghosted double image (user's wolf/sheep video). Characters jump between cuts. |
| 6 | Reliable 15–120 s generation | **Works, slowly** | 15 s ×3, 30 s ×2, 60 s, 120 s completed. 120 s needed a restart after a GPU crash; ~65 min GPU time. |
| 7 | GPU stability & memory | **Not acceptable** | Three stalls/crashes in three days (details §3.7). Reproduced today: 480p VAE benchmark stalled (GPU 0–1 % for > 1 min with 6.1 GB held) and the Docker engine returned HTTP 500 until WSL was restarted. |
| 8 | Recovery, retry, export | **Partly** | Retry API works; finished clips are reused after a restart when the same request + seed is resent. Jobs live in memory: a restart erases every job record; there is no history in the UI; the retry button could not be exercised in the browser (timeout bug). MP4 export/download works. |

**Overall:** the product generates real images and multi-scene videos and now understands prompts much better, but it is **not yet reliable** (memory/GPU stalls) and **not yet consistent** (characters, counts, details).

---

## 2. Critical problems (ranked by user impact)

1. **Stalls and crashes** during long or 480p jobs (Docker VM out of memory, GPU stall).
2. **Character identity drifts** between scenes and clips.
3. **Ghosting** inside multi-clip scenes.
4. **Image composition errors** (crowd counts, multi-person scenes) and low default image resolution.
5. **Slow generation** (≈ 2 min per 5 s Draft clip; 120 s ≈ 1 h).
6. **Lost jobs on restart**, no history, retry not exercisable from the UI.
7. Visual details ignored (colours of small items, background props, specific places).

---

## 3. Root causes

### 3.1 Prompt understanding (fixed in `5dc5170`, keep testing)
Our own 600-character cut (not the model) truncated scenes; CLIP silently dropped image prompt tails; stories were not split into scenes. Fixed by the prompt compiler with real tokenizer budgets.

### 3.2 Images
- SDXL/CLIP binds attributes and counts weakly — a **model limit**: counts above ~4 are approximate on every SDXL model.
- Default resolution `standard` = 680×384 (`backend/app/schemas/generation.py:88`, `src/components/studio/create-workspace.tsx:69`) — RealVisXL is trained at ~1 MP; small sizes degrade faces and detail. **Fixable.**

### 3.3 Character consistency
- Each clip is a fresh text-to-video sample with a different seed (`seed + scene·1000 + k`); text alone cannot pin a face. **Architectural**: needs image/reference conditioning.
- The only reference-capable model on disk is **Wan2.1 VACE 1.3B** (Apache-2.0); benchmarked only for last-frame continuation (works, ~7× slower). Its reference-image ("R2V") mode is **unmeasured**.

### 3.4 Scene actions / details
- 1.3B video models follow the main subject and action but drop secondary details (props, colours of accessories, background landmarks). **Model limit**, partly mitigated by shorter, focused scene prompts (done).

### 3.5 Smoothness
- Crossfading two independently generated clips of one scene blends two different poses (`backend/app/services/long_video.py:19`, `generation_service.py:500`). **Fixable**: one clip per scene beat (≤ 5 s) with cuts, or continuation conditioning.

### 3.6 Speed (measured today, same latents, 81 frames, 576×320 — `docs/speed/vae_report_standard_81f.json`)

| Stage | Time |
| --- | --- |
| Model load (cold) | 42.6 s |
| Text encode (UMT5 on CPU) | 6.6 s per call — repeated for every clip although a scene's prompt is identical |
| Denoise (3 DMD steps) | 19.4 s |
| VAE decode fp32 untiled | 213.6 s, 6.95 GB (spills to shared memory) |
| **VAE decode fp32 tiled (current)** | **39.9 s**, 4.57 GB |
| **VAE decode bf16 untiled** | **15.8 s**, 4.95 GB, **PSNR 57.9 dB** vs fp32 untiled |
| VAE decode bf16 tiled | 23.4 s, 3.68 GB, PSNR 54.4 dB |

The VAE decode is ~60 % of a clip. bf16 untiled is 2.5× faster with a numerical difference far below visibility (> 45 dB). Because Wan's authors warn about bf16 colour artefacts, frames 10/40/75 were compared side by side (`docs/speed/vae_fp32_vs_bf16_draft.png`): no visible difference in colour, fur detail or background on this clip. More clips (skin tones, dark scenes) must be checked before switching. At 480p the benchmark itself stalled (see 3.7), so 480p numbers are **unmeasured**.

### 3.7 GPU stability and memory (measured)

| Measurement | Value |
| --- | --- |
| Docker/WSL VM memory | 23.5 GiB |
| Other projects' containers running in the same VM (39 total) | **7.9 GiB idle** (`sourcebot-qdrant` 4.1 GiB, `hdms-clamav` 1.0 GiB, …) |
| Video backend with image + video models resident | **18.5 GiB** (measured 2026-11-13) |
| Sum | **≈ 26.4 GiB > 23.5 GiB** |
| VRAM during the stalls | 6.1–7.8 GB of 8.2 GB, GPU 0–17 % |

Root cause (strong evidence, final proof pending): the AI backend shares the WSL VM with ~37 unrelated containers, so loading the 11 GB UMT5 text encoder pushes the VM past its memory limit; the VM swaps and the GPU job and the Docker engine stall. Contributing: both models kept in RAM after a model switch, fp32/untiled decodes near the 8 GB VRAM ceiling, and Windows apps using ~0.6–1.5 GB VRAM.

### 3.8 Recovery
In-memory `JobStore` (`generation_service.py:63`); the video deadline is checked only between denoising steps (`video_engine.py:323-325`), so a failing clip cannot be forced and stalls are not detected; no watchdog.

---

## 4. Candidate open-source components (license and size from the Hugging Face API, 2026-11-14)

Repository totals include every variant; the subset actually needed is smaller.

| Component | Purpose | License | Repo size | On disk now | Fit on 8 GB / notes |
| --- | --- | --- | --- | --- | --- |
| RealVisXL V5 Lightning | Photoreal images | OpenRAIL++ | 41.6 GB repo (6.9 GB used) | ✅ | Fits with offload; keep |
| Wan2.1 T2V 1.3B + **FastWan** transformer | Video | Apache-2.0 | 28.9 / 29.2 GB | ✅ | 4.6–5.0 GB VRAM; keep |
| **Wan2.1 VACE 1.3B** | Reference-image / continuation video for consistency | Apache-2.0 | 19.0 GB | ✅ | 6 GB VRAM, ~7× slower (continuation); R2V unmeasured |
| Phantom (Wan-based subject-to-video) | Identity-preserving video | Apache-2.0 | 62.8 GB repo (1.3B and 14B) | ❌ | 1.3B variant may fit; **unmeasured** — benchmark only after VACE |
| Wan2.2 TI2V 5B | Better quality T2V/I2V | Apache-2.0 | 34.2 GB | ❌ | 5B in bf16 needs ~10 GB VRAM; only with quantisation/offload; likely 3–5× slower — **not recommended** on this GPU |
| LTX-Video 0.9.x | Fast video | "other" (custom) | 47.6–253 GB | ❌ | License must be reviewed before any use |
| SkyReels V2 DF 1.3B | Long video (diffusion forcing) | "other" (custom) | 29.0 GB | ❌ | License review needed |
| FLUX.1-schnell (GGUF) | Better prompt adherence for images | Apache-2.0, **gated** | 57.8 GB repo | ❌ | Q4 GGUF + T5 fits with offload; needs HF login; slower than RealVisXL — **unmeasured** |
| InstantID / IP-Adapter (SDXL) | Same face across images | Apache-2.0 (InstantID also depends on InsightFace models with non-commercial terms) | 4.2 / 19.8 GB | ❌ | Small; license of the face-analysis model must be checked |
| SD 3.5 Medium | Images | "other" (Stability community), gated | 48.9 GB | ❌ | Not better than RealVisXL for photorealism at this size |

---

## 5. Recommended architecture (for this hardware)

```
Prompt ──► Prompt compiler (done) ──► per-scene prompts + cast with appearance
                                          │
                     ┌────────────────────┴───────────────────┐
     Consistency mode OFF (fast)                  Consistency mode ON (slower, opt-in)
     FastWan T2V per scene beat (≤5 s)            1. RealVisXL renders one reference image per
     one clip per beat, hard cuts                    character (1024 px, approved by the user)
                                                  2. VACE 1.3B (on disk) generates each scene with
                                                     the reference image(s)  ← benchmark first
                     └────────────────────┬───────────────────┘
                                          ▼
                 bf16 VAE decode (Draft) / tiled decode (480p) ─► join with cuts ─► validated MP4
GPU worker in its own process (watchdog, VRAM/RAM pre-flight)  ·  jobs persisted in SQLite
```

Principles: keep the models that already work; add consistency through **reference conditioning with a model already on disk** before downloading anything; make the GPU worker restartable without losing jobs; never run the AI backend in a VM that is already 1/3 full.

---

## 6. Implementation phases

Each phase ends with real generations on this PC; a phase is complete only when its acceptance tests (§8) pass.

| Phase | Goal | Work | Downloads |
| --- | --- | --- | --- |
| **0 — Stability** | No stalls or lost work | Memory budget: unload the image model fully (RAM too) before video; pre-flight check of free VM RAM and VRAM with a clear error; GPU worker as a child process with a watchdog (no progress for N s → kill, mark retryable, restart worker); persist jobs in SQLite and resume long videos after restart; sweep orphan temp files; enforce the clip timeout around text-encode and VAE; document the WSL memory requirement and/or stop idle containers while generating | none |
| **1 — Speed without quality loss** | ≥ 1.5× faster Draft | bf16 untiled VAE decode for Draft after a visual A/B check; tiled decode for 480p; cache prompt embeddings per scene; measure 480p after Phase 0 | none |
| **2 — Coherent video** | No ghosting | One clip per scene beat (split beats > 5 s into sub-beats with their own action text) and hard cuts; keep crossfade only for continuation-conditioned clips | none |
| **3 — Character consistency** | Same character across scenes | Reference-image pipeline: character sheet image from RealVisXL → VACE 1.3B R2V per scene; benchmark VACE R2V vs prompt-only on 3 fixed stories; decide by measured identity similarity + manual review; Phantom 1.3B only if VACE fails | Phantom only after approval and benchmark |
| **4 — Image quality** | Correct composition, native resolution | Default image size 1024-class; benchmark FLUX.1-schnell GGUF vs RealVisXL on counts/multi-person prompts (needs HF login); character consistency for images via the same reference sheet (InstantID/IP-Adapter after license check) | FLUX (gated), InstantID — after approval |
| **5 — Recovery & UX** | Users never lose work | Job history page from SQLite, resume button, retry of failed scenes from the UI (re-tested with a real failure), export of finished MP4s | none |

---

## 7. Real benchmark results to date

| Benchmark | Result | Source |
| --- | --- | --- |
| 5 s 480p video | Wan 25 steps 17.3 min → FastWan 3 steps **2.7 min** | `docs/benchmarks/` |
| 5 s Draft video, warm | 112–123 s total | `docs/benchmarks/` |
| Clip stage breakdown, Draft 81 frames | load 42.6 s · encode 6.6 s · denoise 19.4 s · VAE 39.9 s (current) | `docs/speed/` |
| VAE decode options | fp32 tiled 39.9 s · **bf16 untiled 15.8 s (PSNR 57.9 dB)** · bf16 tiled 23.4 s · fp32 untiled 213.6 s | `docs/speed/` |
| VACE continuation | 213.6 s per 33-frame Draft clip, 5.95 GB VRAM, 15.7 GB RAM | `docs/benchmarks/` |
| Long videos | 15 s: 4 min 58 s · 30 s (6 scenes): 6 min 47 s · 60 s: 15.6 min · 120 s: ~65 min GPU | Phase I report |
| Image | RealVisXL 680×384 ~30–70 s incl. queue; 1344×768 ~11 s warm | Phase I / Phase A |
| VRAM leak | none over 4 consecutive jobs (4.24–4.31 GB) | `docs/verification/phase_i/vram_leak_test.log` |
| Memory budget | other containers 7.9 GiB + backend 18.5 GiB > VM 23.5 GiB | §3.7 |
| 480p VAE benchmark | **stalled** (GPU 0–1 %, Docker API 500) — reproduces the stability bug | §3.7 |

---

## 8. Acceptance tests (run on this PC, real models, results saved)

| Priority | Test | Pass criterion |
| --- | --- | --- |
| Prompt | Meadow, wolf/sheep structured, rabbit story, classroom | Every instruction has a status; no `omitted_budget` for video; each scene prompt contains its action and cast |
| Images | Classroom (10 students), 2-person portrait, product shot — 3 seeds each | Native-resolution output; teacher + students present; counts within ±2 for ≤ 5 people; manual review recorded |
| Consistency | Fisherman (6 scenes), girl story (3 scenes), wolf/sheep (4 scenes) | Same clothing colours in every scene incl. hat; identity similarity between scene keyframes above a threshold fixed after the first benchmark; manual review |
| Actions/env | Meadow, fisherman | Named place visible in its scene; main action visible; per-scene checklist recorded |
| Smoothness | Any 30 s video | No ghosted frames at clip joins (frame-diff check + review) |
| Long video | 15 s, 60 s, 120 s Draft; 30 s Quality | Completes without manual restart; exact length; decoded |
| Stability | 3 consecutive 120 s Draft jobs with the other containers running; one 480p 30 s | No stall; if the watchdog fires, the job resumes automatically |
| Recovery | Kill the backend mid-job; restart | Job reappears with its status; resumes from finished clips; retry button works on a real failure |

---

## 9. Remaining limitations (honest)

- **Exact counts, small details and multi-character identity** are limited by SDXL and 1.3B video models; reference conditioning improves identity but does not guarantee it.
- **Speed**: even with every optimisation, a 120 s video on an RTX 3050 will take tens of minutes; Consistency mode will be slower still (VACE measured ~7× per clip for continuation).
- **480p** is the maximum practical video size; 720p is unstable on the 1.3B model and does not fit with larger models.
- **Shared machine**: reliable generation needs the AI backend to have enough VM memory — either raise the WSL limit (32 GB host leaves little for Windows) or pause idle containers (e.g. `sourcebot-qdrant` 4.1 GiB) while generating.
- Larger, better models (Wan 14B, HunyuanVideo, LTX 13B) do not fit 8 GB VRAM at usable speed; they are out of scope on this hardware.

---

## 10. Progress log

### 2026-11-14 — Phase 0 (part) and Phase 1 (part), all verified with real runs

**Stability root cause confirmed.** With the other projects' containers running, the 480p VAE benchmark stalled (GPU 0–1 %, Docker API HTTP 500). After stopping them (`scripts/ai-session.ps1 free-all`, user-approved; 37 containers, nothing deleted), the **same benchmark completed** with no stall. Measured memory per model (`backend/scripts/measure_memory.py`):

| Step | Process RAM | VM RAM available | VRAM free |
| --- | --- | --- | --- |
| idle | 0.5 GiB | 21.7 GiB | 7.0 GB |
| image model loaded | 0.8 GiB (weights memory-mapped) | 21.5 GiB | 7.0 GB |
| **video model loaded** | **14.2 GiB** | 8.2 GiB | 3.65 GB |
| video unloaded + `malloc_trim` | 0.7 GiB | 21.7 GiB | 7.0 GB |

**Changes (backend):**
- `app/services/memory.py`: pre-flight check (video model loads only with ≥ 15 GiB VM RAM and ≥ 4 GB VRAM free; each clip needs ≥ 1.8 GB VRAM free) → clear, retryable `out_of_memory` error instead of a stalled VM; `release()` = gc + CUDA cache + glibc `malloc_trim`.
- `video_engine.py`: VAE in **bf16** (`VIDEO_VAE_DTYPE`); **untiled decode for Draft, tiled for 480p**; prompt-embedding cache per scene; clip deadline also checked before text encoding and before VAE decode; cache cleared on unload/CUDA error.
- `video_storage.py` / `generation_service.py`: half-written `.part.mp4` files removed at startup.
- `scripts/ai-session.ps1`: `free`, `free-all`, `restore`, `status`.

**480p VAE decode (832×480, 81 frames):** fp32 tiled 96.8 s / 4.96 GB · bf16 untiled 265.6 s / 7.32 GB (too close to 8 GB — rejected) · **bf16 tiled 56.0 s / 4.2 GB, PSNR 57.0 dB** (chosen for Quality).

**Acceptance runs after the change (real API jobs):**

| Job | Before | After | Quality |
| --- | --- | --- | --- |
| Meadow 15 s Draft, seed 42, incl. model load | 4 min 39 s | **2 min 35 s (1.8×)** | Frames identical to the previous run (`docs/speed/before_after_meadow.png`) |
| Beach 5 s Quality 480p | 161 s | **122 s (1.3×)** | Sharp, correct (`docs/speed/after_beach_480p.png`) |

**Prompt compiler v2** (user's "Doomsday – Live Review" prompt): markdown headings, `Dialogue:` / `Visual requirements:` sections, quotes spanning two lines, camera directions, quality words, `No cartoon…` requirements (turned into positive "live-action footage" because FastWan has no negative prompt), audio (reported as impossible in silent video), duration lines, and scene details are now handled. Result via the API with the real UMT5 tokenizer: 6 scenes, 111–155 / 511 tokens, 20 included · 2 compressed (4K, lip-sync) · 7 unsupported (title, 4 dialogue blocks, voice, sound effects) — no more "could not be turned into visual instructions". Also fixed: details written after an action were attached to the scene but never sent to the model; characters described with numbers ("30-year-old male reporter") were not recognised. Backend tests: **250 passed**.

**Still open in Phase 0:** GPU worker in a separate process with a watchdog, SQLite job persistence/resume, retry re-test with a real failure.

## 11. What happens next

Phase 0 (stability) first, because every later test depends on runs that do not stall. No model is downloaded until Phase 3/4 benchmarks with models already on disk are done and the download is approved.
