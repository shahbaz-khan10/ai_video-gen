"""Phase K real tests through the running app's HTTP API (nothing mocked): upload each test image, queue an
image-to-video job, wait, download the MP4. Runs on the host against http://localhost:8003.

    python backend/scripts/phase_k_app_tests.py --inputs docs/phase_k/inputs --out docs/phase_k/app [--only k1_portrait]
        [--quality draft] [--seconds 3] [--camera none] [--motion normal] [--tag name]
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

API = "http://localhost:8003/api/v1"

TESTS = {
    "k1_portrait": "The woman slowly turns her head slightly to the side and smiles gently.",
    "k2_standing": "The man raises one hand and waves, then lowers it, relaxed natural movement.",
    "k3_sheep": "The sheep walk slowly forward through the meadow, the grass moves gently in the wind.",
    "k4_river": "The river flows, the water ripples and sparkles, clouds drift slowly across the sky, trees sway gently.",
    "k5_market": "The old man looks up and smiles, shoppers walk past in the background.",
}


def call(method: str, path: str, body: bytes | None = None, ctype: str = "application/json") -> dict:
    req = urllib.request.Request(API + path, data=body, method=method, headers={"Content-Type": ctype})
    try:
        with urllib.request.urlopen(req, timeout=120) as res:
            return json.load(res)
    except urllib.error.HTTPError as err:
        raise SystemExit(f"{method} {path} -> {err.code}: {err.read().decode()[:400]}") from None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--inputs", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--only", default=",".join(TESTS))
    ap.add_argument("--quality", default="draft")
    ap.add_argument("--seconds", type=int, default=3)
    ap.add_argument("--resolution", default="standard")
    ap.add_argument("--camera", default="none")
    ap.add_argument("--motion", default="normal")
    ap.add_argument("--seed", type=int, default=4242)
    ap.add_argument("--tag", default="")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    log = out / "app_runs.json"
    rows = json.loads(log.read_text()) if log.exists() else []
    for name in args.only.split(","):
        src = next(Path(args.inputs).glob(f"{name}.*"))
        data = src.read_bytes()
        ctype = "image/png" if src.suffix == ".png" else "image/jpeg"
        uploaded = call("POST", "/uploads/images", data, ctype)
        aspect = "9:16" if uploaded["height"] > uploaded["width"] else "16:9"
        payload = {
            "mode": "image-to-video", "prompt": TESTS[name], "aspect_ratio": aspect,
            "duration_seconds": args.seconds, "resolution": args.resolution, "quality": args.quality,
            "motion": args.motion, "camera": args.camera, "seed": args.seed,
            "source_image": {"upload_id": uploaded["upload_id"]},
        }
        t0 = time.time()
        job = call("POST", "/generations", json.dumps(payload).encode())
        while job["status"] in ("queued", "processing"):
            time.sleep(3)
            job = call("GET", f"/generations/{job['id']}")
        wall = round(time.time() - t0, 1)
        row = {"test": name, "quality": args.quality, "seconds": args.seconds, "resolution": args.resolution,
               "camera": args.camera, "motion": args.motion, "status": job["status"], "wall_seconds": wall,
               "error": job.get("error"), "model_prompt": (job.get("plan") or {}).get("model_prompt"), "job_id": job["id"]}
        if job["status"] == "completed":
            tag = f"_{args.tag}" if args.tag else ""
            path = out / f"{name}_{args.quality}_{args.seconds}s{tag}.mp4"
            with urllib.request.urlopen("http://localhost:8003" + job["video"]["url"]) as res:
                path.write_bytes(res.read())
            row.update(output=path.name, width=job["video"]["width"], height=job["video"]["height"], frames=job["video"]["num_frames"])
        rows.append(row)
        log.write_text(json.dumps(rows, indent=1))
        print(json.dumps({k: row[k] for k in ("test", "quality", "seconds", "status", "wall_seconds")}), flush=True)


if __name__ == "__main__":
    main()
