"""REAL benchmark: Wan2.1 T2V 1.3B used as a text-to-image model (num_frames=1).

Wan's UMT5 text encoder understands long sentences far better than SDXL's CLIP, so this checks whether
single-frame Wan follows multi-person / spatial prompts better than RealVisXL. Uses already-downloaded weights.

    python scripts/benchmark_wan_image.py --out /app/outputs/benchmarks/<name> [--steps 30]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings  # noqa: E402
from scripts.benchmark_generation import TESTS, peak_rss_gb, plan_of  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--steps", type=int, default=30)
    ap.add_argument("--width", type=int, default=832)
    ap.add_argument("--height", type=int, default=480)
    ap.add_argument("--tests", default="T1_classroom")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    import torch
    from PIL import Image

    from app.services.video_engine import WAN_NEGATIVE_PROMPT, WanVideoEngine

    engine = WanVideoEngine(get_settings())
    t0 = time.monotonic()
    engine.load()
    load_s = time.monotonic() - t0
    pipe = engine._pipe
    for name in args.tests.split(","):
        prompt = TESTS[name]["prompt"]
        torch.cuda.reset_peak_memory_stats()
        with torch.inference_mode():
            t1 = time.monotonic()
            pos, neg = pipe.encode_prompt(
                prompt=prompt, negative_prompt=WAN_NEGATIVE_PROMPT, do_classifier_free_guidance=True,
                num_videos_per_prompt=1, device=pipe.text_encoder.device, dtype=pipe.transformer.dtype,
            )
            t2 = time.monotonic()
            frames = pipe(
                prompt_embeds=pos.to("cuda"), negative_prompt_embeds=neg.to("cuda"), width=args.width,
                height=args.height, num_frames=1, num_inference_steps=args.steps, guidance_scale=5.0,
                generator=torch.Generator("cpu").manual_seed(1234), output_type="np",
            ).frames[0]
            t3 = time.monotonic()
        path = out / f"{name}_wan_t2i.png"
        Image.fromarray((frames[0] * 255).round().clip(0, 255).astype("uint8")).save(path)
        record = {
            "test": name,
            "original_prompt": prompt,
            "scene_plan": plan_of(prompt),
            "result": {
                "model": engine.model_id + " (num_frames=1, text-to-image)",
                "model_prompt": prompt,
                "output": path.name,
                "resolution": f"{args.width}x{args.height}",
                "steps": args.steps,
                "load_seconds": round(load_s, 1),
                "text_encode_seconds_cpu": round(t2 - t1, 1),
                "generate_seconds": round(t3 - t2, 1),
                "peak_vram_gb": round(torch.cuda.max_memory_allocated() / 2**30, 2),
            },
            "peak_process_ram_gb": peak_rss_gb(),
        }
        (out / f"{name}_wan_t2i.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
        print(json.dumps({"test": name, **record["result"]}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
