"""REAL benchmark: Wan2.2 TI2V-5B (Apache-2.0) text-to-video on this machine's 8 GB GPU.

The 5B transformer is ~10 GB in bf16, so it cannot sit on an 8 GB GPU: its blocks are streamed from CPU RAM one at
a time (diffusers group offloading). The UMT5 text encoder is the one already downloaded for Wan2.1 (same model);
it runs on the CPU first and is freed before the transformer loads, so peak RAM stays below the WSL limit.

    python scripts/benchmark_wan22.py --out /app/outputs/benchmarks/wan22 --width 832 --height 480 --frames 49 --steps 25
"""

from __future__ import annotations

import argparse
import gc
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings  # noqa: E402

WAN22 = "Wan-AI/Wan2.2-TI2V-5B-Diffusers"
NEGATIVE = (
    "blurry, low quality, distorted face, deformed hands, extra fingers, overexposed, static frame, "
    "watermark, text, subtitles, cartoon, painting, jpeg artifacts, flicker"
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--prompt", required=True)
    ap.add_argument("--name", default="wan22")
    ap.add_argument("--width", type=int, default=832)
    ap.add_argument("--height", type=int, default=480)
    ap.add_argument("--frames", type=int, default=49)  # 4k+1; Wan2.2 5B runs at 24 fps
    ap.add_argument("--steps", type=int, default=25)
    ap.add_argument("--guidance", type=float, default=5.0)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    import torch
    from diffusers import AutoencoderKLWan, WanPipeline, WanTransformer3DModel
    from transformers import T5TokenizerFast, UMT5EncoderModel

    from app.services.video_engine import write_mp4

    settings = get_settings()
    hub = {"cache_dir": str(settings.image_model_cache_dir), "local_files_only": True}
    timings: dict[str, float] = {}

    # 1) Prompt -> embeddings on the CPU with Wan2.1's UMT5 (identical encoder), then free it.
    t = time.monotonic()
    tok = T5TokenizerFast.from_pretrained(settings.video_model_id, subfolder="tokenizer", **hub)
    enc = UMT5EncoderModel.from_pretrained(settings.video_model_id, subfolder="text_encoder", dtype=torch.bfloat16, **hub)

    def embed(text: str) -> torch.Tensor:
        ids = tok([text], padding="max_length", max_length=512, truncation=True, add_special_tokens=True,
                  return_attention_mask=True, return_tensors="pt")
        with torch.inference_mode():
            h = enc(ids.input_ids, ids.attention_mask).last_hidden_state.clone()
            n = int(ids.attention_mask.sum())
            h[:, n:] = 0  # Wan zeroes the padding positions
            return h.to("cuda", torch.bfloat16)

    pos, neg = embed(args.prompt), embed(NEGATIVE)
    del enc
    gc.collect()
    timings["text_encode_s"] = round(time.monotonic() - t, 1)

    # 2) Transformer (bf16, streamed block by block) + Wan2.2 VAE.
    t = time.monotonic()
    transformer = WanTransformer3DModel.from_pretrained(WAN22, subfolder="transformer", dtype=torch.bfloat16, **hub)
    vae = AutoencoderKLWan.from_pretrained(WAN22, subfolder="vae", dtype=torch.float32, **hub)
    pipe = WanPipeline.from_pretrained(WAN22, transformer=transformer, vae=vae, text_encoder=None, tokenizer=tok,
                                       dtype=torch.bfloat16, **hub)
    pipe.transformer.enable_group_offload(onload_device=torch.device("cuda"), offload_device=torch.device("cpu"),
                                          offload_type="block_level", num_blocks_per_group=1, use_stream=False)  # pinned 10 GB fails under WSL
    pipe.vae.to("cuda")
    pipe.vae.enable_tiling()
    timings["load_s"] = round(time.monotonic() - t, 1)

    # 3) Generate.
    torch.cuda.reset_peak_memory_stats()
    t = time.monotonic()
    frames = pipe(
        prompt_embeds=pos, negative_prompt_embeds=neg, height=args.height, width=args.width,
        num_frames=args.frames, num_inference_steps=args.steps, guidance_scale=args.guidance,
        generator=torch.Generator("cpu").manual_seed(args.seed), output_type="np",
    ).frames[0]
    timings["generate_s"] = round(time.monotonic() - t, 1)
    path = out / f"{args.name}_{args.width}x{args.height}_{args.frames}f_{args.steps}s.mp4"
    write_mp4(frames, path, fps=24)
    result = {
        "model": WAN22, "output": str(path), "size": f"{args.width}x{args.height}", "frames": args.frames,
        "seconds_of_video": round(args.frames / 24, 2), "steps": args.steps, "guidance": args.guidance,
        **timings, "seconds_per_step": round(timings["generate_s"] / args.steps, 1),
        "peak_vram_gb": round(torch.cuda.max_memory_allocated() / 2**30, 2),
    }
    print(json.dumps(result), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
