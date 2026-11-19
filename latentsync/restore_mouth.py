"""Sharpens the redrawn mouth of a lip-synced video with GFPGAN v1.4 (Apache-2.0).

LatentSync 1.5 redraws the lower face at 256 px, so an open mouth comes out as a soft dark gap with smooth "plastic"
lips. GFPGAN restores teeth and lip texture; only an ellipse around the mouth is blended back (feathered), so the
eyes, beard edge and identity stay as LatentSync left them.

    python /service/restore_mouth.py IN.mp4 OUT.mp4 [weight]
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

import cv2
import numpy as np

MODEL = "/latentsync/checkpoints/gfpgan/GFPGANv1.4.pth"


def restore(src: Path, dst: Path, weight: float = 0.5) -> None:
    from gfpgan import GFPGANer

    restorer = GFPGANer(model_path=MODEL, upscale=1, arch="clean", channel_multiplier=2, bg_upsampler=None)
    cap = cv2.VideoCapture(str(src))
    fps = cap.get(cv2.CAP_PROP_FPS) or 25
    with tempfile.TemporaryDirectory() as tmp:
        frames_dir = Path(tmp)
        n = 0
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            _, _, restored = restorer.enhance(frame, has_aligned=False, only_center_face=True, paste_back=True,
                                              weight=weight)
            out = frame
            marks = restorer.face_helper.all_landmarks_5
            if restored is not None and marks:
                lm = np.asarray(marks[0])  # eyes, nose, mouth corners
                eye_dist = np.linalg.norm(lm[0] - lm[1])
                cx, cy = (lm[3] + lm[4]) / 2
                mask = np.zeros(frame.shape[:2], np.float32)
                cv2.ellipse(mask, (int(cx), int(cy + 0.1 * eye_dist)), (int(0.95 * eye_dist), int(0.6 * eye_dist)),
                            0, 0, 360, 1.0, -1)
                k = int(eye_dist * 0.4) | 1
                mask = cv2.GaussianBlur(mask, (k, k), 0)[..., None]
                out = (restored * mask + frame * (1 - mask)).astype(np.uint8)
            cv2.imwrite(str(frames_dir / f"{n:06d}.png"), out)
            n += 1
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-framerate", str(fps), "-i", str(frames_dir / "%06d.png"), "-i", str(src),
             "-map", "0:v", "-map", "1:a?", "-c:v", "libx264", "-crf", "16", "-pix_fmt", "yuv420p", "-c:a", "aac",
             "-shortest", str(dst)],
            check=True,
        )


if __name__ == "__main__":
    restore(Path(sys.argv[1]), Path(sys.argv[2]), float(sys.argv[3]) if len(sys.argv) > 3 else 0.5)
