"""Does a reference image keep the same person across scenes? Prompt-only FastWan vs Wan VACE 1.3B with a
reference image, on the same scene texts, seeds, size and length.

  python scripts/benchmark_consistency.py --reference /out/reporter_reference.png --out /out
Writes one MP4 per method and scene, a JSON record (time, VRAM, RAM) and a comparison sheet.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

LOOK = ("a 30-year-old male news reporter with short dark brown hair, clean-shaven, wearing a dark grey jacket over "
        "a light blue collared shirt")
STYLE = "Ultra-realistic cinematic live-action footage, handheld camera."
SCENES = [
    f"{LOOK} stands in the middle of a destroyed city, buildings collapsing, cars burning, dark clouds and huge "
    f"explosions in the background. {STYLE}",
    f"Close-up of {LOOK} holding a professional camera and speaking into it, the destroyed city burning behind him. {STYLE}",
    f"A giant explosion behind {LOOK}; he turns around in shock, then looks back at the camera, smoke and fire around. {STYLE}",
]
WIDTH, HEIGHT, FPS = 576, 320, 16


def rss_gib() -> float:
    from app.services.memory import snapshot

    return round(snapshot().process_rss_gib or 0, 2)


def main() -> None:
    import torch
    from PIL import Image

    from app.core.config import get_settings
    from app.services import memory
    from app.services.video_engine import VideoParams, WanVideoEngine, WAN_NEGATIVE_PROMPT, write_mp4

    ap = argparse.ArgumentParser()
    ap.add_argument("--reference", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--frames", type=int, default=49)
    ap.add_argument("--vace-steps", type=int, default=20)
    ap.add_argument("--only", choices=["fastwan", "vace"], default=None)
    ap.add_argument("--same-seed", action="store_true", help="FastWan: one seed for every scene")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    settings = get_settings()
    record: dict = {"frames": args.frames, "size": f"{WIDTH}x{HEIGHT}", "scenes": SCENES, "methods": {}}

    # --- A: prompt only, FastWan (what the app does today) ------------------------------------
    if args.only in (None, "fastwan"):
        engine = WanVideoEngine(settings)
        t0 = time.perf_counter()
        engine.load()
        rec = {"load_seconds": round(time.perf_counter() - t0, 1), "clips": []}
        for k, prompt in enumerate(SCENES):
            torch.cuda.reset_peak_memory_stats()
            t = time.perf_counter()
            tag = "fastwan_sameseed" if args.same_seed else "fastwan"
            path = out / f"{tag}_scene{k + 1}.mp4"
            engine.generate(VideoParams(prompt=prompt, width=WIDTH, height=HEIGHT, num_frames=args.frames,
                                        num_inference_steps=3, seed=100 if args.same_seed else 100 + k, fps=FPS),
                            deadline=time.monotonic() + 3600, output_path=path)
            rec["clips"].append({"scene": k + 1, "seconds": round(time.perf_counter() - t, 1),
                                 "peak_vram_gb": round(torch.cuda.max_memory_allocated() / 2**30, 2)})
            print("fastwan", rec["clips"][-1], flush=True)
        rec["peak_rss_gib"] = rss_gib()
        engine.unload()
        record["methods"]["fastwan_same_seed" if args.same_seed else "fastwan_prompt_only"] = rec

    # --- B: VACE 1.3B with the reference image -------------------------------------------------
    if args.only in (None, "vace"):
        from diffusers import AutoencoderKLWan, UniPCMultistepScheduler, WanPipeline, WanVACEPipeline, WanVACETransformer3DModel

        memory.release()
        hub = {"cache_dir": str(settings.image_model_cache_dir), "local_files_only": True}
        t0 = time.perf_counter()
        base = WanPipeline.from_pretrained(settings.video_model_id, transformer=None, vae=None, **hub)
        vae = AutoencoderKLWan.from_pretrained(settings.video_model_id, subfolder="vae", dtype=torch.bfloat16, **hub)
        transformer = WanVACETransformer3DModel.from_pretrained(
            "Wan-AI/Wan2.1-VACE-1.3B-diffusers", subfolder="transformer", dtype=torch.bfloat16, **hub
        )
        pipe = WanVACEPipeline(
            tokenizer=base.tokenizer, text_encoder=base.text_encoder.to(torch.bfloat16), vae=vae,
            scheduler=UniPCMultistepScheduler.from_config(base.scheduler.config, flow_shift=3.0), transformer=transformer,
        )
        pipe.transformer.to("cuda")
        pipe.vae.to("cuda")
        pipe.set_progress_bar_config(disable=True)
        rec = {"load_seconds": round(time.perf_counter() - t0, 1), "steps": args.vace_steps, "guidance": 5.0, "clips": []}
        reference = Image.open(args.reference).convert("RGB")
        for k, prompt in enumerate(SCENES):
            torch.cuda.reset_peak_memory_stats()
            t = time.perf_counter()
            with torch.inference_mode():
                pos, neg = pipe.encode_prompt(prompt=prompt, negative_prompt=WAN_NEGATIVE_PROMPT,
                                              do_classifier_free_guidance=True, num_videos_per_prompt=1,
                                              device=pipe.text_encoder.device, dtype=torch.bfloat16, max_sequence_length=512)
                frames = pipe(
                    reference_images=[reference], prompt_embeds=pos.to("cuda"), negative_prompt_embeds=neg.to("cuda"),
                    height=HEIGHT, width=WIDTH, num_frames=args.frames, num_inference_steps=args.vace_steps,
                    guidance_scale=5.0, generator=torch.Generator("cpu").manual_seed(100 + k), output_type="np",
                ).frames[0]
            write_mp4(frames, out / f"vace_ref_scene{k + 1}.mp4", fps=FPS)
            rec["clips"].append({"scene": k + 1, "seconds": round(time.perf_counter() - t, 1),
                                 "peak_vram_gb": round(torch.cuda.max_memory_allocated() / 2**30, 2)})
            print("vace", rec["clips"][-1], flush=True)
        rec["peak_rss_gib"] = rss_gib()
        record["methods"]["vace_reference"] = rec

    prev = out / "consistency_report.json"
    if prev.exists() and args.only:
        old = json.loads(prev.read_text())
        old["methods"].update(record["methods"])
        record = old
    prev.write_text(json.dumps(record, indent=1))
    print(json.dumps(record["methods"], indent=1))


if __name__ == "__main__":
    main()
