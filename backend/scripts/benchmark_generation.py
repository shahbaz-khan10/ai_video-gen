"""REAL generation benchmark (not mocked): timings, memory and outputs for fixed prompts.

    python scripts/benchmark_generation.py --out /app/outputs/benchmarks/<name> [--only T1,T3] [--video-frames 33]

For every test it saves the original prompt, the planner's scene plan, the exact prompt sent to the model,
the generated file, and a JSON record with load/encode/denoise/decode times, resolution, duration, peak
VRAM and peak process RAM. Run it with the backend stopped: two models on an 8 GB GPU do not fit.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings  # noqa: E402
from app.schemas.generation import IMAGE_SIZES, VIDEO_SIZES, AspectRatio, ImageResolution, VisualStyle  # noqa: E402

TESTS = {
    "T1_classroom": {
        "kind": "image",
        "prompt": "A realistic school classroom. One male teacher wearing a white shirt and black trousers stands at "
        "the front beside a blackboard, teaching ten students sitting at separate desks. The teacher must be "
        "visible at the front. Students must remain seated.",
    },
    "T2_snow_forest": {
        "kind": "video",
        "prompt": "A cinematic scene of a man wearing a blue jacket walking through a snowy forest at night. Snow is "
        "falling. Tall pine trees surround the path. The camera slowly follows him from behind.",
    },
    "T3_beach": {
        "kind": "video",
        "prompt": "A golden retriever runs along a beach at sunset. Waves move in the background. The camera tracks "
        "the dog from the side.",
    },
    "T4_story": {
        "kind": "story",
        "prompt": "A short cinematic story about a young man walking through a village, meeting an old farmer, "
        "helping him carry vegetables, and returning home at sunset.",
    },
}


def peak_rss_gb() -> float:
    """Peak resident memory of this process (Linux VmHWM), in GB."""
    try:
        for line in Path("/proc/self/status").read_text().splitlines():
            if line.startswith("VmHWM:"):
                return round(int(line.split()[1]) / 1024**2, 2)
    except OSError:
        pass
    return -1.0


def plan_of(prompt: str) -> dict:
    from app.services.prompt_understanding import PromptUnderstandingEngine

    return PromptUnderstandingEngine.plan_scene(prompt, VisualStyle.PHOTOREALISTIC).to_dict()


def bench_image(name: str, prompt: str, out: Path, steps: int) -> dict:
    import torch

    from app.services.image_engine import DiffusersImageEngine, ImageParams

    settings = get_settings()
    engine = DiffusersImageEngine(settings)
    torch.cuda.reset_peak_memory_stats()
    t0 = time.monotonic()
    engine.load()
    load_s = time.monotonic() - t0
    width, height = IMAGE_SIZES[ImageResolution.HIGH][AspectRatio.LANDSCAPE]
    params = ImageParams(prompt=prompt, style=VisualStyle.PHOTOREALISTIC, width=width, height=height, steps=steps, seed=1234)

    sent: dict = {}
    original_fit = engine._fit_prompt

    def capture(parts: list[str]) -> str:
        sent["parts"] = parts
        sent["prompt"] = original_fit(parts)
        return sent["prompt"]

    engine._fit_prompt = capture  # record exactly what the model receives
    t1 = time.monotonic()
    image, device = engine.generate(params, deadline=time.monotonic() + 600)
    gen_s = time.monotonic() - t1
    path = out / f"{name}.png"
    image.save(path)
    engine.unload()
    return {
        "model": engine.model_id,
        "model_prompt": sent.get("prompt"),
        "output": path.name,
        "resolution": f"{width}x{height}",
        "steps": engine._profile.clamp_steps(steps),
        "load_seconds": round(load_s, 1),
        "generate_seconds": round(gen_s, 1),
        "peak_vram_gb": round(torch.cuda.max_memory_allocated() / 2**30, 2),
        "device": device,
    }


def bench_video(name: str, prompt: str, out: Path, frames: int, steps: int, size: str) -> dict:
    import torch

    from app.services.video_engine import WAN_NEGATIVE_PROMPT, WanVideoEngine, write_mp4
    from app.services.video_storage import probe_mp4

    settings = get_settings()
    engine = WanVideoEngine(settings)
    torch.cuda.reset_peak_memory_stats()
    t0 = time.monotonic()
    engine.load()
    load_s = time.monotonic() - t0
    pipe = engine._pipe
    width, height = VIDEO_SIZES[ImageResolution(size)][AspectRatio.LANDSCAPE]

    with torch.inference_mode():
        t1 = time.monotonic()
        pos, neg = pipe.encode_prompt(
            prompt=prompt, negative_prompt=WAN_NEGATIVE_PROMPT, do_classifier_free_guidance=True,
            num_videos_per_prompt=1, device=pipe.text_encoder.device, dtype=pipe.transformer.dtype,
        )
        encode_s = time.monotonic() - t1
        step_times: list[float] = []

        def on_step(_p, _i, _t, kwargs):
            step_times.append(time.monotonic())
            return kwargs

        t2 = time.monotonic()
        result = pipe(
            prompt_embeds=pos.to("cuda"), negative_prompt_embeds=neg.to("cuda"), width=width, height=height,
            num_frames=frames, num_inference_steps=steps, guidance_scale=settings.video_guidance_scale,
            generator=torch.Generator("cpu").manual_seed(42), output_type="np", callback_on_step_end=on_step,
        )
        t3 = time.monotonic()
    denoise_s = step_times[-1] - t2
    decode_s = t3 - step_times[-1]
    path = out / f"{name}.mp4"
    t4 = time.monotonic()
    write_mp4(result.frames[0], path, fps=settings.video_fps)
    encode_mp4_s = time.monotonic() - t4
    w, h, n, fps = probe_mp4(path)
    return {
        "model": engine.model_id,
        "model_prompt": prompt,
        "negative_prompt": WAN_NEGATIVE_PROMPT,
        "output": path.name,
        "resolution": f"{w}x{h}",
        "frames": n,
        "duration_seconds": round(n / fps, 2),
        "steps": steps,
        "guidance_scale": settings.video_guidance_scale,
        "load_seconds": round(load_s, 1),
        "text_encode_seconds_cpu": round(encode_s, 1),
        "denoise_seconds": round(denoise_s, 1),
        "seconds_per_step": round(denoise_s / steps, 2),
        "vae_decode_seconds": round(decode_s, 1),
        "mp4_encode_seconds": round(encode_mp4_s, 2),
        "total_seconds_excluding_load": round(encode_s + denoise_s + decode_s + encode_mp4_s, 1),
        "peak_vram_gb": round(torch.cuda.max_memory_allocated() / 2**30, 2),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--only", default="")
    ap.add_argument("--video-frames", type=int, default=33)
    ap.add_argument("--video-steps", type=int, default=25)
    ap.add_argument("--video-size", choices=["standard", "large"], default="standard")
    ap.add_argument("--image-steps", type=int, default=6)
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    wanted = {t for t in args.only.split(",") if t}

    for name, test in TESTS.items():
        if wanted and not any(name.startswith(w) for w in wanted):
            continue
        record = {"test": name, "kind": test["kind"], "original_prompt": test["prompt"], "scene_plan": plan_of(test["prompt"])}
        try:
            if test["kind"] == "image":
                record["result"] = bench_image(name, test["prompt"], out, args.image_steps)
            elif test["kind"] == "video":
                record["result"] = bench_video(
                    name, test["prompt"], out, args.video_frames, args.video_steps, args.video_size
                )
            else:
                record["result"] = {"skipped": "multi-scene stories are not supported by the current pipeline"}
        except Exception as exc:  # recorded, not hidden
            record["result"] = {"error": f"{type(exc).__name__}: {exc}"}
        record["peak_process_ram_gb"] = peak_rss_gb()
        (out / f"{name}.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
        print(json.dumps({"test": name, **record["result"]}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
