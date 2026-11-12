# Phase A — Generation Audit and Root-Cause Report

Date: 2026-11-12 · Branch `shahbaz_ai_vdeo` @ `0fc0149` · Hardware: RTX 3050 8 GB, Ryzen 5 7500F, 32 GB RAM, Docker Desktop (WSL2, 24 GB).

Every number below was **measured** with real models (`backend/scripts/benchmark_generation.py`, `backend/scripts/benchmark_wan_image.py`). Raw records, images and videos: `docs/benchmarks/phase_a/`. Nothing here is from mocked tests.

---

## 1. Measured baseline

### Images — RealVisXL V5.0 Lightning (1344×768, 6 steps)

| Test | Load | Generate | Peak VRAM | Prompt adherence (manual check of the saved image) |
| --- | --- | --- | --- | --- |
| T1 classroom | 32 s | 30 s (first image after load; ~11 s warm, measured earlier) | 5.4 GB | ✅ teacher at the front by the blackboard, white shirt, black trousers · ✅ students seated at desks · ❌ **~17 students instead of 10** |

Same prompt with Wan2.1 used as a single-frame image model (832×480, 30 steps): 28 s, 3.7 GB VRAM. ✅ composition and count close to 10 · ❌ **cartoon style**, not realistic. Not a better image model.

### Videos — Wan2.1 T2V 1.3B (25 steps, guidance 5.0)

| Test | Size / frames | Text encode (CPU) | Denoise | VAE decode | MP4 | Total (excl. load) | Peak VRAM |
| --- | --- | --- | --- | --- | --- | --- | --- |
| T2 snow forest (cold, first job) | 576×320 / 33 (2 s) | **118 s** | 99 s (3.95 s/step) | 17 s | 1.5 s | 235 s | 4.5 GB |
| T3 beach (warm) | 576×320 / 33 (2 s) | 5.6 s | 96 s (3.85 s/step) | 16 s | 0.8 s | 119 s | 4.5 GB |
| T3 beach (warm) | 576×320 / 81 (5 s) | 5.4 s | 289 s (11.6 s/step) | 41 s | 0.9 s | 336 s | 4.6 GB |
| User job "monkey dance" (from logs) | 832×480 / 81 (5 s) | — | — | — | — | **1038 s (17.3 min)** | — |

Model load: 83 s cold, 29–38 s warm. Backend container RAM while the video model is loaded: ~15 GB.

Adherence (frames checked manually):
- T2 ✅ man seen from behind, night, snowy pine forest · ❌ a large blurred **phantom figure** appears in the foreground · ❌ falling snow barely visible · ⚠ very dark, jacket colour unclear.
- T3 ✅ golden retriever running on a sunset beach, waves, side tracking — good.
- T4 ❌ not possible: no multi-scene pipeline exists.

---

## 2. Root causes

### 2.1 Prompt understanding (why instructions look "ignored")

Measured on the four test prompts (`PromptUnderstandingEngine.plan_scene`):

| Test | Truth | Planner output |
| --- | --- | --- |
| T1 | 1 teacher + 10 students | `people_count = 0`, no individuals, shot "medium shot from waist up" |
| T2 | snow falling, camera follows from behind | "camera" listed as an **object**; weather and camera movement not extracted |
| T3 | a dog, side tracking | dog not recognised as the subject; human "waist up" shot |
| T4 | village, farmer, 4-part story | key objects "**table**" and "**car**" (substring hits inside "vege**table**s", "**car**ry"); village not recognised; no scene sequence |

Causes:
1. **Keyword lists, not language understanding.** Fixed vocabularies (≈9 indoor and 7 outdoor places, 11 objects, a few person words) and substring matching. Anything outside the lists ("students", "teacher", "farmer", "village", "dog") is invisible.
2. **No validation.** Nothing checks that each instruction in the prompt is represented; extraction errors are silent.
3. **The plan is barely used.** For images only a people-count phrase and the style are added; for **video the plan is not used at all**. The UI never shows it (`/generations/plan` is never called).
4. **No camera/motion/sequence model.** Camera movement, shot type, actions over time and scene order have no representation.

### 2.2 Images

5. **CLIP truncation is *not* the cause for these prompts** — all four are 27–48 CLIP tokens (limit 77). It matters only for long prompts (> ~60 words).
6. **SDXL/CLIP cannot count or bind attributes reliably.** With a clear prompt, layout and clothing were right; the count was wrong (17 vs 10). Earlier failures came from a vague prompt and from the SD-Turbo pipeline that was running at the time (1-step model fed 20–35 steps at 1024 px → merged faces).
7. **No adherence measurement existed**, so regressions could not be seen.

### 2.3 Videos

