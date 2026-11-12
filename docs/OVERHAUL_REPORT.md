# Generation quality, prompt accuracy & 2-minute video — final report

Date: 2026-11-12 · Branch `shahbaz_ai_vdeo` (on top of `0fc0149`) · Hardware: RTX 3050 8 GB, Ryzen 5 7500F, 32 GB RAM, Docker Desktop (WSL2, 24 GB).
Baseline and root-cause analysis: [PHASE_A_GENERATION_AUDIT.md](PHASE_A_GENERATION_AUDIT.md). Every number here was measured with the real models. Raw records, videos and frame sheets are in `docs/benchmarks/` (`phase_a/` = before, `phase_h/` = after). Nothing comes from mocked tests.

---

## 1. Root causes (summary of Phase A)

1. **Keyword planner, not prompt understanding**: tiny vocabularies and substring matching (T1 found 0 people; "vege**table**s" → table, "**car**ry" → car). No check that each instruction was used.
2. **The plan was not used for video at all**, and video ignored the style selector.
3. **Slow sampler**: Wan2.1 with 25 steps and guidance = 50 transformer passes per clip; 5 s at 480p took 17.3 min.
4. **81-frame limit (~5 s)** and no multi-scene pipeline: anything longer, or any story, was impossible.
5. Cold starts from switching image/video models; the 11 GB text encoder runs on CPU (needed on 8 GB VRAM).
6. SDXL/CLIP cannot count exactly (17 students drawn for 10) — a model limit, now reported to the user instead of hidden.

## 2. What changed

