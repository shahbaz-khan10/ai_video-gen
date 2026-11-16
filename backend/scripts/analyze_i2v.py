"""Measures image-to-video outputs against their source images and writes a 4-frame strip per video.

  frame0_psnr      first frame vs the uploaded image (cropped and resized the same way): is the photo kept?
  last_psnr        last frame vs the uploaded image: how far the picture moved or drifted (lower = more change)
  motion           mean |frame difference| (0-255)
  flicker_ratio    largest frame difference / median frame difference; ~1-3 is smooth, large values mean a jump

    python scripts/analyze_i2v.py --inputs /k/inputs --videos /k/app
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main() -> None:
    import imageio.v2 as iio
    import numpy as np
    from PIL import Image

    from app.services.video_engine import fit_image

    ap = argparse.ArgumentParser()
    ap.add_argument("--inputs", required=True)
    ap.add_argument("--videos", required=True)
    args = ap.parse_args()
    rows = []
    for video in sorted(Path(args.videos).glob("k*_*.mp4")):
        name = "_".join(video.stem.split("_")[:2])
        frames = [np.asarray(f) for f in iio.get_reader(str(video), "ffmpeg")]
        h, w = frames[0].shape[:2]
        with Image.open(next(Path(args.inputs).glob(f"{name}.*"))) as src:
            ref = np.asarray(fit_image(src, w, h)).astype(np.float32)

        def psnr(a) -> float:
            mse = float(np.mean((a.astype(np.float32) - ref) ** 2))
            return round(10 * np.log10(255.0**2 / max(mse, 1e-6)), 2)

        diffs = np.array([np.abs(frames[i + 1].astype(np.float32) - frames[i]).mean() for i in range(len(frames) - 1)])
        row = {
            "video": video.name, "size": f"{w}x{h}", "frames": len(frames),
            "frame0_psnr": psnr(frames[0]), "last_psnr": psnr(frames[-1]),
            "motion": round(float(diffs.mean()), 2),
            "flicker_ratio": round(float(diffs.max() / max(np.median(diffs), 1e-3)), 2),
        }
        rows.append(row)
        picks = [frames[round(i * (len(frames) - 1) / 3)] for i in range(4)]
        Image.fromarray(np.concatenate(picks, axis=1)).save(video.with_name(video.stem + "_strip.jpg"), quality=88)
        print(json.dumps(row), flush=True)
    (Path(args.videos) / "analysis.json").write_text(json.dumps(rows, indent=1))


if __name__ == "__main__":
    main()
