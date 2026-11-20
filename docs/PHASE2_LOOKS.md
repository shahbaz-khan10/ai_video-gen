# Phase 2: natural-looking output with ffmpeg (CPU)

No new AI model and no new download. Everything runs with the ffmpeg build that ships with `imageio-ffmpeg` (already
used to write every video), on the CPU, after the video is generated and before it is validated and published.
Code: `backend/app/services/postprocess.py`; wiring: `GenerationService._complete_video` / `_postprocess` / `_ken_burns`.

## Features

| Option | API field | What it does |
|---|---|---|
| Look | `look`: `none` · `film` · `documentary_bw` · `sepia` · `warm_commercial` | Colour + grain + vignette preset (`postprocess.LOOK_FILTERS`) |
| Enhance | `enhance: true` | `hqdn3d` light denoise, 2x Lanczos upscale, gentle unsharp |
| Ken Burns | image-to-video `quality: "kenburns"` + `camera` | Slow zoom/pan over the uploaded photo with `zoompan`, 24 fps, up to 121 frames; no video model |

Available on text-to-video (single and long videos) and image-to-video. If a Look or Enhance fails, the generated
video is kept unchanged and the job gets a note (`job.notes`), shown in the UI: minutes of GPU work are never thrown
away for a colour filter.

## Measured (RTX 3050 machine, CPU work, 20 Nov 2026)

On a real 576x320, 81-frame clip (5 s) and a real RealVisXL image:

| Step | Time |
|---|---|
| Look `film` / `documentary_bw` / `sepia` / `warm_commercial` | 0.4 / 0.4 / 0.5 / 0.4 s |
| Enhance (576x320 -> 1152x640) | 0.7 s |
| Ken Burns 5 s, 576x320 (zoom_in / pan_right / tilt_up) | 0.4 s each |
| Ken Burns 5 s, 832x480 | 0.6 s |

Through the app (API, end to end):

| Job | Before | After |
|---|---|---|
| Text-to-video 5 s 576x320 (FastWan) | 74 s, no look | 77 s with `documentary_bw` (+3 s incl. job overhead) |
| Image-to-video 5 s | 157 s (Draft, AI) | **7.6 s** with Ken Burns + sepia + enhance (1664x960, 121 frames) |

## AI upscaling: skipped

An AI upscaler (e.g. Real-ESRGAN) would need its own GPU slot inside the backend lock and adds minutes per clip on an
8 GB card; it was not built. The classic Enhance pass is offered instead: it sharpens and enlarges but does not invent
detail. If AI upscaling is wanted later it should run as a separate, measured step after generation.

## Licenses

No new model or dataset. ffmpeg is the binary already bundled by `imageio-ffmpeg` and used for all video writing.
