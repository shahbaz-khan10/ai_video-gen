"""Prompt compiler: scenes, per-scene prompts, token budgets and honest instruction statuses.

Logic tests count words (fast, no model files). The ``real_*`` tests use the models' own tokenizers and run
when the model cache is mounted (AVS_IMAGE_MODEL_CACHE_DIR); otherwise they are skipped.
"""

from __future__ import annotations

import os
import re

import pytest

from app.services.prompt_compiler import compile_plan, segment
from app.services.prompt_tokens import CLIP_MAX_TOKENS, UMT5_MAX_TOKENS, count_tokens, load_tokenizer

MEADOW = (
    "A beautiful green countryside meadow surrounded by tall pine trees, distant green mountains, a small flowing "
    "river, colorful wildflowers, soft sunlight and a blue sky with a few white clouds.\n\n"
    "A white sheep is peacefully eating fresh green grass.\n\n"
    "A grey wolf slowly appears from behind a tree in the background.\n\n"
    "Maintain the same environment, character appearance and lighting throughout.\n\n"
    "Create a cinematic multi-scene story."
)
WOLF_SHEEP = (
    "Create an exactly 30-second cinematic 3D animated wildlife story featuring ONLY TWO main characters: one grey "
    "wolf and one white sheep.\n\nCHARACTER CONSISTENCY (VERY IMPORTANT):\n1. WOLF: One medium-sized grey wolf, dark "
    "grey fur, white chest, yellow eyes, pointed ears, long bushy tail. Keep exactly the same wolf in every scene.\n"
    "2. SHEEP: One small white sheep, fluffy white wool, pink face, black eyes. Keep exactly the same sheep in every "
    "scene.\n\nMaintain the exact same environment and lighting throughout.\n\n"
    "SCENE 1 (0-7 seconds): Wide cinematic establishing shot of the beautiful green meadow. The white sheep is "
    "peacefully eating fresh green grass.\n\nSCENE 2 (7-15 seconds): The grey wolf slowly appears from behind a tree "
    "in the background.\n\nSCENE 3 (15-23 seconds): The sheep notices the wolf and runs toward the river.\n\n"
    "SCENE 4 (23-30 seconds): The wolf stops at the river bank while the sheep escapes across the water."
)
RABBIT = (
    "Title: The Brave Little Rabbit\n\nOnce upon a time, there was a little rabbit named Ruby who lived in a beautiful "
    "forest.\n\nOne day, Ruby heard a tiny bird crying near a river. The bird had fallen from its nest and couldn't "
    "fly.\n\nRuby wanted to help, but the river was deep and dangerous.\n\nShe quickly called her forest friends. A "
    "clever monkey brought a long branch, and a strong elephant carefully lifted the bird.\n\nTogether, they saved "
    "the little bird!\n\nThe bird happily flew back to its mother.\n\nAll the animals praised Ruby for her kindness.\n\n"
    "Ruby smiled and said, \"Even the smallest animal can make a big difference!\"\n\n"
    "Moral: Kindness and teamwork can make the impossible possible."
)


def words(text: str) -> int:
    return len(re.findall(r"\w+|[^\w\s]", text))


def video(prompt: str, seconds: float = 30, budget: int = 511, **kw):
    return compile_plan(prompt, mode="text-to-video", style_text="cinematic film still", style_name="cinematic",
                        duration_seconds=seconds, measure=words, budget=budget, tokenizer_name="words",
                        measured=False, **kw)


def image(prompt: str, budget: int = 75):
    return compile_plan(prompt, mode="text-to-image", style_text="photorealistic raw photo", style_name="photorealistic",
                        measure=words, budget=budget, tokenizer_name="words", measured=False)


def by_target(plan):
    return {c.target: c for c in plan.compiled}


# --- Phase 4 validation prompt ----------------------------------------------------------------------


