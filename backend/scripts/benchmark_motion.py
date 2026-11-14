"""Why do people look half-body and static? Compare video prompt styles on the same seeds.

V0  what the app sends today (image style words: "cinematic film still, anamorphic lens …")
V1  video style words (no "still"/"photograph"/"portrait lens"; asks for natural motion)
V2  V1 + full-body wide framing when the action moves the body (walk, run, step …)

Motion energy = mean absolute difference between consecutive frames (0-255), averaged over the clip.

  python scripts/benchmark_motion.py --out /out
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

PROMPTS = {
    "walk": "A young woman with long black hair wearing a red coat walks along a busy city street.",
    "reporter_back": (
        "A terrified 30-year-old male reporter with short dark brown hair, wearing a dark grey jacket over a light "
        "blue shirt, steps backward as a huge dark cloud approaches over a burning city."
    ),
    "run": "A man in a blue tracksuit runs across a wet football field in the rain.",
}
VIDEO_STYLE = "cinematic video, smooth natural motion, realistic movement, dramatic lighting, film grain"
FRAMING = "Camera: wide shot, full body visible from head to feet"


def motion_energy(frames) -> float:
    import numpy as np

    arr = [np.asarray(f, dtype=np.float32) for f in frames]
    if np.max(arr[0]) <= 1.0:
        arr = [a * 255 for a in arr]
    return float(np.mean([np.abs(arr[i + 1] - arr[i]).mean() for i in range(len(arr) - 1)]))


def main() -> None:
    import imageio.v2 as iio

    from app.core.config import get_settings
    from app.services.image_engine import STYLE_PROMPTS
    from app.services.prompt_compiler import compile_plan
    from app.services.video_engine import VideoParams, WanVideoEngine

    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--frames", type=int, default=49)
    ap.add_argument("--only", default=None, help="comma-separated variants, e.g. V3")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    def words(t: str) -> int:
        return len(t.split())

    engine = WanVideoEngine(get_settings())
    engine.load()
    rows = []
    for name, prompt in PROMPTS.items():
        v0 = compile_plan(prompt, mode="text-to-video", style_text=STYLE_PROMPTS["cinematic"], style_name="cinematic",
                          duration_seconds=5, measure=words, budget=400, tokenizer_name="words", measured=False).compiled[0].text
        v1 = v0.replace(STYLE_PROMPTS["cinematic"], VIDEO_STYLE)
        v2 = v1.replace(" Style:", f" {FRAMING}. Style:", 1)
        # V3: framing first (early words weigh more) and the movement spelled out.
        v3 = "Wide full-body shot, the whole figure from head to feet in frame, natural movement. " + v1
        variants = (("V0", v0), ("V1", v1), ("V2", v2), ("V3", v3))
        if args.only:
            variants = tuple(v for v in variants if v[0] in args.only.split(","))
        for variant, text in variants:
            path = out / f"{name}_{variant}.mp4"
            t = time.perf_counter()
            engine.generate(VideoParams(prompt=text, width=576, height=320, num_frames=args.frames, num_inference_steps=3,
                                        seed=4242, fps=16), deadline=time.monotonic() + 3600, output_path=path)
            # iterate: list(reader) asks for an "infinite" length and raises MemoryError
            frames = [f for f in iio.get_reader(str(path), "ffmpeg")]
            row = {"prompt": name, "variant": variant, "seconds": round(time.perf_counter() - t, 1),
                   "motion_energy": round(motion_energy(frames), 2), "text": text}
            rows.append(row)
            print(json.dumps({k: v for k, v in row.items() if k != "text"}), flush=True)
    report = out / "motion_report.json"
    old = json.loads(report.read_text()) if report.exists() and args.only else []
    report.write_text(json.dumps(old + rows, indent=1))


if __name__ == "__main__":
    main()
