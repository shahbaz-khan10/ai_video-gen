"""REAL inference smoke test: loads the local model and generates one image.

    python scripts/smoke_test.py

Needs PyTorch, Diffusers and downloaded weights (scripts/download_model.py). Unlike the
pytest suite, nothing here is mocked. The image is written to IMAGE_OUTPUT_DIR and then
re-opened to prove it is a valid PNG.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings  # noqa: E402
from app.schemas.generation import IMAGE_SIZES, AspectRatio  # noqa: E402
from app.services.image_engine import DiffusersImageEngine, EngineError, ImageParams  # noqa: E402
from app.services.image_store import ImageStore  # noqa: E402

PROMPT = "RAW photo, documentary photography, three women in shawls drinking tea outdoors, natural light, highly detailed"


def main() -> int:
    settings = get_settings()
    engine = DiffusersImageEngine(settings)
    status = engine.status()
    print(f"Engine state: {status.state} | device: {status.device} | CUDA available: {status.cuda_available}")
    if not status.accepts_jobs:
        print(status.detail)
        return 1

    import torch

    if status.device == "cuda":
        torch.cuda.reset_peak_memory_stats()
        print(f"GPU: {torch.cuda.get_device_name(0)}")

    width, height = IMAGE_SIZES[settings.image_default_resolution][AspectRatio.LANDSCAPE]
    params = ImageParams(
        prompt=PROMPT,
        width=width,
        height=height,
        num_inference_steps=settings.image_default_steps,
        seed=42,
        negative_prompt=settings.image_negative_prompt or None,
    )
    print(f"Model: {settings.image_model_id} | {width}x{height} | {params.num_inference_steps} steps")
    try:
        started = time.monotonic()
        generated = engine.generate(params, deadline=started + settings.image_generation_timeout_seconds)
        first = time.monotonic() - started
        started = time.monotonic()
        engine.generate(params, deadline=started + settings.image_generation_timeout_seconds)
        warm = time.monotonic() - started
    except EngineError as exc:
        print(f"Generation failed [{exc.code}]: {exc.message}")
        return 1

    store = ImageStore(settings.image_output_dir)
    filename = store.save(generated.image, (width, height))
    path = store.resolve(filename)
    assert path is not None

    from PIL import Image

    with Image.open(path) as img:
        img.verify()
    with Image.open(path) as img:
        size, extrema = img.size, img.convert("L").getextrema()

    print(f"First image (incl. model load): {first:.1f}s | warm image: {warm:.2f}s")
    if status.device == "cuda":
        print(f"Peak VRAM allocated: {torch.cuda.max_memory_allocated() / 2**30:.2f} GiB")
    print(f"Saved and re-opened {size[0]}x{size[1]} PNG: {path}")
    if extrema[0] == extrema[1]:
        print("WARNING: the image is a single flat colour, which suggests numerical problems (e.g. NaNs in FP16).")
        return 1
    print("REAL INFERENCE OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
