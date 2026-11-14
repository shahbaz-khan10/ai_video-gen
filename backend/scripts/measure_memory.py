"""RAM and VRAM of each model on this machine, and whether unloading really gives the memory back.

  python scripts/measure_memory.py
Steps: idle -> image model loaded -> image unloaded (gc only) -> malloc_trim -> video model loaded ->
video unloaded + trim. Prints process RSS, VM MemAvailable and free VRAM after each step.
"""

from __future__ import annotations

import ctypes
import gc
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main() -> None:
    import torch

    from app.core.config import get_settings
    from app.services.image_engine import DiffusersImageEngine
    from app.services.memory import snapshot
    from app.services.video_engine import WanVideoEngine

    rows = []

    def step(name: str) -> None:
        s = snapshot()
        rows.append({"step": name, "rss_gib": round(s.process_rss_gib or 0, 2),
                     "vm_available_gib": round(s.ram_available_gib or 0, 2),
                     "vram_free_gib": round(s.vram_free_gib or 0, 2)})
        print(rows[-1], flush=True)

    settings = get_settings()
    step("idle")
    image = DiffusersImageEngine(settings)
    t = time.perf_counter()
    image.load()
    print(f"image load {time.perf_counter() - t:.1f}s", flush=True)
    step("image loaded")
    image._pipe = None  # what unload() did before: drop references, gc, empty cache
    gc.collect()
    torch.cuda.empty_cache()
    step("image unloaded (gc + empty_cache)")
    ctypes.CDLL("libc.so.6").malloc_trim(0)
    step("after malloc_trim")
    video = WanVideoEngine(settings)
    t = time.perf_counter()
    video.load()
    print(f"video load {time.perf_counter() - t:.1f}s", flush=True)
    step("video loaded")
    video.unload()
    ctypes.CDLL("libc.so.6").malloc_trim(0)
    step("video unloaded + trim")
    print(json.dumps(rows, indent=1))


if __name__ == "__main__":
    main()
