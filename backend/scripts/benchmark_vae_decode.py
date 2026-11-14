"""Where does a FastWan clip spend its time, and how fast can the VAE decode be without losing quality?

Runs the real model once (text encode on CPU, 3 DMD steps), keeps the latents, then decodes the same latents
with several VAE settings. Reports time, peak VRAM and PSNR against the float32 untiled decode.

  python scripts/benchmark_vae_decode.py --frames 81 --size standard --out /app/outputs/benchmarks/vae
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

PROMPT = (
    "A grey wolf slowly appears from behind a tree in the background. Characters: grey wolf; white sheep. "
    "Setting: a green countryside meadow with tall pine trees, distant mountains and a small river. "
    "Style: cinematic film still."
)
SIZES = {"standard": (576, 320), "large": (832, 480)}


def main() -> None:
    import numpy as np
    import torch

    from app.core.config import get_settings
    from app.services.video_engine import DMD_TIMESTEPS, MAX_TEXT_TOKENS, WanVideoEngine, write_mp4

    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", type=int, default=81)
    ap.add_argument("--size", choices=SIZES, default="standard")
    ap.add_argument("--out", default="/app/outputs/benchmarks/vae")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    width, height = SIZES[args.size]

    engine = WanVideoEngine(get_settings())
    t0 = time.perf_counter()
    engine.load()
    load_s = time.perf_counter() - t0
    pipe = engine._pipe
    device = "cuda"
    report: dict = {"frames": args.frames, "size": f"{width}x{height}", "load_seconds": round(load_s, 1)}

    with torch.inference_mode():
        t0 = time.perf_counter()
        embeds, _ = pipe.encode_prompt(
            prompt=PROMPT, negative_prompt=None, do_classifier_free_guidance=False, num_videos_per_prompt=1,
            max_sequence_length=MAX_TEXT_TOKENS, device=pipe.text_encoder.device, dtype=pipe.transformer.dtype,
        )
        report["text_encode_seconds_cpu"] = round(time.perf_counter() - t0, 2)
        t0 = time.perf_counter()
        embeds2, _ = pipe.encode_prompt(
            prompt=PROMPT, negative_prompt=None, do_classifier_free_guidance=False, num_videos_per_prompt=1,
            max_sequence_length=MAX_TEXT_TOKENS, device=pipe.text_encoder.device, dtype=pipe.transformer.dtype,
        )
        report["text_encode_seconds_cpu_second_call"] = round(time.perf_counter() - t0, 2)
        embeds = embeds.to(device)

        generator = torch.Generator(device="cpu").manual_seed(7)
        torch.cuda.synchronize()
        t0 = time.perf_counter()
        latents = pipe.prepare_latents(1, pipe.transformer.config.in_channels, height, width, args.frames,
                                       torch.float32, torch.device(device), generator)
        for i, t in enumerate(DMD_TIMESTEPS):
            sigma = t / 1000
            v = pipe.transformer(hidden_states=latents.to(pipe.transformer.dtype), timestep=torch.tensor([t], device=device),
                                 encoder_hidden_states=embeds, return_dict=False)[0].float()
            clean = latents - sigma * v
            if i + 1 < len(DMD_TIMESTEPS):
                ns = DMD_TIMESTEPS[i + 1] / 1000
                latents = (1 - ns) * clean + ns * torch.randn(latents.shape, generator=generator).to(device)
            else:
                latents = clean
        torch.cuda.synchronize()
        report["denoise_seconds"] = round(time.perf_counter() - t0, 2)

        vae = pipe.vae
        z = vae.config.z_dim
        mean = torch.tensor(vae.config.latents_mean).view(1, z, 1, 1, 1).to(device)
        std = torch.tensor(vae.config.latents_std).view(1, z, 1, 1, 1).to(device)
        scaled = latents * std + mean

        def decode(dtype, tiled: bool):
            vae.to(dtype)
            (vae.enable_tiling if tiled else vae.disable_tiling)()
            torch.cuda.empty_cache()
            torch.cuda.reset_peak_memory_stats()
            torch.cuda.synchronize()
            t = time.perf_counter()
            video = vae.decode(scaled.to(dtype), return_dict=False)[0]
            torch.cuda.synchronize()
            secs = time.perf_counter() - t
            frames = pipe.video_processor.postprocess_video(video.float(), output_type="np")[0]
            return frames, secs, torch.cuda.max_memory_allocated() / 2**30

        variants = [("fp32_untiled", torch.float32, False), ("fp32_tiled", torch.float32, True),
                    ("bf16_untiled", torch.bfloat16, False), ("bf16_tiled", torch.bfloat16, True)]
        if args.size == "large":  # fp32 untiled needs more than 8 GB at 480p: the tiled fp32 decode is the reference
            variants = variants[1:]
        reference = None
        report["vae"] = {}
        for name, dtype, tiled in variants:
            try:
                frames, secs, peak = decode(dtype, tiled)
            except torch.cuda.OutOfMemoryError:
                report["vae"][name] = {"error": "out of memory"}
                torch.cuda.empty_cache()
                print(name, "OOM", flush=True)
                continue
            arr = np.asarray(frames, dtype=np.float32)
            if reference is None:
                reference = arr
            mse = float(np.mean((arr - reference) ** 2))
            psnr = float("inf") if mse == 0 else 10 * np.log10(1.0 / mse)
            report["vae"][name] = {"seconds": round(secs, 2), "peak_vram_gb": round(peak, 2),
                                   "psnr_vs_reference_db": None if psnr == float("inf") else round(psnr, 2)}
            write_mp4(frames, out / f"{name}_{args.size}_{args.frames}f.mp4", fps=16)
            print(name, report["vae"][name], flush=True)
        vae.to(torch.float32)

    print(json.dumps(report, indent=1))
    (out / f"report_{args.size}_{args.frames}f.json").write_text(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
