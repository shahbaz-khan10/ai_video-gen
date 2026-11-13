"""Measures real tokenizer lengths of the prompts the app sends to its models.

Run inside the backend image with the models volume mounted (tokenizers are read from the local cache):
  python scripts/audit_prompt_tokens.py [--out report.json]

For each test prompt it shows: prompt length in CLIP (RealVisXL) and UMT5 (Wan) tokens, how the current
planner splits it into scenes, the exact model prompt(s) built, their token counts, and which clauses the
planner reports as not reaching the model.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings  # noqa: E402

PROMPTS = {
    "phase4_meadow": (
        "A beautiful green countryside meadow surrounded by tall pine trees, distant green mountains, a small "
        "flowing river, colorful wildflowers, soft sunlight and a blue sky with a few white clouds.\n\n"
        "A white sheep is peacefully eating fresh green grass.\n\n"
        "A grey wolf slowly appears from behind a tree in the background.\n\n"
        "Maintain the same environment, character appearance and lighting throughout.\n\n"
        "Create a cinematic multi-scene story."
    ),
    # Reconstruction of the structure of the user's wolf/sheep prompt (the original job record was lost);
    # the instruction lines are the ones quoted in the bug report.
    "wolf_sheep_structured": (
        "Create an exactly 30-second cinematic 3D animated wildlife story featuring ONLY TWO main characters: one "
        "grey wolf and one white sheep.\n\nCHARACTER CONSISTENCY (VERY IMPORTANT):\n1. WOLF: One medium-sized grey "
        "wolf, dark grey fur, white chest, yellow eyes, pointed ears, long bushy tail. Keep exactly the same wolf "
        "in every scene.\n2. SHEEP: One small white sheep, fluffy white wool, pink face, black eyes. Keep exactly "
        "the same sheep in every scene.\n\nMaintain the exact same environment and lighting throughout.\n\n"
        "SCENE 1 (0-7 seconds): Wide cinematic establishing shot of the beautiful green meadow. The white sheep is "
        "peacefully eating fresh green grass.\n\nSCENE 2 (7-15 seconds): The grey wolf slowly appears from behind a "
        "tree in the background.\n\nSCENE 3 (15-23 seconds): The sheep notices the wolf and runs toward the river.\n\n"
        "SCENE 4 (23-30 seconds): The wolf stops at the river bank while the sheep escapes across the water."
    ),
    "rabbit_story": (
        "Title: The Brave Little Rabbit\n\nOnce upon a time, there was a little rabbit named Ruby who lived in a "
        "beautiful forest.\n\nOne day, Ruby heard a tiny bird crying near a river. The bird had fallen from its nest "
        "and couldn't fly.\n\nRuby wanted to help, but the river was deep and dangerous.\n\nShe quickly called her "
        "forest friends. A clever monkey brought a long branch, and a strong elephant carefully lifted the bird.\n\n"
        "Together, they saved the little bird!\n\nThe bird happily flew back to its mother.\n\nAll the animals "
        "praised Ruby for her kindness.\n\nRuby smiled and said, \"Even the smallest animal can make a big "
        "difference!\"\n\nMoral: Kindness and teamwork can make the impossible possible."
    ),
    "classroom": "A teacher standing in front of 10 students in a classroom.",
}


def tokenizers():
    from app.services.prompt_tokens import load_tokenizer

    s = get_settings()
    clip = load_tokenizer(s.image_model_id, s.image_model_cache_dir)
    umt5 = load_tokenizer(s.video_model_id, s.image_model_cache_dir)
    if clip is None or umt5 is None:
        raise SystemExit("Tokenizers not found in the model cache.")
    return clip, umt5


def count(tok, text: str) -> int:
    return len(tok(text, add_special_tokens=False).input_ids)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out")
    parser.add_argument("--duration", type=int, default=30)
    parser.add_argument("--after", action="store_true", help="Measure the prompt compiler instead of the old planner.")
    args = parser.parse_args()
    if args.after:
        return after(args)

    from app.services.scene_planner import RulePlanner, build_image_prompt_parts, build_video_prompt, validate

    clip, umt5 = tokenizers()
    clip_budget = clip.model_max_length - 2
    report = {"clip_budget_tokens": clip_budget, "umt5_budget_tokens": 512, "prompts": {}}
    for name, prompt in PROMPTS.items():
        plan = RulePlanner.plan(prompt)
        scenes = plan.scenes
        video_prompts = [build_video_prompt(plan, "cinematic", s) for s in scenes]
        image_prompt = ", ".join(build_image_prompt_parts(plan, "photorealistic"))
        checked = validate(plan, mode="text-to-video", model_prompt=" | ".join(video_prompts))
        # Where CLIP would cut the image prompt: the text of the first 77 tokens.
        ids = clip(image_prompt, add_special_tokens=False).input_ids
        clip_kept = clip.decode(ids[:clip_budget])
        entry = {
            "chars": len(prompt),
            "clip_tokens": count(clip, prompt),
            "umt5_tokens": count(umt5, prompt),
            "scenes": len(scenes),
            "scene_descriptions_chars": [len(s.description) for s in scenes],
            "scene_description_truncated_at_600": any(len(s.description) >= 600 for s in scenes),
            "video_prompts": [{"text": p, "umt5_tokens": count(umt5, p)} for p in video_prompts],
            "image_prompt_clip_tokens": len(ids),
            "image_prompt_clip_kept": clip_kept,
            "image_prompt_clip_dropped": clip.decode(ids[clip_budget:]) if len(ids) > clip_budget else "",
            "instructions": [
                {"text": i.text, "status": i.status, "reaches_model": i.reaches_model} for i in checked.instructions
            ],
            "limitations": checked.limitations,
        }
        report["prompts"][name] = entry
        print(f"\n=== {name}: {entry['chars']} chars | CLIP {entry['clip_tokens']} tokens (budget {clip_budget}) | "
              f"UMT5 {entry['umt5_tokens']} tokens (budget 512) | scenes {entry['scenes']}")
        for k, vp in enumerate(entry["video_prompts"], 1):
            print(f"  video prompt {k}: {vp['umt5_tokens']} UMT5 tokens")
        print(f"  image prompt: {len(ids)} CLIP tokens; dropped by CLIP: {entry['image_prompt_clip_dropped'][:160]!r}")
        print(f"  600-char scene cut: {entry['scene_description_truncated_at_600']}")
        for i in entry["instructions"]:
            flag = "" if i["reaches_model"] else "  <-- reported 'cut off by the model's text limit'"
            print(f"  [{i['status']:9}] {i['text'][:90]}{flag}")
    if args.out:
        Path(args.out).write_text(json.dumps(report, indent=1), encoding="utf-8")


def after(args) -> None:
    """Same prompts through the prompt compiler, for video (args.duration s) and for an image."""
    from app.services.image_engine import STYLE_PROMPTS
    from app.services.prompt_compiler import compile_plan
    from app.services.prompt_tokens import count_tokens

    clip, umt5 = tokenizers()
    report = {"prompts": {}}
    for name, prompt in PROMPTS.items():
        entry = {}
        for mode, tok, budget, tname, duration in (
            ("text-to-video", umt5, 511, "umt5 (Wan2.1)", args.duration),
            ("text-to-image", clip, clip.model_max_length - 2, "clip (RealVisXL)", None),
        ):
            style = "cinematic" if mode == "text-to-video" else "photorealistic"
            plan = compile_plan(
                prompt, mode=mode, style_text=STYLE_PROMPTS.get(style), style_name=style, duration_seconds=duration,
                measure=lambda t, tok=tok: count_tokens(tok, t), budget=budget, tokenizer_name=tname, measured=True,
            )
            entry[mode] = json.loads(plan.model_dump_json(include={"scenes", "instructions", "compiled", "limitations"}))
            print(f"\n=== {name} · {mode}{f' {duration}s' if duration else ''}: {len(plan.compiled)} prompt(s)")
            for c in plan.compiled:
                states = ", ".join(f"{x.name}={x.status}" for x in c.components)
                print(f"  [{c.target}] {c.tokens}/{c.budget} tokens ({c.model}) · {states}")
                print(f"     {c.text}")
            for i in plan.instructions:
                print(f"  {i.status:15} {i.text[:85]!r}" + (f"  — {i.note}" if i.note else ""))
        report["prompts"][name] = entry
    if args.out:
        Path(args.out).write_text(json.dumps(report, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
