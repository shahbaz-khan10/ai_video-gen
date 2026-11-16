# Phase K — Image-to-Video: Report

Date: 2026-11-14 to 2026-11-16 · Hardware: RTX 3050 8 GB, Ryzen 5 7500F, 32 GB RAM (WSL VM 23.5 GiB), Docker backend.

Every number below comes from a real generation on this machine. No output is mocked. The only fake engine is the
one in the unit tests, which writes a tiny real MP4 and is labelled as such. The evidence files are in `docs/phase_k/`.

## 1. Summary

- **Image-to-video works end to end in the app:** upload → describe the motion → settings → generate → preview →
  download. It was tested through the HTTP API (16 real jobs) and in a real browser (Edge, Playwright).
- **Model:** Wan2.1 VACE 1.3B (Apache-2.0). The uploaded image is the first frame, and it is also passed as VACE's
  reference image.
  - **Draft** mode: the VACE weights with FastWan's 3-step distilled base blocks.
  - **Quality** mode: VACE as released, 20 steps with guidance.
- **Nothing was downloaded.** All weights were already on disk from earlier phases.
- **Draft is the default because it kept the photo best in our tests.** Clothing, background and objects stayed the
  same, and faces stayed recognisable (with some smoothing). Quality moves more but changes faces and details more,
  and is about 4× slower.
- **Not solved:**
  - Faces are not perfectly preserved. The portrait's skin became smoother and lighter.
  - A 5 s clip of sheep walking toward the camera changed the number of sheep (4 → 2).
  - Fast or large movements are weak.

## 2. Model evaluation (before any download)

Sizes and licences come from the Hugging Face API (`?blobs=true`). The VRAM figures are estimates from the parameter
counts unless they say "measured".

| Model | Licence | Download size | Fits 8 GB? | Decision |
| --- | --- | --- | --- | --- |
| **Wan2.1 VACE 1.3B** (diffusers) | Apache-2.0 | 19.0 GB repo, **already on disk** (transformer 6.7 GB fp32) | Yes, **measured** 6.4 GB peak at 576×320 / 49 frames | **Selected** |
| Wan2.1 I2V **14B** 480P | Apache-2.0 | 90.1 GB | No (~28 GB of bf16 weights) | Rejected |
| "Wan2.1 I2V 1.3B" | — | — | — | **No official model exists.** Wan2.1 image-to-video is 14B only. |
| alibaba-pai Wan2.1-Fun 1.3B InP (V1.0 / V1.1) | Apache-2.0 | 19.8 GB repo; new files needed ≈ 7.9 GB (3.13 GB transformer + 4.77 GB CLIP) | Probably (1.3B) | Not downloaded. It uses the VideoX-Fun format (not diffusers), needs 20+ steps like VACE, and has no distilled version. VACE on disk does the same job. |
| Wan2.2 TI2V 5B | Apache-2.0 | 34.2 GB | No in bf16 (~10 GB); only with offload, several times slower | Rejected on this GPU |
| CogVideoX-5B-I2V | CogVideoX licence ("other") | 21.6 GB | Only with offload; slow | Rejected (5B; restrictive licence) |
| LTX-Video 0.9.x / 13B | Custom licence ("other") | 47.6–254 GB | 2B variants might fit | Not downloaded; the licence needs review first |
| GGUF-quantised Wan 14B I2V (community) | Apache-2.0 base | 8–10 GB per quant | Borderline; needs ComfyUI/GGUF loaders | Not tested; on a 3050 a 14B model would take many minutes per clip |

Disk: 48 GB free on C:. RAM: the backend VM has 23.5 GiB.

**FastWan does not do image-to-video on its own.** Its transformer has 16 input channels (text only). Image
conditioning comes from VACE's extra blocks. Draft mode works because VACE was trained with the Wan2.1 T2V 1.3B base
frozen, and FastWan is that same base distilled. All 825 base tensors match by name and shape, so FastWan's base
blocks were copied into VACE. This combination is our own and is not an official model, so it was only accepted after
the measurements in §5.

## 3. What was built

