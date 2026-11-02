"""Download image-model weights into IMAGE_MODEL_CACHE_DIR, once.

Supports photorealistic models (e.g. Realistic Vision, SDXL) and rapid draft models (SD-Turbo).
"""

from __future__ import annotations

import argparse
import shutil
import sys
from fnmatch import fnmatch
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--yes", action="store_true", help="download without asking")
    parser.add_argument("--model", type=str, default=None, help="override model id to download")
    args = parser.parse_args()

    try:
        from huggingface_hub import HfApi, snapshot_download
    except ImportError:
        print("huggingface_hub is not installed. Install the AI requirements first (see backend/README.md).")
        return 1

    settings = get_settings()
    model_id = args.model or settings.image_model_id
    cache_dir = settings.image_model_cache_dir

    try:
        info = HfApi().model_info(model_id, files_metadata=True)
    except Exception as err:
        print(f"Failed to query model {model_id}: {err}")
        return 1

    # Check whether fp16 variant exists in repo
    has_fp16 = any(s.rfilename.endswith(".fp16.safetensors") for s in info.siblings)

    allow_patterns = [
        "model_index.json",
        "LICENSE*",
        "scheduler/*",
        "tokenizer/*",
        "*/config.json",
    ]
    if has_fp16:
        allow_patterns.append("*.fp16.safetensors")
    else:
        allow_patterns.append("*.safetensors")

    files = [s for s in info.siblings if any(fnmatch(s.rfilename, p) for p in allow_patterns)]
    total = sum(s.size or 0 for s in files)
    free = shutil.disk_usage(cache_dir.anchor or ".").free

    print(f"Model:       {model_id}")
    print(f"Destination: {cache_dir}")
    print(f"Format:      {'FP16' if has_fp16 else 'Standard Safetensors'}")
    print(f"Files:       {len(files)}  ({total / 1e9:.2f} GB)")
    print(f"Free disk:   {free / 1e9:.1f} GB")
    print("License:     read it at https://huggingface.co/" + model_id)
    if free < total + 1e9:
        print("Not enough free disk space (needs the download size plus 1 GB headroom).")
        return 1
    if not args.yes and input("Download now? [y/N] ").strip().lower() != "y":
        print("Cancelled.")
        return 1

    cache_dir.mkdir(parents=True, exist_ok=True)
    try:
        snapshot_download(model_id, cache_dir=str(cache_dir), allow_patterns=allow_patterns)
    except Exception as err:
        print(f"Download failed: {type(err).__name__}: {err}")
        print("Re-run the script to resume; completed files are not downloaded again.")
        return 1
    print(f"Done. {model_id} downloaded successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
