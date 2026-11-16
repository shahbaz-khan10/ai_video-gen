# Prompt agent, voice and lip-sync: report

Dates: 2026-11-16. Hardware: RTX 3050 8 GB, 32 GB RAM (WSL VM 23.5 GiB). Every number below comes from a real run.
Evidence files: `docs/phase_k/agent/`, `docs/speech/`, `docs/talking/`.

## 1. Prompt agent: Florence-2-base (MIT, 0.46 GB, about 0.44 GB of VRAM)

**What it does** (`backend/app/services/prompt_agent.py`; on by default, switchable in the UI):

1. **Image-to-video:** it describes the uploaded photo (people, clothes, objects, background) and adds that
   description to the video prompt. Sentences about mood and facial expression are left out. If the background is
   plain, it also adds "Plain *grey* background that stays the same colour".
2. **After generating:** it counts what the prompt asked for (for example "three sheep"), or the people and animals
   that were in the photo. For a plain background it also checks that the colour of the first and last frame did not
   change.
3. **When a check fails:**
   - Image or image-to-video: it generates **once more** with the next seed and keeps the better result.
   - Text-to-video: it **only reports** the failure. Retrying did not fix counts and doubles the video time.

**It does not make generation faster.** Florence-2 takes about 1 s per caption and 0.2–0.6 s per detection on the
GPU, or 7 s on the CPU. A retry costs one whole extra generation.

| Test | Without the agent | With the agent |
| --- | --- | --- |
| User's photo, 480p, "turns his head" | background turned **green**, arms uncrossed | background **grey**, arms crossed; checks: person 1 ✓, background ✓ (`before_after_agent.jpg`) |
| "Four brown dogs" (image) | 5 dogs, 12 s | first image had 5 → retry had **exactly 4**, 26 s (`dogs_before_after.jpg`) |
| "Three sheep and two children" (image) | 4 sheep, 1 child | retry was no better: the first image is shown and the failure is reported (54 s) |
| Image-to-video, 3 s Draft with the agent | — | 45 s per job, checks passed (2 runs) |

**Counting accuracy and fixes:**
- *Phrase grounding* merged all the sheep in a video frame into one box. *Object detection* is used instead.
- Florence-2 labels sheep as "animal". The agent now counts that label as a match.
- It added one extra box around the whole group of dogs. Group boxes are now dropped.
- "human beard" matched "bear". Labels are now matched as whole words only.
- After these fixes the counts match the pictures: sheep 4, child 1, dogs 5, photo sheep 4.

## 2. Voice: Chatterbox Multilingual 0.1.7 (Resemble AI, MIT, 0.5B)

It runs in its own container (`speech/`). It needs torch 2.6, transformers 5.2 and diffusers 0.29, which conflict
with the backend. The model is unloaded after every request.

| Text | language_id | Result | Generation time |
| --- | --- | --- | --- |
| English | en | ✅ 7.1 s of audio | 33 s (first run, includes warm-up); later runs 15–18 s including the model load |
| Hindi (Devanagari) | hi | ✅ 6.7 s | 8.6 s |
| Roman Urdu | hi | ✅ 6.8 s | 7.2 s |
| **Urdu script** | hi | ❌ **39 s of audio for a 6 s sentence**: the model invented sounds | — |

- VRAM: 3.0–3.2 GB. The first load took 247 s, including the 3 GB download.
- **Urdu:** Chatterbox has no Urdu model. Urdu is spoken with the Hindi model and must be written in **Roman letters
  or Hindi script**. Urdu script is rejected with a clear message.
- **Voices:** a voice is copied from a 10–20 s recording. No male or female recordings have been provided yet, so
  every test used the built-in voice. The app has an "Add voice" button: name + male/female + a recording.
- How natural the Hindi and Urdu speech sounds has **not been checked by ear** in this report. The WAV files are in
  `docs/speech/` for the user to listen to.

## 3. Lip-sync: MuseTalk 1.5 (MIT code; the models may be used for any purpose)

It runs in its own container (`lipsync/`: torch 2.0 + OpenMMLab). Each request runs in a child process, so the GPU
memory is returned when it finishes.

| Source | Speech | Voice | Lip-sync | Total |
| --- | --- | --- | --- | --- |
| User photo, English | 4.9 s | 15 s | 50 s | 66 s |
| User photo, Roman Urdu | 6.4 s | 18 s | 50 s | 69 s |
| User photo, Hindi | 5.4 s | 16 s | 41 s | 57 s |
| Generated 3 s video of the photo, Roman Urdu | 6.6 s | 98 s (cold model load) | 69 s | 168 s |
| In the browser (Make it talk) | 5.9 s | | | ✅ video with sound + download link |

- Every output is H.264 video with AAC audio, and its length equals the speech length.
- The mouth opens and closes with the words (`photo_en_mouth.jpg`). The rest of the face stays the same.
- On a photo only the mouth moves.
- If the audio is longer than the video, MuseTalk plays the frames forwards and backwards. No new frames are
  invented.

## 4. Failures found and fixed
| Problem | Fix |
| --- | --- |
| mmpose import: "numpy.dtype size changed" / "Numpy is not available" | numpy 1.23.5 and xtcocotools compiled against it (fixed in the running container; added to `lipsync/Dockerfile` but **not yet verified by a rebuild**) |
| ffmpeg could not encode a 795 px wide photo (H.264 needs even sides) | The image is cropped to even sides and capped at 1280 px |
| The output could not be moved from /tmp to /outputs (different disks) | `shutil.move` |
| The speech image still had a placeholder `app.py` | The service code is now mounted from the repo, so code changes no longer need an image rebuild |
| **Docker's containerd crashed with SIGBUS**: drive C: had 0 GB free | The user freed space (C: now 27 GB free); unused Docker build cache pruned (16.7 GB) |
| A finished background build recreated the speech container during a job (exit 137) | Services are now started with `--no-build` |
| An image-to-video job took 9 min right after the Docker restart | Models were read from a cold disk cache; the next two runs took 45 s each |

Tests: backend 312 passed, 6 skipped; frontend 26 passed.

## 5. Limits and open points
- **Disk:** Docker's disk file is 182 GB, and C: has only 27 GB free. Large downloads or builds can fill it again.
  Compacting the Docker disk is a separate step that needs the user's approval.
- No Urdu script, and no male/female voices until the user provides recordings.
- The agent finds count mistakes but often cannot fix them. A retry with a new seed helped in 1 of 2 image tests.
- Talking-video jobs are kept in memory, so they are lost when the backend restarts.
