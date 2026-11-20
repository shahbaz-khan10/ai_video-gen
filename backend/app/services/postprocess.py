"""CPU post-processing with ffmpeg: "Look" presets, an optional enhance pass and Ken Burns clips.

None of this uses the GPU or an AI model, so it is safe to run while the GPU is busy and costs seconds, not minutes.
The ffmpeg binary is the static build shipped with imageio-ffmpeg (the backend image has no system ffmpeg).
"""

from __future__ import annotations

import logging
import os
import subprocess
import time
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)

VideoLook = Literal["none", "film", "documentary_bw", "sepia", "warm_commercial"]
KenBurnsMove = Literal["none", "static", "zoom_in", "zoom_out", "pan_left", "pan_right", "tilt_up", "orbit"]

# Filter chains. Grain is temporal noise (changes every frame like film), not a fixed pattern.
LOOK_FILTERS: dict[str, str] = {
    # Neutral film: light grain and a soft vignette, colours untouched.
    "film": "noise=alls=8:allf=t+u,vignette=angle=PI/6",
    # Black-and-white documentary: no colour, a little more contrast, grain and vignette.
    "documentary_bw": "hue=s=0,eq=contrast=1.15:brightness=0.01,noise=alls=10:allf=t+u,vignette=angle=PI/5",
    # Sepia / historical: sepia matrix, softer contrast, heavier grain and vignette.
    "sepia": (
        "colorchannelmixer=.393:.769:.189:0:.349:.686:.168:0:.272:.534:.131,"
        "eq=contrast=0.95:brightness=0.02,noise=alls=12:allf=t+u,vignette=angle=PI/4.5"
    ),
    # Warm commercial: warmer highlights, a touch more saturation and contrast, clean (no grain).
    "warm_commercial": "colorbalance=rs=.06:gs=.02:bs=-.06:rh=.04:bh=-.04,eq=saturation=1.12:contrast=1.05",
}
LOOK_LABELS: dict[str, str] = {
    "none": "None",
    "film": "Film grain",
    "documentary_bw": "Documentary B&W",
    "sepia": "Sepia / historical",
    "warm_commercial": "Warm commercial",
}

# Light denoise, 2x Lanczos upscale, gentle sharpen. Classic filters only: no AI upscaler fits beside the video
# models on 8 GB without its own GPU slot, and this one runs on the CPU (time measured in docs/PHASE2_LOOKS.md).
ENHANCE_FILTER = "hqdn3d=1.5:1.5:3:3,scale=iw*2:ih*2:flags=lanczos,unsharp=5:5:0.5:5:5:0.0"


class PostprocessError(RuntimeError):
    pass


def ffmpeg_exe() -> str:
    import imageio_ffmpeg

    return imageio_ffmpeg.get_ffmpeg_exe()


def _run(args: list[str], timeout: int = 600) -> None:
    try:
        subprocess.run([ffmpeg_exe(), "-nostdin", "-y", "-v", "error", *args], check=True, capture_output=True,
                       timeout=timeout)
    except subprocess.CalledProcessError as exc:
        raise PostprocessError(exc.stderr.decode(errors="replace")[-600:]) from None
    except subprocess.TimeoutExpired:
        raise PostprocessError("ffmpeg took too long") from None


def _rewrite(path: Path, video_filter: str) -> float:
    """Re-encodes ``path`` in place through ``video_filter``; keeps any audio. Returns the seconds it took."""
    started = time.monotonic()
    out = path.with_name(path.name + ".pp.mp4")
    try:
        _run(["-i", str(path), "-vf", video_filter, "-c:v", "libx264", "-crf", "17", "-preset", "medium",
              "-pix_fmt", "yuv420p", "-c:a", "copy", "-movflags", "+faststart", str(out)])
        os.replace(out, path)
    finally:
        out.unlink(missing_ok=True)
    return time.monotonic() - started


def apply_look(path: Path, look: str | None) -> float:
    """Applies a Look preset in place. "none"/None is a no-op. Returns seconds spent (0 when nothing was done)."""
    if not look or look == "none":
        return 0.0
    if look not in LOOK_FILTERS:
        raise PostprocessError(f"Unknown look: {look}")
    seconds = _rewrite(path, LOOK_FILTERS[look])
    logger.info("look %s applied to %s in %.1fs", look, path.name, seconds)
    return seconds


def enhance(path: Path) -> float:
    """Denoise + 2x upscale + sharpen, in place. Returns seconds spent."""
    seconds = _rewrite(path, ENHANCE_FILTER)
    logger.info("enhance applied to %s in %.1fs", path.name, seconds)
    return seconds


def ken_burns_filter(width: int, height: int, frames: int, fps: int, move: str) -> str:
    """zoompan expression for a slow camera move over a still. The still is first scaled to 4x the output so the
    sub-pixel steps of the move do not jitter (zoompan rounds its crop to whole pixels)."""
    zoom_to = 1.25
    step = (zoom_to - 1.0) / max(frames - 1, 1)
    centre_x, centre_y = "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
    # The crop window is iw/zoom wide; pans move it across the spare width at a fixed 1.15 zoom.
    pan_zoom = 1.15
    progress = f"(on/{max(frames - 1, 1)})"
    if move == "zoom_out":
        z, x, y = f"{zoom_to}-{step}*on", centre_x, centre_y
    elif move == "pan_left":
        z, x, y = str(pan_zoom), f"(iw-iw/zoom)*(1-{progress})", centre_y
    elif move == "pan_right":
        z, x, y = str(pan_zoom), f"(iw-iw/zoom)*{progress}", centre_y
    elif move == "tilt_up":
        z, x, y = str(pan_zoom), centre_x, f"(ih-ih/zoom)*(1-{progress})"
    else:  # zoom_in, none, static, orbit: a gentle push in is the classic Ken Burns default
        z, x, y = f"1+{step}*on", centre_x, centre_y
    return (
        f"scale={width * 4}:{height * 4}:force_original_aspect_ratio=increase,crop={width * 4}:{height * 4},"
        f"zoompan=z='{z}':x='{x}':y='{y}':d={frames}:s={width}x{height}:fps={fps},format=yuv420p"
    )


def ken_burns(image: Path, output: Path, width: int, height: int, frames: int, fps: int, move: str) -> float:
    """Writes a ``frames``-long MP4 of a slow move over ``image``. Returns seconds spent."""
    started = time.monotonic()
    _run(["-loop", "1", "-i", str(image), "-vf", ken_burns_filter(width, height, frames, fps, move),
          "-frames:v", str(frames), "-c:v", "libx264", "-crf", "17", "-preset", "medium", "-movflags", "+faststart",
          str(output)])
    return time.monotonic() - started
