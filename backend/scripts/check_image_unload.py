"""Does unloading the image model give its RAM back? (Needed before the video model loads: ~15 GiB.)

    python scripts/check_image_unload.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def anon() -> str:
    for line in open("/proc/self/status"):
        if line.startswith("RssAnon"):
            return f"{int(line.split()[1]) / 2**20:.2f} GiB"
    return "?"


def main() -> None:
    from app.core.config import get_settings
    from app.services.image_engine import DiffusersImageEngine, ImageParams

    engine = DiffusersImageEngine(get_settings())
    print("start", anon(), flush=True)
    engine.generate(ImageParams(prompt="a red apple", style="photorealistic", width=1344, height=768, steps=5, seed=1,
                                negative_prompt=None, guidance_scale=None), deadline=time.monotonic() + 600)
    print("after image", anon(), flush=True)
    engine.unload()
    print("after unload", anon(), flush=True)
    from app.services import memory

    memory.release()
    print("after release", anon(), flush=True)


if __name__ == "__main__":
    main()
