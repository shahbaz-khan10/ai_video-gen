"""REAL benchmark: FastWan2.1-T2V-1.3B (DMD-distilled, 3 steps, no CFG) vs. the 25-step Wan baseline.

FastWan's transformer has the same architecture as Wan2.1 T2V 1.3B; only the weights differ. It is sampled
with three fixed timesteps (1000, 757, 522): predict the clean video, re-noise to the next timestep, repeat.
The UMT5 text encoder and VAE are reused from the already-downloaded Wan2.1 repo.

    python scripts/benchmark_fastwan.py --out /app/outputs/benchmarks/<name> --frames 33 --size standard
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings  # noqa: E402
from app.schemas.generation import VIDEO_SIZES, AspectRatio, ImageResolution  # noqa: E402
from app.services.scene_planner import RulePlanner, build_video_prompt  # noqa: E402
from scripts.benchmark_generation import TESTS, peak_rss_gb  # noqa: E402

FASTWAN_ID = "FastVideo/FastWan2.1-T2V-1.3B-Diffusers"
DMD_TIMESTEPS = (1000, 757, 522)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--frames", type=int, default=33)
    ap.add_argument("--size", choices=["standard", "large"], default="standard")
    ap.add_argument("--tests", default="T2_snow_forest,T3_beach")
    ap.add_argument("--plan-prompt", action="store_true", help="send the planner's expanded prompt instead of the raw prompt")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    import torch
    from diffusers import AutoencoderKLWan, WanPipeline, WanTransformer3DModel

    from app.services.video_engine import write_mp4
    from app.services.video_storage import probe_mp4

    settings = get_settings()
    hub = {"cache_dir": str(settings.image_model_cache_dir), "local_files_only": True}
    t0 = time.monotonic()
    transformer = WanTransformer3DModel.from_pretrained(FASTWAN_ID, subfolder="transformer", dtype=torch.bfloat16, **hub)
    vae = AutoencoderKLWan.from_pretrained(settings.video_model_id, subfolder="vae", dtype=torch.float32, **hub)
    pipe = WanPipeline.from_pretrained(settings.video_model_id, transformer=transformer, vae=vae, dtype=torch.bfloat16, **hub)
    pipe.transformer.to("cuda")
    pipe.vae.to("cuda")
    pipe.vae.enable_tiling()
    load_s = time.monotonic() - t0
    width, height = VIDEO_SIZES[ImageResolution(args.size)][AspectRatio.LANDSCAPE]

    for name in args.tests.split(","):
        raw = TESTS[name]["prompt"]
        prompt = build_video_prompt(RulePlanner.plan(raw), "cinematic") if args.plan_prompt else raw
        torch.cuda.reset_peak_memory_stats()
        gen = torch.Generator("cpu").manual_seed(42)
        with torch.inference_mode():
            t1 = time.monotonic()
            embeds, _ = pipe.encode_prompt(
                prompt=prompt, do_classifier_free_guidance=False, num_videos_per_prompt=1,
                max_sequence_length=512, device=pipe.text_encoder.device, dtype=torch.bfloat16,
            )
            embeds = embeds.to("cuda")
            t2 = time.monotonic()
            latents = pipe.prepare_latents(1, 16, height, width, args.frames, torch.float32, torch.device("cuda"), gen)
            for i, t in enumerate(DMD_TIMESTEPS):
                sigma = t / 1000
                velocity = pipe.transformer(
                    hidden_states=latents.to(torch.bfloat16),
                    timestep=torch.tensor([t], device="cuda"),
                    encoder_hidden_states=embeds,
                    return_dict=False,
                )[0].float()
                clean = latents - sigma * velocity  # flow matching: x_t = (1-s)·x0 + s·noise, v = noise - x0
                if i + 1 < len(DMD_TIMESTEPS):
                    next_sigma = DMD_TIMESTEPS[i + 1] / 1000
                    noise = torch.randn(latents.shape, generator=gen, dtype=torch.float32).to("cuda")
                    latents = (1 - next_sigma) * clean + next_sigma * noise
                else:
                    latents = clean
            torch.cuda.synchronize()
            t3 = time.monotonic()
            z_dim = pipe.vae.config.z_dim
            mean = torch.tensor(pipe.vae.config.latents_mean).view(1, z_dim, 1, 1, 1).to("cuda", torch.float32)
            inv_std = 1.0 / torch.tensor(pipe.vae.config.latents_std).view(1, z_dim, 1, 1, 1).to("cuda", torch.float32)
            video = pipe.vae.decode(latents / inv_std + mean, return_dict=False)[0]
            frames = pipe.video_processor.postprocess_video(video, output_type="np")[0]
            t4 = time.monotonic()
        path = out / f"{name}_fastwan_{args.size}_{args.frames}f.mp4"
        write_mp4(frames, path, fps=settings.video_fps)
        t5 = time.monotonic()
        w, h, n, fps = probe_mp4(path)
        result = {
            "model": FASTWAN_ID + " (3-step DMD, no CFG)",
            "model_prompt": prompt,
            "output": path.name,
            "resolution": f"{w}x{h}",
            "frames": n,
            "duration_seconds": round(n / fps, 2),
            "steps": len(DMD_TIMESTEPS),
            "load_seconds": round(load_s, 1),
            "text_encode_seconds_cpu": round(t2 - t1, 1),
            "denoise_seconds": round(t3 - t2, 1),
            "vae_decode_seconds": round(t4 - t3, 1),
            "mp4_encode_seconds": round(t5 - t4, 2),
            "total_seconds_excluding_load": round(t5 - t1, 1),
            "peak_vram_gb": round(torch.cuda.max_memory_allocated() / 2**30, 2),
        }
        record = {"test": name, "original_prompt": raw, "result": result, "peak_process_ram_gb": peak_rss_gb()}
        (out / f"{path.stem}.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
        print(json.dumps({"test": name, **{k: v for k, v in result.items() if k != "model_prompt"}}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
