"""Scene planner: rule extraction, clause coverage, limitations and the LLM merge guard rails.

No model is loaded here; the LLM layer is tested through ``merge`` with hand-written replies.
"""

from __future__ import annotations

import pytest

from app.services.llm_planner import _parse_json, merge
from app.services.scene_planner import (
    RulePlanner,
    build_image_prompt_parts,
    build_video_prompt,
    negative_terms,
    split_clauses,
    validate,
)

CLASSROOM = (
    "A realistic school classroom. One male teacher wearing a white shirt and black trousers stands at the front "
    "beside a blackboard, teaching ten students sitting at separate desks. The teacher must be visible at the "
    "front. Students must remain seated."
)
FOREST = (
    "A cinematic scene of a man wearing a blue jacket walking through a snowy forest at night. Snow is falling. "
    "Tall pine trees surround the path. The camera slowly follows him from behind."
)
BEACH = "A golden retriever runs along a beach at sunset. Waves move in the background. The camera tracks the dog from the side."
STORY = (
    "A short cinematic story about a young man walking through a village, meeting an old farmer, helping him "
    "carry vegetables, and returning home at sunset."
)


def chars(plan):
    return {c.id: c for c in plan.characters}


# --- extraction ------------------------------------------------------------------------------


def test_classroom_counts_roles_clothing_and_positions() -> None:
    plan = RulePlanner.plan(CLASSROOM)
    c = chars(plan)
    assert plan.people_count == 11
    assert c["teacher"].count == 1 and c["teacher"].description == "male teacher"
    assert c["teacher"].clothing == "a white shirt and black trousers"
    assert "beside a blackboard" in c["teacher"].position
    assert c["students"].count == 10 and "separate desks" in c["students"].position
    assert plan.environment.location == "classroom" and plan.environment.setting == "indoor"
    assert len(plan.scenes) == 1  # one moment, not a story


def test_forest_weather_time_camera_and_clothing() -> None:
    plan = RulePlanner.plan(FOREST)
    assert chars(plan)["man"].clothing == "a blue jacket"
    env = plan.environment
    assert (env.location, env.weather, env.time_of_day) == ("forest", "snow", "night")
    assert plan.camera.movement == "follows the subject from behind"
    assert "camera" not in {o.name for o in plan.objects}  # "the camera follows" is direction, not a prop


def test_beach_animal_subject_and_side_tracking() -> None:
    plan = RulePlanner.plan(BEACH)
    dog = chars(plan)["retriever"]
    assert dog.kind == "animal" and dog.description == "golden retriever"
    assert plan.people_count is None
    assert plan.camera.movement == "tracks the subject from the side"
    assert plan.environment.time_of_day == "sunset"


def test_story_becomes_ordered_scenes_with_subject() -> None:
    plan = RulePlanner.plan(STORY)
    descriptions = [s.description for s in plan.scenes]
    assert len(descriptions) == 4
    assert descriptions[1] == "young man meeting an old farmer"
    assert descriptions[3] == "young man returning home at sunset"
    assert plan.environment.location == "village"


@pytest.mark.parametrize(
    ("prompt", "absent"),
    [
        (STORY, {"table", "car"}),  # vege-TABLE-s, CAR-ry
        ("A cartoon of many humans in Germany", {"man"}),
        ("A woman eating a mango", {"man"}),
    ],
)
def test_no_substring_false_positives(prompt: str, absent: set[str]) -> None:
    plan = RulePlanner.plan(prompt)
    found = {o.name for o in plan.objects} | set(chars(plan))
    assert not (found & absent)


def test_pronoun_sentences_become_scenes() -> None:
    plan = RulePlanner.plan(
        "A girl wakes up in her bedroom at sunrise. She is wearing pink pajamas. She makes tea in the kitchen. "
        "She walks to a park and sits on a bench. In the evening she reads a book by the window."
    )
    descriptions = [s.description for s in plan.scenes]
    assert descriptions == [
        "A girl wakes up in her bedroom at sunrise",
        "the girl makes tea in the kitchen",
        "the girl walks to a park and sits on a bench",
        "In the evening the girl reads a book by the window",
    ]


def test_descriptive_sentences_stay_one_scene() -> None:
    plan = RulePlanner.plan("A woman stands on a cliff. She is wearing a red coat. She has long hair.")
    assert len(plan.scenes) == 1


def test_sequence_words_split_scenes() -> None:
    clauses = split_clauses("A chef chops onions, then he fries them. Finally the family eats dinner.")
    assert clauses == ["A chef chops onions", "he fries them", "the family eats dinner"]


def test_negations_are_collected() -> None:
    assert negative_terms("A portrait of a woman, no glasses, without jewelry.") == ["glasses", "jewelry"]


# --- validation -------------------------------------------------------------------------------


def test_every_classroom_clause_is_planned_and_reaches_the_model() -> None:
    plan = RulePlanner.plan(CLASSROOM)
    prompt = ", ".join(build_image_prompt_parts(plan, "photorealistic"))
    checked = validate(plan, mode="text-to-image", model_prompt=prompt)
    assert [i.status for i in checked.instructions] == ["included"] * 5
    assert all(i.reaches_model for i in checked.instructions)
    assert checked.model_prompt.startswith(CLASSROOM)  # the user's words are never rewritten or dropped


def test_large_counts_are_reported_as_a_limitation() -> None:
    checked = validate(RulePlanner.plan(CLASSROOM), mode="text-to-image", model_prompt=CLASSROOM)
    assert any("10 students" in note for note in checked.limitations)


