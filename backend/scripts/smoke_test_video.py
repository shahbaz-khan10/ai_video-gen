"""REAL text-to-video smoke test: loads Wan2.1 and generates one short MP4. Nothing is mocked.

    python scripts/smoke_test_video.py [--size standard|large] [--seconds 2] [--steps 25]

Needs the video libraries (requirements-video.txt) and downloaded weights. The MP4 is written to
VIDEO_OUTPUT_DIR, then decoded frame by frame to prove it is a valid video.
"""

from __future__ import annotations

import argparse
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings  # noqa: E402
from app.schemas.generation import VIDEO_SIZES, AspectRatio, ImageResolution, video_frames_for  # noqa: E402
from app.services.video_engine import VideoEngineError, VideoParams, WanVideoEngine  # noqa: E402
from app.services.video_storage import VideoStorage  # noqa: E402

PROMPT = "A cat walks slowly across a sunny garden path, flowers swaying in a light breeze, realistic, smooth motion"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--size", choices=["standard", "large"], default="standard")
    parser.add_argument("--seconds", type=int, choices=[2, 3, 5], default=2)
    parser.add_argument("--steps", type=int, default=None)
    parser.add_argument("--prompt", default=PROMPT)
    args = parser.parse_args()

    settings = get_settings()
    engine = WanVideoEngine(settings)
    status = engine.status()
    print(f"Video engine: {status.state} | {status.detail}")
    try:
        engine.ensure_can_accept()
    except VideoEngineError as err:
        print(f"Cannot run: {err.message}")
        return 1

    import torch

    width, height = VIDEO_SIZES[ImageResolution(args.size)][AspectRatio.LANDSCAPE]
    frames = video_frames_for(args.seconds, settings.video_fps)
    steps = args.steps or settings.video_default_steps
    print(f"Model: {engine.model_id} | {width}x{height} | {frames} frames @ {settings.video_fps} fps | {steps} steps")

    storage = VideoStorage(settings.video_output_dir)
    job_id = str(uuid.uuid4())
    tmp = storage.temp_path(job_id)
    if torch.cuda.is_available():
        torch.cuda.reset_peak_memory_stats()
    started = time.monotonic()
    try:
        engine.load()
        loaded = time.monotonic()
        device = engine.generate(
            VideoParams(args.prompt, width, height, frames, steps, seed=42, fps=settings.video_fps),
            deadline=time.monotonic() + settings.video_timeout_seconds,
            output_path=tmp,
        )
        stored = storage.finalize(job_id, tmp)
    except VideoEngineError as err:
        storage.discard(job_id)
        print(f"FAILED [{err.code}]: {err.message}")
        return 1
    done = time.monotonic()

    print(f"Load: {loaded - started:.0f}s | generate + encode: {done - loaded:.0f}s | device: {device}")
    if torch.cuda.is_available():
        print(f"Peak VRAM allocated: {torch.cuda.max_memory_allocated() / 2**30:.2f} GiB")
    print(
        f"Decoded {stored.num_frames} frames, {stored.width}x{stored.height}, {stored.duration_seconds}s, "
        f"{stored.size_bytes / 1e6:.2f} MB -> {settings.video_output_dir / stored.filename}"
    )
    print("REAL VIDEO INFERENCE OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
