"""Lip-sync service: LatentSync 1.5 (ByteDance, Apache-2.0) redraws the mouth in a video or photo to match a WAV.

Same HTTP API as the MuseTalk service in ../lipsync, so the backend switches with AVS_LIPSYNC_URL. Each request runs
LatentSync's own inference script in a child process, so all GPU memory is returned when it exits and the video
models can load again. Files are exchanged through the shared /outputs volume. If the audio is longer than the video,
LatentSync plays the frames forward and backward to cover it.
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
from pydantic import BaseModel, Field

OUTPUTS = Path("/outputs")
LATENTSYNC = Path("/latentsync")
CKPT = LATENTSYNC / "checkpoints"
app = FastAPI(title="AI Video Studio lip-sync (LatentSync 1.5)")
_lock = threading.Lock()


class LipSyncRequest(BaseModel):
    video_path: str  # under /outputs: an MP4 or a still image (png/jpg)
    audio_path: str  # under /outputs: a WAV
    fps: int = 25
    steps: int = 20  # README: 20-50, more = sharper and slower
    # README: 1.0-3.0, higher = stronger sync but may jitter. Measured on a Hindi 5.8 s clip (sync_check.py, same
    # video and voice): 1.5 -> mouth lags by 4 frames, 2.5 -> lag 0 and the mouth opens 2.4x wider when speaking than
    # when silent (MuseTalk 1.5: 1.4x), no visible distortion.
    guidance_scale: float = 2.5
    # Reuses U-Net features between steps. Measured: 40 steps without it looked the same as 20 with it, at 2x the time.
    deepcache: bool = True
    # GFPGAN on the mouth only (restore_mouth.py): defined lip edges and visible teeth instead of a flat dark gap.
    # 0 = off; 0.5 looked most natural (0.8 smooths the skin too much). ~1 min for a 6 s clip.
    restore_mouth: float = Field(0.5, ge=0.0, le=1.0)


def _inside_outputs(path: str) -> Path:
    p = Path(path).resolve()
    if OUTPUTS.resolve() not in p.parents or not p.is_file():
        raise HTTPException(404, f"Not found under /outputs: {path}")
    return p


def _run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True, capture_output=True)


def _audio_seconds(path: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         check=True, capture_output=True, text=True)
    return float(out.stdout.strip() or 0)


def _video_frames(path: Path) -> int:
    out = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v", "-show_entries",
                          "stream=nb_read_frames", "-of", "csv=p=0", str(path)], check=True, capture_output=True, text=True)
    return int(out.stdout.strip() or 0)


def _prepare_video(path: Path, audio: Path, tmp: Path) -> Path:
    """LatentSync reads a 25 fps video. A photo becomes a still clip as long as the speech; H.264 needs even sizes."""
    out = tmp / "source25.mp4"
    even = "scale=trunc(iw/2)*2:trunc(ih/2)*2"
    if path.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"):
        seconds = _audio_seconds(audio) + 0.2
        _run(["ffmpeg", "-y", "-v", "error", "-loop", "1", "-i", str(path), "-t", f"{seconds:.2f}", "-r", "25",
              "-vf", f"scale='min(1280,iw)':-2,{even}", "-c:v", "libx264", "-crf", "16", "-pix_fmt", "yuv420p", str(out)])
    else:
        _run(["ffmpeg", "-y", "-v", "error", "-i", str(path), "-an", "-vf", f"fps=25,{even}", "-c:v", "libx264",
              "-crf", "16", "-pix_fmt", "yuv420p", str(out)])
    return out


@app.get("/health")
def health() -> dict:
    ok = (CKPT / "latentsync_unet.pt").is_file() and (CKPT / "whisper/tiny.pt").is_file()
    return {"status": "ok" if ok else "models_missing", "busy": _lock.locked(), "engine": "latentsync-1.5"}


@app.post("/lipsync")
def lipsync(req: LipSyncRequest) -> dict:
    video = _inside_outputs(req.video_path)
    audio = _inside_outputs(req.audio_path)
    out_dir = OUTPUTS / "talking"
    out_dir.mkdir(parents=True, exist_ok=True)
    name = f"{uuid.uuid4()}.mp4"
    with _lock, tempfile.TemporaryDirectory() as tmp:
        src = _prepare_video(video, audio, Path(tmp))
        produced = Path(tmp) / name
        started = time.perf_counter()
        proc = subprocess.run(
            ["python", "-m", "scripts.inference",
             "--unet_config_path", "configs/unet/stage2.yaml",  # 256 px model = LatentSync 1.5
             "--inference_ckpt_path", str(CKPT / "latentsync_unet.pt"),
             "--inference_steps", str(req.steps), "--guidance_scale", str(req.guidance_scale),
             *(["--enable_deepcache"] if req.deepcache else []),
             "--video_path", str(src), "--audio_path", str(audio), "--video_out_path", str(produced),
             "--temp_dir", str(Path(tmp) / "work")],
            cwd=LATENTSYNC, capture_output=True, text=True, timeout=3600,
        )
        if proc.returncode != 0 or not produced.is_file():
            tail = (proc.stdout + proc.stderr)[-1500:]
            if "Face not detected" in tail:
                raise HTTPException(422, "No clear face was found in some frames. Use a clip where the face is "
                                         "large, frontal and visible in every frame.")
            raise HTTPException(500, f"LatentSync failed: {tail}")
        if req.restore_mouth > 0 and (CKPT / "gfpgan/GFPGANv1.4.pth").is_file():
            restored = Path(tmp) / f"restored_{name}"
            fix = subprocess.run(  # child process: GPU memory is returned when it exits
                ["python", "/service/restore_mouth.py", str(produced), str(restored), str(req.restore_mouth)],
                cwd=tmp, capture_output=True, text=True, timeout=1800,
            )
            if fix.returncode == 0 and restored.is_file():
                produced = restored  # on failure keep the plain LatentSync result rather than failing the job
        expected = int(_audio_seconds(audio) * 25)
        frames = _video_frames(produced)
        if frames < expected * 0.9:
            raise HTTPException(500, f"Lip-sync produced {frames} frames for {expected} expected.")
        final = out_dir / name
        shutil.move(str(produced), final)  # /tmp and /outputs are different filesystems: rename fails
    return {"path": str(final), "seconds": round(time.perf_counter() - started, 1)}