def test_image_mode_reports_camera_movement_and_stories() -> None:
    forest = validate(RulePlanner.plan(FOREST), mode="text-to-image", model_prompt=FOREST)
    assert any("Camera movement" in note for note in forest.limitations)
    story = validate(RulePlanner.plan(STORY), mode="text-to-image", model_prompt=STORY)
    assert any("several moments" in note for note in story.limitations)


def test_text_limit_cut_is_reported() -> None:
    plan = RulePlanner.plan(FOREST)
    checked = validate(plan, mode="text-to-image", model_prompt=FOREST, fits=lambda clause: "camera" not in clause)
    cut = [i for i in checked.instructions if not i.reaches_model]
    assert [i.text for i in cut] == ["The camera slowly follows him from behind"]
    # Users are never told to shorten their prompt; the compiler reports per-instruction statuses instead.
    assert not any("Shorten the prompt" in note for note in checked.limitations)


def test_unplanned_clause_is_flagged() -> None:
    plan = RulePlanner.plan("A red kite. Quantum ripples shimmer.")
    checked = validate(plan, mode="text-to-image", model_prompt=plan.original_prompt)
    assert any(i.status == "unsupported" and "Quantum" in i.text for i in checked.instructions)


# --- model prompts ----------------------------------------------------------------------------


def test_image_prompt_keeps_user_words_first_and_restates_counts() -> None:
    parts = build_image_prompt_parts(RulePlanner.plan(CLASSROOM), "photorealistic")
    assert parts[0] == CLASSROOM
    assert parts[1] == "one male teacher, 10 students"


def test_video_prompt_carries_continuity_block() -> None:
    plan = RulePlanner.plan(STORY)
    prompt = build_video_prompt(plan, "cinematic", plan.scenes[1])
    assert prompt.startswith("young man meeting an old farmer.")
    assert "Story context:" not in prompt  # the whole story made the model blend scenes together
    assert "Setting: village" in prompt and "Style: cinematic." in prompt


def test_each_scene_gets_its_own_place_and_time() -> None:
    plan = RulePlanner.plan(
        "A girl wakes up in her bedroom at sunrise. She makes tea in the kitchen. "
        "She walks to a park and sits on a bench. In the evening she reads a book."
    )
    prompts = [build_video_prompt(plan, None, s) for s in plan.scenes]
    assert "Setting: bedroom, sunrise." in prompts[0]
    assert "Setting: kitchen, sunrise." in prompts[1]
    assert "Setting: park, sunrise." in prompts[2]
    assert "Setting: park, evening." in prompts[3]  # no new place named: stays where the story was
    assert all("tea" not in p for p in (prompts[0], prompts[2], prompts[3]))


def test_undescribed_character_in_a_multi_scene_video_is_flagged() -> None:
    from app.services.scene_planner import validate

    plan = RulePlanner.plan("A girl wakes up in her bedroom. She makes tea in the kitchen. She walks to a park.")
    limits = validate(plan, mode="text-to-video", model_prompt="x").limitations
    assert any("'girl'" in l and "different-looking" in l for l in limits)


def test_reworded_scene_clauses_still_count_as_reaching_the_model() -> None:
    from app.services.scene_planner import validate

    plan = RulePlanner.plan("A girl wakes up in her bedroom. She makes tea in the kitchen. She walks to a park.")
    prompt = " | ".join(build_video_prompt(plan, None, s) for s in plan.scenes)
    checked = validate(plan, mode="text-to-video", model_prompt=prompt)
    assert all(i.reaches_model for i in checked.instructions)
    assert not any("text limit" in l for l in checked.limitations)


# --- LLM merge guard rails -----------------------------------------------------------------------


def test_merge_keeps_rule_counts_and_characters() -> None:
    rules = RulePlanner.plan(CLASSROOM)
    llm = {
        "main_subject": "a teacher teaching a class",
        "characters": [{"id": "teacher", "kind": "person", "count": 1, "position": "front of the room"},
                       {"id": "students", "kind": "group", "count": 6, "action": "seated"}],  # miscounted
        "scenes": [{"index": 1, "description": "A teacher at the blackboard facing ten seated students."}],
    }
    merged = merge(rules, llm, "llm:test")
    assert merged.planner == "rules+llm:test"
    assert {c.id: c.count for c in merged.characters}["students"] == 10
    assert merged.people_count == 11


def test_merge_restores_characters_the_llm_dropped() -> None:
    merged = merge(RulePlanner.plan(STORY), {"characters": [{"id": "man", "kind": "person"}]}, "llm:test")
    assert {"man", "farmer"} <= {c.id for c in merged.characters}


def test_merge_ignores_malformed_entries() -> None:
    merged = merge(RulePlanner.plan(BEACH), {"characters": ["not an object", {"kind": "alien"}], "camera": "bad"}, "llm:test")
    assert "retriever" in {c.id for c in merged.characters}
    assert merged.camera.movement == "tracks the subject from the side"


def test_parse_json_tolerates_think_blocks_and_chatter() -> None:
    assert _parse_json('<think>hmm</think>Sure! {"main_subject": "dog"} done') == {"main_subject": "dog"}
    with pytest.raises(ValueError):
        _parse_json("no json here")


def test_wearing_describes_the_subject_and_is_not_a_scene() -> None:
    plan = RulePlanner.plan(
        "An old fisherman with a white beard, wearing a yellow raincoat, pushes his boat into the sea at dawn. "
        "He rows across calm water. He casts a fishing net from the boat."
    )
    assert [s.description for s in plan.scenes] == [
        "An old fisherman with a white beard, wearing a yellow raincoat, pushes his boat into the sea at dawn",
        "the old fisherman rows across calm water",
        "the old fisherman casts a fishing net from the boat",
    ]
    assert chars(plan)["fisherman"].clothing == "a yellow raincoat"