def test_meadow_story_keeps_environment_colours_and_actions_in_every_scene() -> None:
    plan = video(MEADOW)
    prompts = by_target(plan)
    assert list(prompts) == ["scene 1", "scene 2"]
    for p in prompts.values():
        assert "green countryside meadow" in p.text and "tall pine trees" in p.text  # environment preserved
        assert "white sheep" in p.text  # the sheep stays white (and stays in the shot)
        assert all(c.status == "included" for c in p.components)
    assert "peacefully eating fresh green grass" in prompts["scene 1"].text
    assert "grey wolf slowly appears from behind a tree" in prompts["scene 2"].text.lower()
    assert "grey wolf" in prompts["scene 2"].text
    assert all(i.status == "included" for i in plan.instructions), [(i.text, i.status) for i in plan.instructions]
    keep = next(i for i in plan.instructions if i.text.startswith("Maintain"))
    assert "repeating" in keep.note


# --- structured prompt with SCENE markers and character sheets ----------------------------------------


def test_scene_markers_set_scenes_and_durations() -> None:
    plan = video(WOLF_SHEEP)
    assert [s.duration_seconds for s in plan.scenes] == [7, 8, 8, 7]
    prompts = by_target(plan)
    assert "eating fresh green grass" in prompts["scene 1"].text
    assert "appears from behind a tree" in prompts["scene 2"].text
    assert "runs toward the river" in prompts["scene 3"].text
    assert "escapes across the water" in prompts["scene 4"].text


def test_character_sheets_are_repeated_in_every_scene_they_appear_in() -> None:
    prompts = by_target(video(WOLF_SHEEP))
    for target in ("scene 2", "scene 3", "scene 4"):
        text = prompts[target].text
        assert "dark grey fur, white chest, yellow eyes" in text
        assert "fluffy white wool, pink face" in text
        assert "green meadow" in text  # environment carried from scene 1


def test_no_instruction_is_silently_dropped() -> None:
    plan = video(WOLF_SHEEP)
    statuses = {i.text: i.status for i in plan.instructions}
    assert set(statuses.values()) == {"included"}, statuses
    assert any("Scene boundary (scene 2, 8 s)" in (i.note or "") for i in plan.instructions)
    assert not any("Shorten" in note or "text limit" in note for note in plan.limitations)


def test_long_scene_text_is_never_cut_at_600_characters() -> None:
    long_action = "A white sheep walks slowly across the meadow " + "and looks around carefully " * 40
    plan = video(long_action.strip() + ".", seconds=5)
    assert len(plan.scenes[0].description) > 600
    assert plan.compiled[0].text.startswith(plan.scenes[0].description[:600])


# --- narrative stories ---------------------------------------------------------------------------------


def test_narrative_story_becomes_scenes_with_names_and_pronouns_resolved() -> None:
    plan = video(RABBIT)
    assert len(plan.compiled) >= 6
    texts = [c.text for c in plan.compiled]
    assert not any("Ruby" in t for t in texts)  # the model does not know the name; it gets the description
    called = next(t for t in texts if "called her forest friends" in t)
    assert called.startswith("The little rabbit quickly called")  # "She" is Ruby, not the bird
    statuses = {i.text.split(":")[0]: i for i in plan.instructions}
    assert statuses["Title"].status == "unsupported" and statuses["Moral"].status == "unsupported"
    said = next(i for i in plan.instructions if i.text.startswith("Ruby smiled"))
    assert "Even the smallest animal" in said.note


def test_it_starts_a_new_scene_and_becomes_the_animal() -> None:
    plan = video("A cat sleeps on a sofa. It wakes up and stretches. It walks to the window.", seconds=15)
    assert [c.text.split(".")[0] for c in plan.compiled] == [
        "A cat sleeps on a sofa", "The cat wakes up and stretches", "The cat walks to the window",
    ]