| Area | Change | Files |
| --- | --- | --- |
| Prompt understanding | New rule-based planner: whole-word lexicons, counts ("ten students", "a group of"), characters with clothing/position/action, places, weather, time, lighting, camera shot/angle/movement, objects, negations, ordered story beats (both "walking…, meeting…" and "She makes tea. She walks…"; "wearing…" stays a description) | `backend/app/services/scene_planner.py`, `backend/app/schemas/scene_plan.py` |
| Validation | Every clause of the prompt is checked: planned / partial / not understood, and whether it reaches the model. Known model limits are listed (counts above 4, left/right, text, still-image camera motion, unnamed character looks in multi-scene videos) | `scene_planner.validate` |
| Images | Planner output feeds the RealVisXL prompt (user's words first, counts restated, style) and the negative prompt | `backend/app/services/image_engine.py` |
| Video prompts | Each clip gets its scene text + characters with clothing + **its own scene's place and time** + camera + style (the style selector now applies to video) | `scene_planner.build_video_prompt` |
| Fast video | **FastWan2.1** 3-step DMD transformer replaces 25-step sampling + guidance (default `VIDEO_SAMPLER=fastwan`; `wan` still available) | `backend/app/services/video_engine.py`, `backend/app/core/config.py` |
| Long video | 15/30/60/90/120 s: scenes → clips of ≤ 81 frames → joined (crossfade inside a scene, cut between scenes), trimmed to exact frame count, decoded and validated. Partial clips are kept for **per-scene retry** | `backend/app/services/long_video.py`, `generation_service.py`, `video_storage.py` |
| API | `POST /generations/scene-plan`, `POST /generations/{id}/scenes/{n}/retry`; jobs report `plan`, `scenes[]`, `clips_total`, `clips_completed`; `/info` reports `video_sampler` and FastWan's license | `backend/app/api/routes/*`, `backend/app/schemas/generation.py` |
| UI | Video durations up to 2 min, Draft/Quality, steps hidden for FastWan, **Plan scenes** panel (how the prompt was understood, limitations, editable scenes and lengths), per-scene progress with clip counts and retry, honest ETA from the job's own pace | `src/components/studio/create-workspace.tsx`, `scene-plan-panel.tsx`, `scene-progress.tsx`, `video-options.tsx`, `src/lib/generation/*`, `src/types/api.ts`, `src/lib/api/client.ts` |

## 3. Models evaluated

| Model | License | Size | Result | Decision |
| --- | --- | --- | --- | --- |
| RealVisXL V5.0 Lightning | OpenRAIL++ (already in use) | 6.9 GB | Best photoreal images; counts unreliable | **Kept** for images |
| Wan2.1 T2V 1.3B as image model (1 frame) | Apache-2.0 | (shared) | Right composition, cartoon look | Rejected for images |
| Wan2.1 T2V 1.3B (25 steps + CFG) | Apache-2.0 | 28.9 GB | Phantom figure / dark in T2; 17.3 min for 5 s 480p | Kept as text encoder + VAE; sampler optional |
| **FastWan2.1 T2V 1.3B** (FastVideo) | **Apache-2.0** | 5.96 GB | T2: blue jacket and falling snow visible, no phantom; 6× faster | **Selected** (default) |
| Wan2.1 VACE 1.3B (last-frame continuity) | Apache-2.0 | 7.7 GB | Works (first-frame diff 3.4/255) but 213 s per 33-frame draft clip (~7× slower), 6 GB VRAM, 15.7 GB RAM | Not enabled (`continuity: "last_frame"` → 501) |
| Qwen3-1.7B as LLM planner (CPU) | Apache-2.0 | 4.1 GB | 77–174 s per prompt; collapsed the 4-scene story to 1 | Not wired in; benchmark script only |

No paid or remote API is used anywhere.

## 4. Speed before / after (RTX 3050, measured)

| Job | Before (Wan 25 steps + CFG) | After (FastWan 3 steps) |
| --- | --- | --- |
| 5 s draft 576×320 (81 frames), warm | 336 s | **112–123 s** (denoise 18–24 s; VAE decode 47–82 s is now the largest part) |
| 5 s 480p 832×480 (81 frames) | 1038 s (17.3 min) | **161 s** (2.7 min) |
| 2 s draft (33 frames), warm | 119 s | 30–46 s |
| 15 s, 3 scenes, draft (3 clips, through the API) | impossible | **4 min 58 s** (incl. model load) |
| 120 s, 6 scenes, draft (30 clips, through the API) | impossible | **~65 min of GPU time** (≈100 s/clip warm, up to ~3.7 min/clip when VRAM was full and Windows spilled to shared memory) |

Peak VRAM 4.6–5.0 GB; backend RAM ~15 GB while the video model is loaded.

## 5. Prompt adherence

| Test | Before | After |
| --- | --- | --- |
| T1 classroom (image) | planner: 0 people | planner: 11 people (1 teacher + 10 students), teacher's clothes and position extracted; image count still approximate (SDXL limit, now shown as a limitation) |
| T2 snow forest (video) | phantom figure, snow barely visible, dark | man in blue jacket from behind, falling snow, no phantom |
| T3 beach (video) | good | good (side tracking, sunset, waves) |
| T4 story (video) | not possible | 4 ordered scenes |
| 15 s "girl wakes up / tea / park" | not possible | first run: every clip showed kitchen and tea (global setting + whole-story context) → fixed; second run: bedroom → kitchen → park bench, each scene correct. The girl's look changes between scenes because the prompt gives none; the plan now warns about this |

## 6. 2-minute video

**Maximum tested duration: 120 s** — a real run through the API, draft 576×320, seed 21. Request: `docs/benchmarks/phase_h/long120_request.json`; result `long120.mp4` (1920 frames, exactly 120.0 s, 41 MB, decoded and validated), frame sheet `long120_sheet.png`.

Prompt: an old fisherman (white beard, yellow raincoat, blue wool hat) → pushes boat to sea at dawn → rows at sunrise → casts net → hauls silver fish in the afternoon → rows to harbor → cooks fish by a beach fire in the evening. Planned as 6 scenes × 20 s, 5 clips of 73 frames each (30 clips).

What happened, honestly:
1. First run: clips 1–13 done in ~25 min, then **`CUDA error: unknown error`** (VRAM 7.7 / 8.2 GB used, Windows desktop apps share the GPU). After this error the process cannot use CUDA again; the in-process scene retry failed the same way.
2. Fixes: CUDA driver errors now return `gpu_error` with a clear message and drop the pipeline; `_release` no longer masks the real error; clip folders are keyed by content (model, size, fps, steps, seed, scene prompts), so after `docker compose restart backend` the same request with the same seed reuses finished clips (test: `test_after_a_restart_the_same_request_reuses_finished_clips`).
3. Second run after restart: 13 clips reused, 17 generated, 39.4 min wall-clock; completed.

Adherence (frame sheet): the same white-bearded fisherman in a yellow raincoat in all 6 scenes; scenes in the right order and places (sea at sunrise, net, silver fish, harbor with boats, fire on the beach). Deviation: the hat is blue in scene 1 and black afterwards.

## 7. Known limitations (honest)

- Characters can change between scenes: each clip is generated from text only. Describing hair, age and clothing helps; true identity lock needs last-frame/reference conditioning (VACE), which is ~7× slower here.
- Exact counts above ~4 people, left/right placement and readable text are unreliable in both models.
- Draft is ~320p; Quality (480p) costs ~1.5–2× more time. 720p is not offered (unstable on 1.3B).
- A 2-minute video takes about an hour on this GPU, and longer if other apps use video memory. Jobs are in memory: a backend restart loses the job; resubmitting the same request with the same seed reuses its finished clips.
- With VRAM nearly full, Windows/WSL can reset the GPU (`gpu_error`); the backend must then be restarted.
- The rule planner understands common English phrasing; unusual wording can be "partly understood" — the UI shows exactly which clauses.

## 8. Tests

Backend: 229 passed, 3 skipped (`pytest`, in the backend Docker image). Frontend: 26 passed (`npm test`), `tsc --noEmit` clean, `eslint` 0 errors.
