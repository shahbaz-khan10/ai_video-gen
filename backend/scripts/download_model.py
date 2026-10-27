"""Download image-model weights into IMAGE_MODEL_CACHE_DIR, once.

Usage (from backend/, with the venv active):

    python scripts/download_model.py          # shows size, asks before downloading
    python scripts/download_model.py --yes    # no prompt

Only the files the FP16 Diffusers pipeline needs are fetched (about 2.6 GB for
stabilityai/sd-turbo). The single-file checkpoint and full-precision duplicates are
skipped. Needs internet access once. The API itself never downloads weights.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings  # noqa: E402

ALLOW_PATTERNS = [
    "model_index.json",
    "LICENSE*",
    "scheduler/*",
    "tokenizer/*",
    "*/config.json",
    "*.fp16.safetensors",
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--yes", action="store_true", help="download without asking")
    args = parser.parse_args()

    try:
        from huggingface_hub import HfApi, snapshot_download
    except ImportError:
        print("huggingface_hub is not installed. Install the AI requirements first (see backend/README.md).")
        return 1

    settings = get_settings()
    model_id = settings.image_model_id
    cache_dir = settings.image_model_cache_dir

    from fnmatch import fnmatch

    info = HfApi().model_info(model_id, files_metadata=True)
    files = [s for s in info.siblings if any(fnmatch(s.rfilename, p) for p in ALLOW_PATTERNS)]
    if not any(s.rfilename.endswith(".fp16.safetensors") for s in files):
        print(f"{model_id} has no fp16 safetensors variant; this script only supports Diffusers fp16 repos.")
        return 1
    total = sum(s.size or 0 for s in files)
    free = shutil.disk_usage(cache_dir.anchor or ".").free

    print(f"Model:       {model_id}")
    print(f"Destination: {cache_dir}")
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
        snapshot_download(model_id, cache_dir=str(cache_dir), allow_patterns=ALLOW_PATTERNS)
    except Exception as err:  # network errors, interrupted downloads, gated repos
        print(f"Download failed: {type(err).__name__}: {err}")
        print("Re-run the script to resume; completed files are not downloaded again.")
        return 1
    print("Done. The backend will load the model on the first text-to-image request.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
