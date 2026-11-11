"""Comprehensive Photorealistic Image Generation Test Suite.

Tests the 8 required photographic benchmark scenarios:
  1. A single realistic human portrait.
  2. A full-body human photograph.
  3. Five people in a modern office.
  4. Ten people in a public park.
  5. A realistic street environment.
  6. A person riding a bicycle in a city.
  7. A family photograph with different people.
  8. A detailed indoor restaurant scene.

Evaluates prompt adherence, person count detection, anatomical prompt optimization,
environment preservation, camera optics injection, and negative prompt formulation.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.schemas.generation import AspectRatio, ImageResolution, VisualStyle
from app.services.prompt_understanding import PromptUnderstandingEngine, ShotType
from tests.fakes import FakeImageEngine


BENCHMARK_PROMPTS = {
    "test_1_portrait": (
        "A close-up portrait of a 32-year-old architect with hazel eyes and subtle freckles, "
        "smiling gently, warm studio softbox lighting, shallow depth of field, 85mm lens"
    ),
    "test_2_full_body": (
        "Full-body photograph of a woman standing in a contemporary art gallery, "
        "wearing a navy blue linen suit and white sneakers, feet visible, natural gallery lighting"
    ),
    "test_3_five_people_office": (
        "Generate a realistic photograph of five people standing in a modern office. "
        "Two people are sitting at a table, one person is presenting a laptop, and two people are "
        "discussing a project near a window. Everyone wears different professional clothes. Natural daylight."
    ),
    "test_4_ten_people_park": (
        "Ten people relaxing and talking in a public city park on a sunny afternoon, "
        "sitting on the green grass under shade trees, casual weekend clothing, distant city skyline"
    ),
    "test_5_street_environment": (
        "Realistic street photograph of a rainy cobblestone avenue in autumn, wet pavement reflections, "
        "historic brick townhouses, fallen maple leaves, moody overcast ambient daylight"
    ),
    "test_6_bicycle_city": (
        "A young man in a beige trench coat riding a vintage bicycle down an urban avenue, "
        "morning golden hour sun, motion blur in background, sharp focus on rider and handlebars"
    ),
    "test_7_family": (
        "A candid family photograph of parents and their two young children sitting on their front porch, "
        "laughing naturally, casual cotton clothes, soft afternoon sunlight, natural home environment"
    ),
    "test_8_indoor_restaurant": (
        "Detailed indoor restaurant scene during dinner service, rustic wooden dining tables with wine glasses "
        "and artisan plates, cozy warm candle lighting, exposed brick walls, waiters in the background"
    ),
}


def test_scenario_1_single_human_portrait() -> None:
    prompt = BENCHMARK_PROMPTS["test_1_portrait"]
    plan = PromptUnderstandingEngine.plan_scene(prompt, VisualStyle.PORTRAIT)

    assert plan.people_count == 1
    assert plan.camera_shot in (ShotType.PORTRAIT, ShotType.EXTREME_CLOSE_UP)
    assert "freckles" in plan.optimized_positive_prompt
    assert "85mm" in plan.optimized_positive_prompt
    # Negative prompt must guard against plastic/airbrushed faces and deformed eyes
    assert "plastic skin" in plan.negative_prompt
    assert "distorted eyes" in plan.negative_prompt
    assert "bad anatomy" in plan.negative_prompt


def test_scenario_2_full_body_photograph() -> None:
    prompt = BENCHMARK_PROMPTS["test_2_full_body"]
    plan = PromptUnderstandingEngine.plan_scene(prompt, VisualStyle.PHOTOREALISTIC)

    assert plan.people_count == 1
    assert plan.camera_shot == ShotType.FULL_BODY
    assert "full-body" in plan.optimized_positive_prompt
    assert "navy blue linen suit" in plan.optimized_positive_prompt
    assert "feet visible" in plan.optimized_positive_prompt
    # Negative prompt must guard against missing/floating limbs
    assert "extra limbs" in plan.negative_prompt
    assert "missing legs" in plan.negative_prompt


def test_scenario_3_five_people_office() -> None:
    prompt = BENCHMARK_PROMPTS["test_3_five_people_office"]
    plan = PromptUnderstandingEngine.plan_scene(prompt, VisualStyle.GROUP_PHOTO)

    assert plan.people_count == 5
    assert plan.scene_category == "indoor"
    assert "office" in plan.environment_details.lower()
    assert plan.camera_shot == ShotType.GROUP_SHOT
    # Multi-person instructions must be preserved
    assert "five people" in plan.optimized_positive_prompt or "5 people" in plan.optimized_positive_prompt
    assert "laptop" in plan.key_objects
    assert "table" in plan.key_objects
    assert "window" in plan.key_objects
    # Anti-cloning and anti-merging negative tokens
    assert "identical faces" in plan.negative_prompt
    assert "merged people" in plan.negative_prompt
    assert "cloned face" in plan.negative_prompt


def test_scenario_4_ten_people_public_park() -> None:
    prompt = BENCHMARK_PROMPTS["test_4_ten_people_park"]
    plan = PromptUnderstandingEngine.plan_scene(prompt, VisualStyle.GROUP_PHOTO)

    assert plan.people_count == 10
    assert plan.scene_category == "outdoor"
    assert "park" in plan.environment_details.lower()
    assert "wide" in plan.composition.lower()
    assert "grass" in plan.optimized_positive_prompt
    assert "trees" in plan.optimized_positive_prompt


def test_scenario_5_street_environment() -> None:
    prompt = BENCHMARK_PROMPTS["test_5_street_environment"]
    plan = PromptUnderstandingEngine.plan_scene(prompt, VisualStyle.STREET)

    assert plan.scene_category == "outdoor"
    assert "street" in plan.environment_details.lower()
    assert "cobblestone" in plan.optimized_positive_prompt
    assert "rainy" in plan.optimized_positive_prompt or "wet pavement" in plan.optimized_positive_prompt


def test_scenario_6_bicycle_city() -> None:
    prompt = BENCHMARK_PROMPTS["test_6_bicycle_city"]
    plan = PromptUnderstandingEngine.plan_scene(prompt, VisualStyle.PHOTOREALISTIC)

    assert plan.people_count == 1
    assert "bicycle" in plan.key_objects
    assert "riding" in plan.optimized_positive_prompt
    assert "golden hour" in plan.optimized_positive_prompt


def test_scenario_7_family_photograph() -> None:
    prompt = BENCHMARK_PROMPTS["test_7_family"]
    plan = PromptUnderstandingEngine.plan_scene(prompt, VisualStyle.PORTRAIT)

    assert plan.people_count >= 2
    assert "family" in plan.optimized_positive_prompt
    assert "candid" in plan.optimized_positive_prompt
    assert "cloned face" in plan.negative_prompt


def test_scenario_8_indoor_restaurant() -> None:
    prompt = BENCHMARK_PROMPTS["test_8_indoor_restaurant"]
    plan = PromptUnderstandingEngine.plan_scene(prompt, VisualStyle.PHOTOREALISTIC)

    assert plan.scene_category == "indoor"
    assert "restaurant" in plan.environment_details.lower()
    assert "candle" in plan.optimized_positive_prompt or "warm" in plan.optimized_positive_prompt
    assert "table" in plan.key_objects


def test_api_plan_endpoint_benchmark(settings: Settings) -> None:
    """Verifies that the /api/v1/generations/plan endpoint successfully structures benchmarks."""
    fake_engine = FakeImageEngine()
    app = create_app(settings, engine=fake_engine)

    with TestClient(app) as client:
        for name, prompt_text in BENCHMARK_PROMPTS.items():
            res = client.post(
                "/api/v1/generations/plan",
                json={
                    "mode": "text-to-image",
                    "prompt": prompt_text,
                    "style": "photorealistic",
                },
            )
            assert res.status_code == 200, f"Failed on {name}: {res.text}"
            data = res.json()
            assert "scene" in data
            assert "people" in data
            assert "composition" in data
            assert "prompts" in data
            assert len(data["prompts"]["positive"]) > len(prompt_text)
            assert len(data["prompts"]["negative"]) > 50


def test_api_full_generation_with_photorealism_payload(settings: Settings) -> None:
    """Tests creating and processing an image job with negative prompt, steps and resolution."""
    fake_engine = FakeImageEngine()
    app = create_app(settings, engine=fake_engine)

    with TestClient(app) as client:
        res = client.post(
            "/api/v1/generations",
            json={
                "mode": "text-to-image",
                "prompt": BENCHMARK_PROMPTS["test_3_five_people_office"],
                "aspect_ratio": "16:9",
                "style": "group-photo",
                "resolution": "large",
                "steps": 25,
                "negative_prompt": "oversaturated, glowing edges",
                "guidance_scale": 7.0,
                "seed": 42,
            },
        )
        assert res.status_code == 202
        job_id = res.json()["id"]

        job_res = client.get(f"/api/v1/generations/{job_id}")
        assert job_res.status_code == 200
        job_data = job_res.json()
        assert job_data["settings"]["steps"] == 25
        assert job_data["settings"]["negative_prompt"] == "oversaturated, glowing edges"
        assert job_data["settings"]["guidance_scale"] == 7.0
        assert job_data["settings"]["seed"] == 42

