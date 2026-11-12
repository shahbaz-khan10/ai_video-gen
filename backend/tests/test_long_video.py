"""Long-video planning and assembly (no model: tiny real MP4s made with solid colours)."""

from __future__ import annotations

import numpy as np
import pytest

from app.services.long_video import (
    CROSSFADE_FRAMES,
    MAX_CLIP_FRAMES,
    covered_frames,
    join_clips,
    plan_clips,
    scene_durations,
)
from app.services.video_engine import write_mp4
from app.services.video_storage import probe_mp4


@pytest.mark.parametrize("total", [15, 30, 60, 90, 120])
@pytest.mark.parametrize("continuity", ["prompt", "last_frame"])
def test_clip_plan_covers_the_full_duration_within_model_limits(total: int, continuity: str) -> None:
    durations = scene_durations(total, [None, None, None, None])
    clips = plan_clips(durations, fps=16, continuity=continuity)
    assert all(17 <= c.frames <= MAX_CLIP_FRAMES and (c.frames - 1) % 4 == 0 for c in clips)
    assert covered_frames(clips) >= total * 16  # enough real frames; the join trims the excess
    assert covered_frames(clips) - total * 16 < 4 * len(clips) + 16


def test_two_minutes_needs_many_real_clips() -> None:
    clips = plan_clips(scene_durations(120, [None] * 4), fps=16, continuity="prompt")
    assert len(clips) >= 24  # 120 s cannot come from one 5 s clip


def test_five_second_scenes_are_one_clip_each() -> None:
    clips = plan_clips(scene_durations(15, [None] * 3), fps=16, continuity="prompt")
    assert [c.frames for c in clips] == [81, 81, 81]
    assert [c.overlap_in for c in clips] == [0, 0, 0]  # scenes meet with a cut


def test_clips_within_a_scene_crossfade() -> None:
    clips = plan_clips([30.0], fps=16, continuity="prompt")
    assert clips[0].overlap_in == 0 and all(c.overlap_in == CROSSFADE_FRAMES for c in clips[1:])


def test_scene_durations_scale_explicit_values_to_the_total() -> None:
    assert scene_durations(60, [10, 20, 30]) == [10, 20, 30]
    assert scene_durations(60, [10, 10, 10]) == [20, 20, 20]
    assert sum(scene_durations(120, [30, None, None])) == pytest.approx(120)


def test_too_many_scenes_for_the_duration_is_refused() -> None:
    with pytest.raises(ValueError):
        scene_durations(15, [None] * 10)


def _clip(path, value: int, frames: int) -> None:
    write_mp4([np.full((64, 96, 3), value, dtype=np.uint8)] * frames, path, fps=16)


def test_join_crossfades_and_trims_to_exact_length(tmp_path) -> None:
    a, b = tmp_path / "a.mp4", tmp_path / "b.mp4"
    _clip(a, 20, 33)
    _clip(b, 220, 33)
    out = tmp_path / "joined.mp4"
    written = join_clips([(a, 0), (b, CROSSFADE_FRAMES)], out, fps=16, total_frames=50)
    assert written == 50
    width, height, frames, fps = probe_mp4(out)
    assert (width, height, frames, fps) == (96, 64, 50, 16.0)


def test_join_keeps_frame_order_and_blends_only_the_overlap(tmp_path) -> None:
    import imageio.v2 as imageio

    a, b = tmp_path / "a.mp4", tmp_path / "b.mp4"
    _clip(a, 20, 33)
    _clip(b, 220, 33)
    out = tmp_path / "joined.mp4"
    join_clips([(a, 0), (b, CROSSFADE_FRAMES)], out, fps=16, total_frames=33 + 33 - CROSSFADE_FRAMES)
    levels = [float(f.mean()) for f in imageio.get_reader(str(out), format="ffmpeg")]
    first, last = levels[: 33 - CROSSFADE_FRAMES], levels[33:]
    ramp = levels[33 - CROSSFADE_FRAMES : 33]
    assert max(abs(v - 20) for v in first) < 6 and max(abs(v - 220) for v in last) < 6
    assert all(x < y for x, y in zip(ramp, ramp[1:]))  # a real fade, monotonic from A to B


def test_continuation_overlap_of_one_frame_keeps_order(tmp_path) -> None:
    import imageio.v2 as imageio

    a, b = tmp_path / "a.mp4", tmp_path / "b.mp4"
    _clip(a, 20, 17)
    _clip(b, 220, 17)
    out = tmp_path / "joined.mp4"
    join_clips([(a, 0), (b, 1)], out, fps=16, total_frames=33)
    levels = [float(f.mean()) for f in imageio.get_reader(str(out), format="ffmpeg")]
    assert len(levels) == 33
    assert max(abs(v - 20) for v in levels[:16]) < 6 and max(abs(v - 220) for v in levels[17:]) < 6