8. **Video ignores the selected style** — `VideoParams` carries only the raw prompt; the UI's style choice is dropped.
9. **Short or vague prompts** (e.g. "monkey dance") give Wan too little to work with; nothing expands them into a scene description (Wan's own reference code ships a prompt extender for this reason).
10. **Artefacts at draft size** (phantom figure, darkness) — 576×320 is below Wan 1.3B's trained 480p; detail and coherence drop.

### 2.4 Speed

11. **Compute per clip:** 25 steps × 2 transformer passes (classifier-free guidance) = **50 full passes**. Attention cost grows with the square of the token count: 2 s draft = 6,480 tokens; 5 s at 480p = 32,760 tokens (5× tokens, ~25× attention) → 17 min.
12. **Cold starts on every model switch.** The service unloads the video model before every image job and vice versa; the next video job then pays ~83 s load + ~118 s cold text-encoder pass (weights paged in from disk).
13. **VAE decode is significant** — 41 s for 81 draft frames; it becomes the bottleneck once denoising is made faster.
14. **Text encoder on CPU** is fine when warm (5–6 s) — not a main cause.

### 2.5 Duration

15. **5 s is the model's limit, by design.** Wan2.1 is trained on ≤81 frames (16 fps). Longer output requires stitching multiple clips; no scene splitter, clip assembler or continuity mechanism exists.
16. **Wan2.1 T2V cannot continue from a frame.** Last-frame-to-next-scene continuity needs an image/video-conditioned model (e.g. Wan2.1 VACE 1.3B).

### Cost of a 120-second video with today's pipeline (24 × 5 s clips, measured per-clip times)

| Mode | Per 5 s clip | 120 s total |
| --- | --- | --- |
| Draft 576×320 | 5.6 min | **≈ 2.2 hours** |
| 480p 832×480 | 17.3 min | **≈ 7 hours** |

---

## 3. Candidate models (checked, not downloaded)

| Purpose | Model | License | Download | Notes |
| --- | --- | --- | --- | --- |
| Fast video | FastWan2.1-T2V-1.3B-Diffusers (FastVideo) | Apache-2.0 | ~6.0 GB (transformer only; reuses our T5 + VAE) | Same transformer architecture as Wan 1.3B; DMD-distilled for **3 steps, no CFG** (3 passes instead of 50). Official path uses the FastVideo library with sparse attention; in Diffusers it needs a small custom 3-timestep loop (1000, 757, 522). Must be benchmarked for quality. |
| Scene continuity | Wan2.1-VACE-1.3B-diffusers | Apache-2.0 | ~7.2 GB (transformer + VAE; reuses our T5) | `WanVACEPipeline` in Diffusers 0.42; conditions on first/last frames → next scene can start from the previous scene's last frame. Same cost per step as Wan T2V (with CFG). |
| Scene planner | Qwen3-1.7B (or Qwen3-4B) | Apache-2.0 | ~3.4 GB (~8 GB) | Local LLM to turn a prompt/story into a structured, validated scene plan. CPU-runnable; speed to be benchmarked. |
| Image (prompt following) | FLUX.1-schnell | Apache-2.0, gated | ~17 GB | Best prompt adherence, but needs a Hugging Face login (not completed). |
| Image | Lumina-Image-2.0 | Apache-2.0 | ~11 GB | Gemma-based text encoder; not benchmarked. |
| Rejected | LTX-Video 0.9 (research-only licence), CausVid/Self-Forcing LoRAs (licence unclear/non-commercial), Sana (non-commercial) | | | |

Free, no download: Diffusers 0.42 ships training-free caches for Wan (`FirstBlockCache`, `MagCache`, `TaylorSeer`, `FasterCache`) — candidates for a further speed-up, to be benchmarked for quality.

---

## 4. Proposed implementation stages

| Stage | Change | Needs download |
| --- | --- | --- |
| B | Structured scene planner: deterministic clause/entity extraction + local LLM (Qwen3) producing JSON; coverage validation that every clause is accounted for; limitations reported; shown and editable in the UI | Qwen3-1.7B (~3.4 GB) |
| C | Image: keep RealVisXL; prompt built from the validated plan; count/position instructions emphasised; adherence test suite with recorded misses | — |
| D | Video: style and plan applied; prompt expansion from the plan; keep model resident (no unload when RAM allows); draft vs quality presets from benchmarks | — |
| F | Speed: FastWan 3-step path (+ optional cache), VAE decode tuning, warm-model policy | FastWan (~6 GB) |
| E | 120 s: scene splitter → per-scene clips (≤5 s each) → last-frame continuity (VACE) → crossfade transitions → FFmpeg concat → duration validation; per-scene status, files and retry | VACE 1.3B (~7.2 GB) |
| G | UI: duration up to 120 s, Draft/Quality, scene breakdown editor, per-scene progress and retry, ETA from benchmark data | — |
| H | Fixed adherence benchmark suite (T1–T4) re-run after each stage | — |

Expected (to be verified by benchmark, not promised): 3-step FastWan would cut denoising per clip by up to ~16×; a 120 s draft would then be dominated by VAE decode and model switching rather than denoising.
