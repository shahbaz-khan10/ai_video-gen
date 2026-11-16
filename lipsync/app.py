"""Lip-sync service: MuseTalk 1.5 (MIT code; models free for any use) moves the mouth in a video or photo to match a
speech WAV.

Runs in its own container (torch 2.0 + OpenMMLab). Each request runs MuseTalk's own inference script in a child
process, so all GPU memory is returned when it exits and the video models can load again. Files are exchanged
through the shared /outputs volume. If the audio is longer than the video, MuseTalk plays the frames forward and
backward to cover it (no new frames are invented).
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import threading
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

OUTPUTS = Path("/outputs")
MUSETALK = Path("/musetalk")
app = FastAPI(title="AI Video Studio lip-sync")
_lock = threading.Lock()


class LipSyncRequest(BaseModel):
    video_path: str  # under /outputs: an MP4 or a still image (png/jpg)
    audio_path: str  # under /outputs: a WAV
    fps: int = 25


def _inside_outputs(path: str) -> Path:
    p = Path(path).resolve()
    if OUTPUTS.resolve() not in p.parents or not p.is_file():
        raise HTTPException(404, f"Not found under /outputs: {path}")
    return p


def _even_image(path: Path, tmp: Path) -> Path:
    """H.264 (yuv420p) needs even width and height; a 795 px wide photo made ffmpeg fail (measured). Crops 1 px
    where needed and caps the long side at 1280 px (MuseTalk works on a 256 px face crop anyway)."""
    import cv2

    img = cv2.imread(str(path))
    h, w = img.shape[:2]
    scale = min(1.0, 1280 / max(h, w))
    if scale < 1.0:
        img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
        h, w = img.shape[:2]
    img = img[: h - h % 2, : w - w % 2]
    out = tmp / "source.png"
    cv2.imwrite(str(out), img)
    return out


def _to_25fps(path: Path, tmp: Path) -> Path:
    """MuseTalk is trained on 25 fps video and maps audio to frames at that rate; our 16 fps clips made the mouth run
    out of step with the voice (user report). Resample to 25 fps first, as MuseTalk's README recommends."""
    out = tmp / "source25.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", str(path), "-vf", "fps=25", "-c:v", "libx264", "-crf", "16",
         "-pix_fmt", "yuv420p", str(out)],
        check=True, capture_output=True,
    )
    return out


@app.get("/health")
def health() -> dict:
    ok = (MUSETALK / "models/musetalkV15/unet.pth").is_file()
    return {"status": "ok" if ok else "models_missing", "busy": _lock.locked()}


@app.post("/lipsync")
def lipsync(req: LipSyncRequest) -> dict:
    video = _inside_outputs(req.video_path)
    audio = _inside_outputs(req.audio_path)
    out_dir = OUTPUTS / "talking"
    out_dir.mkdir(parents=True, exist_ok=True)
    name = f"{uuid.uuid4()}.mp4"
    with _lock, tempfile.TemporaryDirectory() as tmp:
        if video.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"):
            video = _even_image(video, Path(tmp))
        else:
            video = _to_25fps(video, Path(tmp))
        config = Path(tmp) / "task.yaml"
        config.write_text(f'task_0:\n  video_path: "{video}"\n  audio_path: "{audio}"\n  result_name: "{name}"\n')
        started = time.perf_counter()
        proc = subprocess.run(
            [
                "python", "-m", "scripts.inference",
                "--inference_config", str(config),
                "--result_dir", tmp + "/results",
                "--unet_model_path", "models/musetalkV15/unet.pth",
                "--unet_config", "models/musetalkV15/musetalk.json",
                "--version", "v15",
                "--use_float16",
                "--fps", str(req.fps),
                "--ffmpeg_path", "/usr/bin",
            ],
            cwd=MUSETALK, capture_output=True, text=True, timeout=3600,
        )
        produced = Path(tmp) / "results" / "v15" / name
        if proc.returncode != 0 or not produced.is_file():
            tail = (proc.stdout + proc.stderr)[-1500:]
            raise HTTPException(500, f"MuseTalk failed: {tail}")
        final = out_dir / name
        shutil.move(str(produced), final)  # /tmp and /outputs are different filesystems: rename fails
    return {"path": str(final), "seconds": round(time.perf_counter() - started, 1)}
