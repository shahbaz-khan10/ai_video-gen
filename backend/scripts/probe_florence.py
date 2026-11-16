"""Real probe of Florence-2-base (MIT): detailed caption + object detection on test photos; time and memory.

    python scripts/probe_florence.py /k/inputs/*.png /k/user/user_photo.png [--cpu]
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

MODEL = "florence-community/Florence-2-base"


def main() -> None:
    import torch
    from PIL import Image
    from transformers import AutoProcessor, Florence2ForConditionalGeneration

    from app.core.config import get_settings

    cpu = "--cpu" in sys.argv
    paths = [p for p in sys.argv[1:] if not p.startswith("--")]
    device = "cpu" if cpu or not torch.cuda.is_available() else "cuda"
    dtype = torch.float32 if device == "cpu" else torch.float16
    hub = {"cache_dir": str(get_settings().image_model_cache_dir), "local_files_only": True}
    t0 = time.perf_counter()
    processor = AutoProcessor.from_pretrained(MODEL, **hub)
    model = Florence2ForConditionalGeneration.from_pretrained(MODEL, torch_dtype=dtype, **hub).to(device).eval()
    print(json.dumps({"device": device, "load_seconds": round(time.perf_counter() - t0, 1),
                      "vram_gb": round(torch.cuda.memory_allocated() / 2**30, 2) if device == "cuda" else 0}), flush=True)

    def run(task: str, image, text: str = ""):
        inputs = processor(text=task + text, images=image, return_tensors="pt").to(device, dtype)
        with torch.inference_mode():
            ids = model.generate(**inputs, max_new_tokens=256, num_beams=3, do_sample=False)
        raw = processor.batch_decode(ids, skip_special_tokens=False)[0]
        return processor.post_process_generation(raw, task=task, image_size=image.size)[task]

    for path in paths:
        image = Image.open(path).convert("RGB")
        t = time.perf_counter()
        caption = run("<MORE_DETAILED_CAPTION>", image)
        t1 = time.perf_counter()
        od = run("<OD>", image)
        t2 = time.perf_counter()
        labels: dict[str, int] = {}
        for label in od.get("labels", []):
            labels[label] = labels.get(label, 0) + 1
        print(json.dumps({"image": Path(path).name, "caption": caption, "caption_s": round(t1 - t, 2),
                          "objects": labels, "od_s": round(t2 - t1, 2)}), flush=True)


if __name__ == "__main__":
    main()
