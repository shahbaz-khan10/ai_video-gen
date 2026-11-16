"""REAL image-to-video benchmark on the models already on disk (nothing mocked, nothing downloaded).

Wan2.1 has no official 1.3B image-to-video model. Wan2.1 VACE 1.3B (Apache-2.0, on disk) can animate an image:
the image is the first frame of the control video and the mask says "keep frame 0, generate the rest".

Variants
  vace20    VACE 1.3B as released: UniPC, 20 steps, CFG 5 (two transformer passes per step).
  vace8     the same with 8 steps.
  *_ref     also passes the image as a VACE reference image (identity anchor).
  vacefast  VACE context blocks + FastWan's DMD-distilled base blocks (VACE was trained with the base model frozen,
            so its base blocks are Wan2.1 T2V 1.3B, the model FastWan was distilled from): 3 steps, no CFG.

Measured per clip: time, peak VRAM, process RAM, frame-0 fidelity (PSNR vs the uploaded image), drift (PSNR of the
last frame vs frame 0, low = scene changed a lot), motion energy (mean |frame diff|, 0-255).

    python scripts/benchmark_i2v.py --inputs /in --out /out [--only vacefast] [--frames 49]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

VACE_ID = "Wan-AI/Wan2.1-VACE-1.3B-diffusers"
FAST_ID = "FastVideo/FastWan2.1-T2V-1.3B-Diffusers"
DMD_SIGMAS = [1.0, 0.757, 0.522]

TESTS = {
    "k1_portrait": "The woman slowly turns her head slightly to the side and smiles gently, her hair moving a little.",
    "k2_standing": "The man shifts his weight, raises one hand to wave and smiles, natural relaxed movement.",
    "k3_sheep": "The sheep walk slowly forward through the meadow, grass moving gently in the wind.",
    "k4_river": "The river flows gently, water rippling, clouds drift slowly across the sky, trees sway in the wind.",
    "k5_market": "The old man looks up and smiles, shoppers move in the background, lamps sway slightly.",
}


def fit(img, width: int, height: int):
    """Cover-crop to the target aspect, then resize (no stretching)."""
    from PIL import Image

    src_ratio, dst_ratio = img.width / img.height, width / height
    if src_ratio > dst_ratio:  # too wide: crop the sides
        w = round(img.height * dst_ratio)
        img = img.crop(((img.width - w) // 2, 0, (img.width - w) // 2 + w, img.height))
    else:
        h = round(img.width / dst_ratio)
        img = img.crop((0, (img.height - h) // 2, img.width, (img.height - h) // 2 + h))
    return img.convert("RGB").resize((width, height), Image.LANCZOS)


def psnr(a, b) -> float:
    import numpy as np

    mse = float(np.mean((a.astype(np.float32) - b.astype(np.float32)) ** 2))
    return round(10 * np.log10(255.0**2 / max(mse, 1e-6)), 2)


def build(variant: str):
    import torch
    from diffusers import (
        AutoencoderKLWan,
        FlowMatchEulerDiscreteScheduler,
        UniPCMultistepScheduler,
        WanPipeline,
        WanVACEPipeline,
        WanVACETransformer3DModel,
    )

    from app.core.config import get_settings

    settings = get_settings()
    hub = {"cache_dir": str(settings.image_model_cache_dir), "local_files_only": True}
    base = WanPipeline.from_pretrained(settings.video_model_id, transformer=None, vae=None, **hub)
    vae = AutoencoderKLWan.from_pretrained(settings.video_model_id, subfolder="vae", dtype=torch.bfloat16, **hub)
    transformer = WanVACETransformer3DModel.from_pretrained(VACE_ID, subfolder="transformer", dtype=torch.bfloat16, **hub)
    if variant.startswith("vacefast"):
        from diffusers import WanTransformer3DModel

        fast = WanTransformer3DModel.from_pretrained(FAST_ID, subfolder="transformer", dtype=torch.bfloat16, **hub)
        fast_sd = fast.state_dict()
        own = transformer.state_dict()
        shared = {k: v for k, v in fast_sd.items() if k in own and own[k].shape == v.shape}
        missing = [k for k in own if not k.startswith("vace_") and k not in shared]
        print(json.dumps({"grafted_tensors": len(shared), "base_tensors_not_grafted": missing[:5]}), flush=True)
        transformer.load_state_dict(shared, strict=False)
        del fast, fast_sd
        scheduler = FlowMatchEulerDiscreteScheduler(shift=1.0, stochastic_sampling=True)
        original = scheduler.set_timesteps

        def dmd_timesteps(num_inference_steps=None, device=None, **_kw):
            original(sigmas=DMD_SIGMAS, device=device)

        scheduler.set_timesteps = dmd_timesteps
    else:
        scheduler = UniPCMultistepScheduler.from_config(base.scheduler.config, flow_shift=3.0)
    pipe = WanVACEPipeline(
        tokenizer=base.tokenizer, text_encoder=base.text_encoder.to(torch.bfloat16), vae=vae,
        scheduler=scheduler, transformer=transformer,
    )
    pipe.transformer.to("cuda")
    pipe.vae.to("cuda")
    pipe.set_progress_bar_config(disable=True)
    return pipe


def main() -> None:
    import numpy as np
    import torch
    from PIL import Image

    from app.services.video_engine import WAN_NEGATIVE_PROMPT, write_mp4

    ap = argparse.ArgumentParser()
    ap.add_argument("--inputs", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--only", default="vace20,vacefast")
    ap.add_argument("--tests", default=",".join(TESTS))
    ap.add_argument("--frames", type=int, default=49)
    ap.add_argument("--large", action="store_true", help="480p instead of Draft size")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    report = out / "i2v_report.json"
    rows = json.loads(report.read_text()) if report.exists() else []

    for variant in args.only.split(","):
        t0 = time.perf_counter()
        pipe = build(variant)
        load_s = round(time.perf_counter() - t0, 1)
        fast = variant.startswith("vacefast")
        steps = 3 if fast else int(variant.removeprefix("vace").split("_")[0])
        use_ref = variant.endswith("_ref")
        for name in args.tests.split(","):
            src = Image.open(next(Path(args.inputs).glob(f"{name}.*")))
            portrait = src.height > src.width
            w, h = ((480, 832) if portrait else (832, 480)) if args.large else ((320, 576) if portrait else (576, 320))
            first = fit(src, w, h)
            frames = args.frames
            video = [first] + [Image.new("RGB", (w, h), (128, 128, 128))] * (frames - 1)
            mask = [Image.new("L", (w, h), 0)] + [Image.new("L", (w, h), 255)] * (frames - 1)
            torch.cuda.reset_peak_memory_stats()
            t1 = time.perf_counter()
            with torch.inference_mode():
                pos, neg = pipe.encode_prompt(
                    prompt=TESTS[name], negative_prompt=None if fast else WAN_NEGATIVE_PROMPT,
                    do_classifier_free_guidance=not fast, num_videos_per_prompt=1, max_sequence_length=512,
                    device=pipe.text_encoder.device, dtype=torch.bfloat16,
                )
                t2 = time.perf_counter()
                result = pipe(
                    video=video, mask=mask, prompt_embeds=pos.to("cuda"),
                    negative_prompt_embeds=None if fast else neg.to("cuda"),
                    height=h, width=w, num_frames=frames, num_inference_steps=steps, reference_images=[first] if use_ref else None,
                    guidance_scale=1.0 if fast else 5.0, generator=torch.Generator("cpu").manual_seed(4242),
                    output_type="np",
                ).frames[0]
            gen_s = time.perf_counter() - t2
            suffix = "_480p" if args.large else ""
            path = out / f"{name}_{variant}{suffix}.mp4"
            write_mp4(result, path, fps=16)
            u8 = [(np.clip(f, 0, 1) * 255).round().astype(np.uint8) for f in result]
            ref = np.asarray(first)
            row = {
                "test": name, "variant": variant, "size": f"{w}x{h}", "frames": frames,
                "load_seconds": load_s, "text_encode_seconds": round(t2 - t1, 1), "generate_seconds": round(gen_s, 1),
                "peak_vram_gb": round(torch.cuda.max_memory_allocated() / 2**30, 2),
                "process_ram_gib": round(int(next(l for l in open("/proc/self/status") if l.startswith("VmRSS")).split()[1]) / 2**20, 2),
                "frame0_psnr_vs_input": psnr(u8[0], ref),
                "last_frame_psnr_vs_input": psnr(u8[-1], ref),
                "motion_energy": round(float(np.mean([np.abs(u8[i + 1].astype(np.float32) - u8[i]).mean() for i in range(len(u8) - 1)])), 2),
                "output": path.name,
            }
            Image.fromarray(np.concatenate([u8[0], u8[len(u8) // 2], u8[-1]], axis=1)).save(out / f"{path.stem}_strip.jpg", quality=88)
            rows = [r for r in rows if not (r["test"] == name and r["variant"] == variant and r["size"] == row["size"])] + [row]
            report.write_text(json.dumps(rows, indent=1))
            print(json.dumps(row), flush=True)
            del result, u8
            torch.cuda.empty_cache()
        del pipe
        torch.cuda.empty_cache()


if __name__ == "__main__":
    main()
