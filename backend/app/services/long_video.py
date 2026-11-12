"""Long videos (15-120 s) from real generated clips.

The video model makes at most 81 frames (~5 s at 16 fps) per clip, so a long video is planned as scenes,
each scene as one or more clips, and the clips of a scene are joined with short crossfades (scenes meet with a cut). Every output frame comes
from a generated clip: nothing is looped, repeated or replaced by a still image. The joined video is
trimmed to exactly ``duration × fps`` frames and validated by decoding it.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

MAX_CLIP_FRAMES = 81  # Wan2.1's trained length
MIN_CLIP_FRAMES = 17
CROSSFADE_FRAMES = 8  # 0.5 s at 16 fps, between clips of the same scene generated independently
# A new scene is a new shot, so scenes meet with a hard cut, as in edited film. A crossfade there would also
# push a 5 s scene (80 frames) past the 81-frame limit and double its generation time.
SCENE_CUT_FRAMES = 0
CONTINUATION_OVERLAP = 1  # a clip that starts from the previous last frame repeats exactly that one frame
MIN_SCENE_SECONDS = 2.0


@dataclass(frozen=True)
class ClipPlan:
    scene: int  # 0-based
    index: int  # 0-based within the scene
    frames: int
    overlap_in: int  # frames blended with the previous clip (0 for the very first clip)


def _wan_frames(n: int) -> int:
    """Smallest valid Wan frame count (4k+1) >= n, within the clip limits."""
    n = max(MIN_CLIP_FRAMES, n)
    n += (-(n - 1)) % 4
    return min(n, MAX_CLIP_FRAMES)


def scene_durations(total_seconds: float, requested: list[float | None]) -> list[float]:
    """Explicit durations are scaled to the total; missing ones share the remainder equally."""
    count = len(requested)
    if count == 0:
        raise ValueError("At least one scene is required.")
    if total_seconds / count < MIN_SCENE_SECONDS:
        raise ValueError(f"Too many scenes: each scene needs at least {MIN_SCENE_SECONDS:.0f} seconds.")
    given = [d for d in requested if d]
    if len(given) == count:
        scale = total_seconds / sum(given)
        durations = [d * scale for d in given]
    else:
        remainder = max(total_seconds - sum(given), MIN_SCENE_SECONDS * (count - len(given)))
        share = remainder / (count - len(given))
        durations = [d if d else share for d in requested]
        scale = total_seconds / sum(durations)
        durations = [d * scale for d in durations]
    if min(durations) < MIN_SCENE_SECONDS - 1e-6:
        raise ValueError(f"Each scene needs at least {MIN_SCENE_SECONDS:.0f} seconds.")
    return [round(d, 3) for d in durations]


def plan_clips(durations: list[float], fps: int, continuity: str) -> list[ClipPlan]:
    """Frame counts per clip so that, after overlaps, the joined video covers every scene's duration."""
    inner_overlap = CONTINUATION_OVERLAP if continuity == "last_frame" else CROSSFADE_FRAMES
    clips: list[ClipPlan] = []
    for s, seconds in enumerate(durations):
        scene_frames = round(seconds * fps)
        incoming = SCENE_CUT_FRAMES if s > 0 else 0
        # Smallest n with n clips of <=81 frames covering the scene plus its overlaps.
        n = 1
        while n * MAX_CLIP_FRAMES < scene_frames + incoming + (n - 1) * inner_overlap:
            n += 1
        needed = scene_frames + incoming + (n - 1) * inner_overlap
        base = math.ceil(needed / n)
        for i in range(n):
            clips.append(
                ClipPlan(scene=s, index=i, frames=_wan_frames(base), overlap_in=(incoming if i == 0 else inner_overlap))
            )
    return clips


def covered_frames(clips: list[ClipPlan]) -> int:
    return sum(c.frames for c in clips) - sum(c.overlap_in for c in clips)


def _read_frames(path: Path) -> Iterator[Any]:
    import imageio.v2 as imageio

    reader = imageio.get_reader(str(path), format="ffmpeg")
    try:
        yield from reader
    finally:
        reader.close()


def join_clips(clips: Iterable[tuple[Path, int]], output: Path, fps: int, total_frames: int) -> int:
    """Streams clips into one H.264 MP4 through FFmpeg, crossfading ``overlap`` frames at each joint,
    and stops at exactly ``total_frames``. Returns the number of frames written."""
    import numpy as np

    from app.services.video_engine import write_mp4

    def blend(a: Any, b: Any, alpha: float) -> Any:
        return ((1 - alpha) * a.astype(np.float32) + alpha * b.astype(np.float32)).round().astype(np.uint8)

    def ordered() -> Iterator[Any]:
        # The last CROSSFADE_FRAMES of each clip are held back until we know how the next clip joins.
        tail: list[Any] = []
        for path, overlap in clips:
            incoming = _read_frames(path)
            n = min(overlap, len(tail))
            yield from tail[: len(tail) - n]
            for k, held in enumerate(tail[len(tail) - n :]):
                yield blend(held, next(incoming), (k + 1) / (n + 1))
            buffer = list(incoming)
            keep = min(CROSSFADE_FRAMES, len(buffer))
            yield from buffer[: len(buffer) - keep]
            tail = buffer[len(buffer) - keep :]
        yield from tail

    def frames() -> Iterator[Any]:
        for written, frame in enumerate(ordered(), start=1):
            yield frame
            if written >= total_frames:
                return

    count = 0

    def counted() -> Iterator[Any]:
        nonlocal count
        for frame in frames():
            count += 1
            yield frame

    write_mp4(counted(), output, fps=fps)
    return count