### Backend
| File | Change |
| --- | --- |
| `backend/app/services/upload_storage.py` (new) | Upload checks and storage. The format is read from the bytes (JPG/PNG/WebP only), not the file name or header. Limits: 10 MB, 40 MP (decompression-bomb guard), sides 256–8192 px. The file is fully decoded (corrupt files are rejected), rotated by its EXIF tag, transparency is flattened, and it is re-encoded as an RGB PNG (metadata/GPS dropped) and saved as `<uuid>.png`. Files are deleted after 24 h. |
| `backend/app/api/routes/uploads.py` (new) | `POST /api/v1/uploads/images`. The body is the raw file, so no multipart dependency is needed. Errors are 413 / 415 / 422 with clear messages. |
| `backend/app/core/limits.py`, `main.py` | Per-path body limit: 10 MB for uploads only. All JSON endpoints keep the 64 KB limit. |
| `backend/app/schemas/generation.py` | `ImageToVideoRequest`: `source_image.upload_id`, `duration_seconds` 2/3/5, `resolution` standard/large, `quality` draft/quality, `motion` subtle/normal/strong, `camera` none/static/zoom_in/zoom_out/pan_left/pan_right/tilt_up/orbit, `seed`. Settings that are not supported (e.g. `steps`) are rejected. |
| `backend/app/services/video_engine.py` | Image-to-video in the same engine. One text encoder and one VAE are shared, and only the transformer is swapped (T2V ↔ VACE Draft ↔ VACE Quality). The image is centre-cropped to the chosen aspect (never stretched). Cancellation is checked before and between steps. VACE is loaded straight onto the GPU, and FastWan's tensors are streamed into it one at a time (RAM fix, §7). |
| `backend/app/services/generation_service.py` | Image-to-video jobs. The final prompt is the user's motion text plus the motion/camera words, then "keep the same people…". No style words are added, because they would repaint the photo. New endpoints: `POST /generations/{id}/cancel` (queued: immediate; running: next step) and `POST /generations/{id}/retry` (same settings and seed). Queued→running and cancel are now atomic (§7). |
| `backend/app/services/image_engine.py` | Unloading the image model now gives its RAM back (§7, the user's "Server out of memory" error). |
| `backend/app/api/routes/generation.py`, `health.py` | Cancel/retry routes. Image-to-video availability in `/validate`. `/info` reports durations 2/3/5. |
| `backend/tests/test_i2v.py` (new) + updated tests | 33 test cases: uploads (each format, EXIF, alpha, empty, PDF, GIF, truncated, too small, >10 MB, JSON limit kept), settings, prompt, job flow, unknown upload, model missing, cancel running/queued, retry, cancel race regression. **288 passed, 6 skipped.** |
| `backend/scripts/benchmark_i2v.py`, `phase_k_app_tests.py`, `analyze_i2v.py`, `check_image_unload.py` (new) | The benchmark, real app tests, metrics and RAM check used for this report. |

### Frontend
| File | Change |
| --- | --- |
| `src/components/studio/use-image-selection.ts` | Checks type, size and dimensions in the browser and decodes the image (corrupt files are caught), then uploads it to the backend. Shows the uploading / ready / failed states, with an "Upload again" retry. |
| `src/components/studio/image-uploader.tsx` | Preview, size in pixels and MB, upload state, replace/remove buttons, and an honest privacy note. |
| `src/components/studio/i2v-options.tsx` (new) | Mode (Draft/Quality with measured time estimates), clip length, motion strength, camera presets. |
| `src/components/studio/create-workspace.tsx` | Image-to-video runs real jobs. The aspect ratio is picked from the photo. The size selector (Small/480p) appears in Draft only. The style selector is hidden for image-to-video. Also: seed, Cancel button, "Stopping…" state, preview and download. |
| `src/lib/api/client.ts`, `src/types/api.ts`, `generation-check.ts`, `job-view.ts`, `studio-options.ts`, `video-options.tsx` | Upload/cancel/retry API calls, types, payload, error titles, measured estimate table. |
| `create/page.tsx`, `settings/page.tsx`, landing footer/workflow | Removed the stale "video is coming soon" text (roadmap bug B8). |

## 4. Hardware benchmarks

### Model comparison (benchmark script, 49 frames = 3 s, 576×320 / 320×576, seed 4242)
| Variant | Steps / CFG | Generate time | Peak VRAM | Face kept? | Notes |
| --- | --- | --- | --- | --- | --- |
| VACE as released | 20 / 5 | 220 s | 6.4 GB | moderately | natural head turn |
| VACE | 8 / 5 | 98 s | 6.4 GB | moderately | **flickered on every frame** in the river test (frame diff 20–54 vs ~2) → rejected |
| VACE + FastWan base | 3 / none | 37 s | 6.4 GB | lighter, rounder face | |
| **VACE + FastWan base + reference image (Draft)** | 3 / none | **43–61 s** | 6.4 GB | **closest to the photo** | smooth (largest frame jump ≤ 2.6× median) |
| VACE + reference (Quality) | 20 / 5 | 237–245 s | 6.4 GB | drifts more than Draft | more motion; no flicker |

### In the app (real jobs; wall time includes ≤3 s of polling)
| Mode | Size | Clip | Time |
| --- | --- | --- | --- |
| Draft | 576×320 | 2 s (33 frames) | 51 s |
| Draft | 576×320 | 3 s (49 frames) | 51–72 s |
| Draft | 576×320 | 5 s (81 frames) | 166 s |
| Draft | 832×480 | 3 s | 175 s (including a switch from text-to-video) |
| Quality | 576×320 | 2 s | 187 s (including a switch) |
| Quality | 576×320 | 3 s | 259–262 s |
| First image-to-video job after a backend start | — | — | +40–80 s model load |
| Switching transformer (T2V ↔ I2V) | — | — | ~20–30 s |
| Text-to-video right after image-to-video | 576×320 | 2 s | 22–34 s (no regression) |

Draft at 480p and 5 s, and Quality at 5 s, were **not measured**. The UI estimates for them (420 s / 600 s) are
extrapolated from the measured scaling and are marked as estimates in `studio-options.ts`.

### Memory
- VRAM: 6.4 GB peak allocated (576×320, 49 frames), the same for Draft and Quality.
- Process RAM after the fixes: **17.7 GB peak** when image-to-video is the first job. **18.7 GB peak** across the
  sequence text-to-video → I2V Quality → I2V Draft. **12.5 GB** steady state. Before the fixes it was **22.7 GB**
  (§7).

## 5. Real tests (5 required images)

The test photos were generated with the app's own RealVisXL model (`docs/phase_k/inputs/`, sheet
`inputs_sheet.jpg`), because no user photos were provided. Each video was looked at frame by frame (4-frame strips
`*_strip.jpg`, face crops `bench/draft_faces.jpg`), and the metrics come from `analyze_i2v.py`
(`app/analysis.json`).