def test_edited_scenes_keep_the_global_environment_and_characters() -> None:
    plan = video(MEADOW, seconds=15, user_scenes=[("The sheep grazes near the river", 7), ("The wolf watches the sheep", 8)])
    prompts = by_target(plan)
    assert [s.duration_seconds for s in plan.scenes] == [7, 8]
    assert prompts["scene 1"].text.startswith("The sheep grazes near the river")
    assert "green countryside meadow" in prompts["scene 2"].text and "grey wolf" in prompts["scene 2"].text


def test_summary_does_not_mistake_fur_for_lighting_or_behind_a_tree_for_a_camera_angle() -> None:
    plan = video(WOLF_SHEEP)
    assert plan.environment.lighting is None and plan.camera.angle is None
    assert plan.environment.location == "meadow"


def test_one_clip_plays_every_moment_in_order() -> None:
    plan = video("A cat sleeps on a sofa. It wakes up and stretches.", seconds=5)
    assert len(plan.compiled) == 1 and plan.compiled[0].target == "video"
    assert "A cat sleeps on a sofa, then the cat wakes up and stretches" in plan.compiled[0].text


# --- budgets -----------------------------------------------------------------------------------------------


def test_budget_compresses_low_priority_parts_first_and_reports_it() -> None:
    plan = video(MEADOW, budget=40)
    for p in plan.compiled:
        assert p.tokens <= 40
        states = {c.name: c.status for c in p.components}
        assert states["action"] == "included"  # the scene's action is the last thing to give way
        assert states["setting"] != "included" or states["style"] != "included"
    statuses = {i.status for i in plan.instructions}
    assert statuses & {"compressed", "omitted_budget"}
    assert any("token budget" in (i.note or "") for i in plan.instructions)


def test_image_shows_one_moment_and_says_why_the_rest_is_not_in_it() -> None:
    plan = image(WOLF_SHEEP)
    assert len(plan.compiled) == 1 and plan.compiled[0].tokens <= 75
    assert "eating fresh green grass" in plan.compiled[0].text
    later = next(i for i in plan.instructions if i.text.startswith("The sheep notices"))
    assert later.status == "unsupported" and "still image shows one moment" in later.note


def test_segments_classify_structure() -> None:
    kinds = [s.kind for s in segment(WOLF_SHEEP)]
    assert kinds[:3] == ["request", "heading", "sheet"]
    assert kinds.count("marker") == 4 and "continuity" in kinds


# --- real tokenizers (run when the model cache is available) ---------------------------------------


def _real(model_id_env: str, default: str):
    cache = os.environ.get("AVS_IMAGE_MODEL_CACHE_DIR")
    tok = load_tokenizer(os.environ.get(model_id_env, default), cache) if cache else None
    if tok is None:
        pytest.skip("model tokenizers not available")
    return tok


@pytest.mark.parametrize("prompt", [MEADOW, WOLF_SHEEP, RABBIT])
def test_real_tokenizers_keep_every_prompt_within_budget(prompt: str) -> None:
    umt5 = _real("AVS_VIDEO_MODEL_ID", "Wan-AI/Wan2.1-T2V-1.3B-Diffusers")
    clip = _real("AVS_IMAGE_MODEL_ID", "SG161222/RealVisXL_V5.0_Lightning")
    vplan = compile_plan(prompt, mode="text-to-video", style_text="cinematic film still", style_name="cinematic",
                         duration_seconds=30, measure=lambda t: count_tokens(umt5, t), budget=UMT5_MAX_TOKENS - 1,
                         tokenizer_name="umt5", measured=True)
    assert all(c.tokens <= UMT5_MAX_TOKENS - 1 for c in vplan.compiled)
    assert all(c.status == "included" for p in vplan.compiled for c in p.components)  # 512 tokens is plenty
    iplan = compile_plan(prompt, mode="text-to-image", style_text="photorealistic raw photo", style_name="photorealistic",
                         measure=lambda t: count_tokens(clip, t), budget=CLIP_MAX_TOKENS - 2,
                         tokenizer_name="clip", measured=True)
    assert iplan.compiled[0].tokens == count_tokens(clip, iplan.compiled[0].text) <= CLIP_MAX_TOKENS - 2


