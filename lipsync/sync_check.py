"""Measures how well the mouth follows the voice in a talking video (run inside the lipsync container).

    python /service/sync_check.py VIDEO.mp4 [AUDIO.wav]

Mouth opening per frame = inner-lip gap (DWPose face points 62/66) / face height, at 25 fps. Voice loudness = RMS of
the audio in the same 40 ms windows. Prints the Pearson correlation of the two (best within +-15 frames of lag, and
the lag): about 0 means the mouth moves independently of the voice, 0.5+ is clearly synced. AUDIO defaults to the
video's own sound track; pass the speech WAV to score a silent source clip against it.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

import cv2
import librosa
import numpy as np

sys.path.insert(0, "/musetalk")
import os  # noqa: E402

os.chdir("/musetalk")
from mmpose.apis import inference_topdown, init_model  # noqa: E402
from mmpose.structures import merge_data_samples  # noqa: E402

FPS = 25


def mouth_series(video: Path, tmp: Path) -> np.ndarray:
    src = tmp / "v25.mp4"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(video), "-vf", f"fps={FPS}", "-an", str(src)], check=True)
    model = init_model("./musetalk/utils/dwpose/rtmpose-l_8xb32-270e_coco-ubody-wholebody-384x288.py",
                       "./models/dwpose/dw-ll_ucoco_384.pth", device="cuda")
    cap = cv2.VideoCapture(str(src))
    values = []
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        face = merge_data_samples(inference_topdown(model, frame)).pred_instances.keypoints[0][23:91]
        height = np.linalg.norm(face[8] - face[27]) or 1.0  # chin to nose bridge
        values.append(np.linalg.norm(face[66] - face[62]) / height)
    return np.asarray(values)


def loudness_series(audio: Path, frames: int) -> np.ndarray:
    y, sr = librosa.load(str(audio), sr=16000)
    hop = sr // FPS
    rms = np.array([np.sqrt(np.mean(y[i * hop:(i + 1) * hop] ** 2)) if i * hop < len(y) else 0.0 for i in range(frames)])
    return rms


def best_corr(a: np.ndarray, b: np.ndarray, max_lag: int = 15) -> tuple[float, int]:
    best = (-2.0, 0)
    for lag in range(-max_lag, max_lag + 1):
        x, y = (a[lag:], b[: len(b) - lag]) if lag >= 0 else (a[:lag], b[-lag:])
        n = min(len(x), len(y))
        if n > 10 and np.std(x[:n]) > 0 and np.std(y[:n]) > 0:
            best = max(best, (float(np.corrcoef(x[:n], y[:n])[0, 1]), lag))
    return best


def main() -> None:
    video = Path(sys.argv[1])
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        if len(sys.argv) > 2:
            audio = Path(sys.argv[2])
        else:
            audio = tmp / "a.wav"
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(video), "-vn", "-ac", "1", str(audio)], check=True)
        mouth = mouth_series(video, tmp)
        loud = loudness_series(audio, len(mouth))
    speech = loud > 0.25 * loud.max()
    corr, lag = best_corr(mouth, loud)
    print(f"frames={len(mouth)}  sync_corr={corr:.2f} (lag {lag} frames)  "
          f"mouth_open speaking={mouth[speech].mean():.3f} silent={mouth[~speech].mean() if (~speech).any() else float('nan'):.3f}  "
          f"mouth_range={mouth.min():.3f}-{mouth.max():.3f}")


if __name__ == "__main__":
    main()