| # | Test | Draft result (3 s) | Frame 0 PSNR vs photo | Largest jump vs median | Verdict |
| --- | --- | --- | --- | --- | --- |
| 1 | Portrait, subtle face movement | Same woman, scarf and hair exact; a slight smile. **The skin gets smoother and lighter, and the eyes softer.** | 33.0 dB | 1.96× | ⚠️ identity mostly kept, visible drift |
| 2 | Person standing, natural movement | Waves and lowers his hand. Face, beard, jacket, shirt, trousers and park all kept. | 31.8 dB | 1.99× | ✅ |
| 3 | Sheep in a meadow | 3 s: same 4 sheep, small movements. **5 s: they walk toward the camera and at the end only 2 large sheep remain plus a faint ghost sheep.** | 31.7 dB | 1.81× / 1.97× | ✅ 3 s · ❌ 5 s (objects not preserved) |
| 4 | Landscape, river and clouds | Water ripples, clouds drift, trees steady. With the zoom-in preset: a gentle zoom. | 32.0 dB | 1.75× / 1.29× | ✅ (the flow is subtle) |
| 5 | Person with a detailed background | Turban, beard, red coat, fruit stall, lamps and blurred shoppers all kept. 480p also tested. | 31.0 / 33.4 dB | 1.78× / 2.37× | ✅ (the face gets slightly younger/softer) |

