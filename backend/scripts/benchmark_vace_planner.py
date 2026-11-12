"""REAL benchmarks for two candidates (nothing mocked):

1. Qwen3-1.7B scene planner on the CPU: time, RAM, and the merged plan for the four test prompts.
2. Wan2.1 VACE 1.3B continuation: starts a new clip from the LAST frame of an existing clip
   (the mechanism needed for scene-to-scene continuity in long videos).

    python scripts/benchmark_vace_planner.py --out /app/outputs/benchmarks/<name> --source <clip.mp4>
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings  # noqa: E402
from scripts.benchmark_generation import TESTS, peak_rss_gb  # noqa: E402

VACE_ID = "Wan-AI/Wan2.1-VACE-1.3B-diffusers"


def bench_planner(out: Path) -> None:
    from app.services.llm_planner import LLMPlanner, merge
    from app.services.scene_planner import RulePlanner, build_video_prompt, validate

    settings = get_settings()
    planner = LLMPlanner(cache_dir=str(settings.image_model_cache_dir))
    t0 = time.monotonic()
    planner._load()
    load_s = time.monotonic() - t0
    for name, test in TESTS.items():
        mode = "text-to-image" if test["kind"] == "image" else "text-to-video"
        duration = 120 if test["kind"] == "story" else None
        rules = RulePlanner.plan(test["prompt"])
        t1 = time.monotonic()
        try:
            data = planner.raw_plan(test["prompt"], mode, duration, rules)
            plan = merge(rules, data, planner.name)
            error = None
        except Exception as exc:  # recorded honestly
            plan, error = rules, f"{type(exc).__name__}: {exc}"
        llm_s = time.monotonic() - t1
        plan = validate(plan, mode=mode, model_prompt=build_video_prompt(plan, "cinematic"))
        record = {
            "test": name,
            "planner": plan.planner,
            "llm_load_seconds": round(load_s, 1),
            "llm_seconds": round(llm_s, 1),
            "error": error,
            "peak_process_ram_gb": peak_rss_gb(),
            "plan": plan.model_dump(exclude_none=True),
        }
        (out / f"{name}_plan.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
        summary = {
            "test": name, "planner": plan.planner, "llm_seconds": record["llm_seconds"], "error": error,
            "people": plan.people_count, "characters": [(c.id, c.count) for c in plan.characters],
            "scenes": [s.description for s in plan.scenes],
            "unplanned": [i.text for i in plan.instructions if i.status != "planned"],
        }
        print(json.dumps(summary), flush=True)
    planner.unload()


def bench_vace(out: Path, source: Path, frames: int, steps: int) -> None:
    import imageio.v2 as iio
    import torch
    from diffusers import AutoencoderKLWan, UniPCMultistepScheduler, WanPipeline, WanVACEPipeline, WanVACETransformer3DModel
    from PIL import Image

    from app.services.video_engine import WAN_NEGATIVE_PROMPT, write_mp4
    from app.services.video_storage import probe_mp4

    settings = get_settings()
    hub = {"cache_dir": str(settings.image_model_cache_dir), "local_files_only": True}
    reader = iio.get_reader(str(source), format="ffmpeg")
    last = [f for f in reader][-1]
    reader.close()
    height, width = last.shape[:2]

    t0 = time.monotonic()
    base = WanPipeline.from_pretrained(settings.video_model_id, transformer=None, vae=None, **hub)
    vae = AutoencoderKLWan.from_pretrained(settings.video_model_id, subfolder="vae", dtype=torch.float32, **hub)
    transformer = WanVACETransformer3DModel.from_pretrained(VACE_ID, subfolder="transformer", dtype=torch.bfloat16, **hub)
    pipe = WanVACEPipeline(
        tokenizer=base.tokenizer, text_encoder=base.text_encoder.to(torch.bfloat16), vae=vae,
        scheduler=UniPCMultistepScheduler.from_config(base.scheduler.config, flow_shift=3.0), transformer=transformer,
    )
    pipe.transformer.to("cuda")
    pipe.vae.to("cuda")
    pipe.vae.enable_tiling()
    load_s = time.monotonic() - t0

    prompt = TESTS["T3_beach"]["prompt"]
    first = Image.fromarray(last)
    video = [first] + [Image.new("RGB", (width, height), (128, 128, 128))] * (frames - 1)
    mask = [Image.new("L", (width, height), 0)] + [Image.new("L", (width, height), 255)] * (frames - 1)
    torch.cuda.reset_peak_memory_stats()
    with torch.inference_mode():
        t1 = time.monotonic()
        pos, neg = pipe.encode_prompt(
            prompt=prompt, negative_prompt=WAN_NEGATIVE_PROMPT, do_classifier_free_guidance=True,
            num_videos_per_prompt=1, device=pipe.text_encoder.device, dtype=torch.bfloat16,
        )
        t2 = time.monotonic()
        result = pipe(
            video=video, mask=mask, prompt_embeds=pos.to("cuda"), negative_prompt_embeds=neg.to("cuda"),
            height=height, width=width, num_frames=frames, num_inference_steps=steps, guidance_scale=5.0,
            generator=torch.Generator("cpu").manual_seed(7), output_type="np",
        ).frames[0]
        t3 = time.monotonic()
    path = out / f"T3_beach_vace_continuation_{frames}f.mp4"
    write_mp4(result, path, fps=settings.video_fps)
    w, h, n, fps = probe_mp4(path)
    first_frame_diff = float(abs(result[0] * 255 - last.astype("float32")).mean())
    record = {
        "test": "T3_beach_continuation",
        "model": VACE_ID + " (first frame = last frame of previous clip)",
        "source_clip": source.name,
        "output": path.name,
        "resolution": f"{w}x{h}",
        "frames": n,
        "steps": steps,
        "load_seconds": round(load_s, 1),
        "text_encode_seconds_cpu": round(t2 - t1, 1),
        "generate_seconds": round(t3 - t2, 1),
        "peak_vram_gb": round(torch.cuda.max_memory_allocated() / 2**30, 2),
        "mean_abs_diff_first_frame_vs_reference_0_255": round(first_frame_diff, 2),
        "peak_process_ram_gb": peak_rss_gb(),
    }
    (out / f"{path.stem}.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    print(json.dumps(record), flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--source", required=True)
    ap.add_argument("--frames", type=int, default=33)
    ap.add_argument("--steps", type=int, default=20)
    ap.add_argument("--skip-planner", action="store_true")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    if not args.skip_planner:
        bench_planner(out)
    bench_vace(out, Path(args.source), args.frames, args.steps)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
