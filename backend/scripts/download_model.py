"""Download the image model's weights into the Hugging Face cache, once, before first use.

    python scripts/download_model.py

Uses IMAGE_MODEL_ID, IMAGE_MODEL_VARIANT and IMAGE_MODEL_CACHE_DIR from the environment
or backend/.env. For stabilityai/sd-turbo with the fp16 variant this is about 2.6 GB.
Only the Diffusers component folders are fetched (not root-level single-file checkpoints),
and nothing is loaded onto the GPU, so PyTorch isn't needed for this step.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings  # noqa: E402


def main() -> int:
    settings = get_settings()
    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        print("huggingface_hub is not installed. Install requirements-ai.txt first (see backend/README.md).")
        return 1

    variant = settings.image_model_variant
    # Configs, tokenizer files and the weights of each component folder (unet/, vae/, text_encoder/...).
    allow = ["model_index.json", "*/*.json", "*/*.txt", "*/*.model"]
    allow.append(f"*/*.{variant}.safetensors" if variant else "*/*.safetensors")
    ignore = [] if variant else ["*/*.fp16.safetensors"]

    print(f"Model:   {settings.image_model_id}")
    print(f"Variant: {variant or 'default'}")
    print(f"Cache:   {settings.image_model_cache_dir or 'Hugging Face default (~/.cache/huggingface)'}")
    print("Downloading. This needs internet access and can take a while...")
    try:
        path = snapshot_download(
            settings.image_model_id,
            allow_patterns=allow,
            ignore_patterns=ignore,
            cache_dir=str(settings.image_model_cache_dir) if settings.image_model_cache_dir else None,
        )
    except Exception as exc:  # network, auth or missing-repo errors
        print(f"Download failed: {exc}")
        return 1

    files = [f for f in Path(path).rglob("*") if f.is_file()]
    if not any(f.name.endswith(".safetensors") for f in files):
        print(f"No weight files matched variant '{variant}'. Check IMAGE_MODEL_VARIANT.")
        return 1
    size = sum(f.stat().st_size for f in files)
    print(f"Done. {size / 1e9:.2f} GB of model files are cached and ready.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