The Quality runs (`bench/quality_all.jpg`, `bench/draft_vs_q20.jpg`) showed stronger motion: a wider wave, the river
visibly flowing. But the man's face changes expression and shape more, and the river grew new rocks. For that reason
Draft is the default and the UI says so.

**Browser test** (`docs/phase_k/browser/`, Edge):
1. A text file named `.png` was rejected in the browser ("damaged or can't be read").
2. The real photo uploaded and showed 1344×768 · 1.4 MB · Ready.
3. Cancel during the first run stopped the job right after the model load, and the next job started with no queue.
4. A generation finished and the MP4 played in the preview, with a Download link.

## 6. Identity and consistency: honest assessment
- **Clothing, colours, background, objects and composition** were kept in every 2–3 s Draft clip.
- **Faces** stay recognisably the same person. They are not pixel-identical: the 1.3B model smooths skin and shifts
  the tone a little, and the portrait was affected most. **Perfect identity preservation is not claimed.**
- **Longer clips (5 s) with big motion** can lose or merge objects (the sheep test).
- **Prompt-following motion:** gentle actions work (smile, wave, ripples, zoom). Walking, running and large camera
  moves are weak or partial.

## 7. Failures found and fixed (all found in real runs)
| Problem | How it was found | Fix |
| --- | --- | --- |
| "Server out of memory: 10.5 GiB available, 15 needed" (the user's report) | The backend kept 11.6 GB after the image model unloaded. Reproduced with `check_image_unload.py`: 7.3 GiB stayed after unload. | Unload now calls `malloc_trim` (1.2 GiB remains), and the video preflight releases memory before it measures. Retested: image job → video job succeeded. |
| 8-step Quality flickered on every frame | River test, per-frame differences | Quality now uses 20 steps (smooth) |
| Quality after Draft produced coloured blobs (frame-0 PSNR 11.6 dB, `k2_standing_quality_3s_wrong_scheduler`) | App test order Draft → Quality | The transformer switch built its scheduler from the previous mode's DMD scheduler. It now always uses Wan's own scheduler config. Retested: correct output. |
| 22.7 GB peak RAM (VM is 23.5 GB) | `VmHWM` after the app tests | VACE is loaded straight to the GPU, and FastWan's tensors are streamed one at a time into the GPU weights. Image-to-video-first loads skip the text-to-video transformer. Now 17.7–18.7 GB peak. |
| Cancel showed "Cancelled" but the job kept running and the next job queued behind it | Browser test | Atomic queued→running and cancel transitions, plus a regression test. Retested in the browser: fixed. The UI shows "Stopping…" while a model load finishes. |
| Poll script lost its HTTP connection during the 480p run | App test | The job itself completed; its timing was taken from the job record. |

## 8. Known limitations
- Faces drift slightly. Fast/large motion is weak. 5 s clips with strong motion can change the number of objects.
- The image is centre-cropped to 16:9, 9:16 or 1:1. Edges outside that crop are lost (the closest ratio is chosen
  automatically).
- Videos are silent, at most 5 s, 16 fps, and up to 480p.
- Motion strength is expressed through words in the prompt; the model has no numeric motion control.
- Uploads are deleted after 24 h. Jobs are still kept in memory (lost on backend restart; roadmap B3).
- Cancelling during the first model load takes effect after the load (up to ~1–2 min).
- The "Image model ready" pill in the preview header is still shown in video modes (roadmap B7, not fixed in this
  phase).
- Draft mode combines VACE with FastWan's base. This is our own, measured combination, not an official model
  release.

## 9. Evidence
- `docs/phase_k/inputs/`: the 5 test photos and `inputs_sheet.jpg`
- `docs/phase_k/bench/`: model-comparison videos, `i2v_report.json`, `portrait_compare.jpg`, `draft_all.jpg`,
  `quality_all.jpg`, `draft_vs_q20.jpg`, `draft_faces.jpg`
- `docs/phase_k/app/`: videos made by the app, `app_runs.json`, `analysis.json`, `check1.jpg` (wrong-scheduler bug,
  Quality, 5 s sheep, zoom, 480p)
- `docs/phase_k/browser/`: browser screenshots and log