# --- user prompt with markdown sections, multi-line dialogue and visual requirements --------------------

DOOMSDAY = """**VIDEO TITLE: DOOMSDAY – LIVE REVIEW**

A terrified 30-year-old male reporter is standing in the middle of a destroyed city. Buildings are collapsing, cars are burning, dark clouds cover the sky, and huge explosions are visible in the background. He is holding a professional camera and speaking directly into it.

**Dialogue:**
"Guys, I can't believe what I'm witnessing right now.
The entire world is falling apart!"

The camera moves closer to his face. Behind him, the sky turns blood red, massive lightning strikes the ground, people are running in panic, and dust fills the atmosphere.

**Dialogue:**
"This is not a movie, this is happening right now!
There is destruction everywhere, and nobody knows where to go!"

A giant explosion occurs behind the reporter. He turns around in shock, then looks back at the camera. The camera shakes realistically.

**Dialogue:**
"Look behind me!
The buildings are disappearing, the ground is shaking, and this might actually be the end!"

The reporter steps backward as a huge dark cloud approaches. His voice becomes emotional and frightened. The camera captures the burning city behind him.

**Dialogue:**
"If this is my last broadcast, remember what you're seeing.
This is the most terrifying day in human history!"

**VISUAL REQUIREMENTS:**
Ultra-realistic cinematic 4K quality.
Same male reporter, same face, same clothes throughout.
Natural English lip-sync and realistic facial expressions.
Realistic destruction, fire, smoke, lightning and explosions.
Handheld live-reporting camera movement.
Dramatic cinematic sound effects.
No cartoon visuals, no face changes, no character changes.
Total duration exactly 30 seconds."""


def _status(plan, start: str):
    return next(i for i in plan.instructions if i.text.lstrip('"').startswith(start))


def test_markdown_sections_dialogue_and_requirements_are_classified() -> None:
    plan = video(DOOMSDAY, seconds=30)
    assert _status(plan, "VIDEO TITLE").status == "unsupported"
    dialogue = [i for i in plan.instructions if i.text.startswith('"')]
    assert len(dialogue) == 4  # each two-line quote is one instruction
    assert all(i.status == "unsupported" and "silent" in i.note for i in dialogue)
    assert "speech" in _status(plan, "Dialogue").note
    assert _status(plan, "Dramatic cinematic sound effects").status == "unsupported"
    assert "silent" in _status(plan, "His voice becomes").note
    duration = _status(plan, "Total duration exactly 30 seconds")
    assert duration.status == "included" and "matches" in duration.note


def test_visual_requirements_reach_every_scene() -> None:
    plan = video(DOOMSDAY, seconds=30)
    assert len(plan.compiled) >= 4
    for p in plan.compiled:
        assert "Realistic destruction, fire, smoke, lightning and explosions" in p.text
        assert "live-action footage" in p.text and "Ultra-realistic" in p.text and "4K" not in p.text
        assert "reporter" in p.text
    assert _status(plan, "No cartoon visuals").status == "included"
    assert "4K" in _status(plan, "Ultra-realistic cinematic 4K quality").note or "832" in _status(plan, "Ultra-realistic cinematic 4K quality").note
    lips = _status(plan, "Natural English lip-sync")
    assert lips.status == "compressed" and "realistic facial expressions" in " ".join(p.text for p in plan.compiled)


def test_camera_directions_and_scene_details_are_used() -> None:
    plan = video(DOOMSDAY, seconds=30)
    text = " | ".join(p.text for p in plan.compiled)
    assert "moves closer to his face" in text and "shakes realistically" in text
    assert "the sky turns blood red" in text  # detail after an action is part of that scene
    for start in ("The camera moves closer", "The camera shakes", "Handheld live-reporting", "Behind him, the sky"):
        assert _status(plan, start).status in ("included", "compressed"), start
    assert not [i.text for i in plan.instructions if (i.note or "").startswith("Could not")]
