"""Prompt agent: caption cleaning, matching, colour checks, and the check-and-retry flow (with a fake agent; the real
Florence-2 model is measured in docs/phase_k/agent)."""

from __future__ import annotations

import io
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.core.config import Settings
from app.main import create_app
from app.services import prompt_agent as pa
from tests.conftest import wait_for_status
from tests.fakes import FakeImageEngine, FakeVideoEngine

CREATE = "/api/v1/generations"


def test_clean_caption_keeps_appearance_and_drops_mood() -> None:
    caption = (
        "The image is a portrait of a young man with a beard. He is wearing a blue long-sleeved t-shirt. "
        "He has a slight smile on his face and is looking directly at the camera. The background is a plain grey color. "
        "The man appears to be confident and relaxed."
    )
    assert pa.clean_caption(caption) == (
        "A young man with a beard. He is wearing a blue long-sleeved t-shirt. The background is a plain grey color."
    )


@pytest.mark.parametrize(
    ("label", "phrase", "ok"),
    [("sheep", "sheep", True), ("man", "children", True), ("woman", "people", True), ("human face", "people", False),
     ("dog", "dogs", True), ("dog", "sheep", False), ("green vegetables", "sheep", False),
     ("human beard", "bear", False)],
)
def test_label_matches(label: str, phrase: str, ok: bool) -> None:
    assert pa.label_matches(label, phrase) is ok


def test_colour_names_and_plain_background() -> None:
    assert pa.colour_name((200, 200, 202)) == "light grey"
    assert pa.colour_name((40, 160, 60)) == "green"
    grey = Image.new("RGB", (400, 400), (200, 200, 200))
    r, g, b, spread = pa.border_colour(grey)
    assert spread < pa.PLAIN_SPREAD and pa.colour_name((r, g, b)) == "light grey"
    green = Image.new("RGB", (400, 400), (40, 160, 60))
    assert pa.colour_distance(pa.border_colour(grey), pa.border_colour(green)) > pa.BACKGROUND_SHIFT_LIMIT


def test_count_targets_from_plan() -> None:
    from app.schemas.scene_plan import Character, ScenePlan

    plan = ScenePlan(original_prompt="x", planner="rules", characters=[
        Character(id="sheep", kind="animal", count=3), Character(id="children", kind="group", count=2),
        Character(id="teacher", count=1), Character(id="crowd", kind="group", count=None),
    ])
    assert pa.count_targets(plan) == [("sheep", 3), ("children", 2)]


class FakeAgent:
    """Answers counts from a script: one answer per call, in order."""

    def __init__(self, counts: list[int], subjects: dict[str, int] | None = None) -> None:
        self.counts = list(counts)
        self._subjects = subjects or {}
        self.unloads = 0

    def available(self) -> bool:
        return True

    def count(self, image, phrase: str) -> int:
        return self.counts.pop(0)

    def subjects(self, image) -> dict[str, int]:
        return dict(self._subjects)

    def describe(self, image) -> str:
        return "A man in a blue shirt. The background is a plain grey color."

    def unload(self) -> None:
        self.unloads += 1


@pytest.fixture
def video_engine() -> FakeVideoEngine:
    return FakeVideoEngine()


@pytest.fixture
def vclient(settings: Settings, engine: FakeImageEngine, video_engine: FakeVideoEngine) -> Iterator[TestClient]:
    with TestClient(create_app(settings, engine=engine, video_engine=video_engine)) as test_client:
        yield test_client


def test_image_retried_once_when_count_is_wrong(vclient: TestClient, engine: FakeImageEngine) -> None:
    vclient.app.state.generation_service.agent = FakeAgent([2, 3])  # first image: 2 sheep, retry: 3
    res = vclient.post(CREATE, json={"mode": "text-to-image", "prompt": "Three white sheep in a meadow", "seed": 10})
    job = wait_for_status(vclient, res.json()["id"], {"completed", "failed"})
    assert job["status"] == "completed", job
    agent = job["agent"]
    assert agent["attempts"] == 2 and agent["checks"][0] == {"name": "count of sheep", "expected": "3", "found": "3", "passed": True}
    assert job["settings"]["seed"] == 11  # the shown image's seed, so it can be reproduced


def test_image_not_retried_when_checks_pass(vclient: TestClient) -> None:
    vclient.app.state.generation_service.agent = FakeAgent([3])
    res = vclient.post(CREATE, json={"mode": "text-to-image", "prompt": "Three white sheep in a meadow"})
    job = wait_for_status(vclient, res.json()["id"], {"completed", "failed"})
    assert job["agent"]["attempts"] == 1 and job["agent"]["checks"][0]["passed"]


def test_agent_can_be_turned_off(vclient: TestClient) -> None:
    fake = FakeAgent([])
    vclient.app.state.generation_service.agent = fake
    res = vclient.post(CREATE, json={"mode": "text-to-image", "prompt": "Three white sheep", "prompt_agent": False})
    job = wait_for_status(vclient, res.json()["id"], {"completed", "failed"})
    assert job["status"] == "completed" and job["agent"] is None


def test_i2v_prompt_gets_photo_description_and_video_is_checked(vclient: TestClient, video_engine: FakeVideoEngine) -> None:
    # The fake video's frames change brightness, so the background check fails and the agent retries once.
    vclient.app.state.generation_service.agent = FakeAgent([1, 1], subjects={"person": 1})
    buf = io.BytesIO()
    Image.new("RGB", (640, 640), (200, 200, 200)).save(buf, format="PNG")
    uid = vclient.post("/api/v1/uploads/images", content=buf.getvalue(), headers={"Content-Type": "image/png"}).json()["upload_id"]
    res = vclient.post(CREATE, json={"mode": "image-to-video", "prompt": "He smiles", "aspect_ratio": "1:1",
                                     "source_image": {"upload_id": uid}})
    job = wait_for_status(vclient, res.json()["id"], {"completed", "failed"})
    assert job["status"] == "completed", job
    prompt = video_engine.calls[0].prompt
    assert "The scene: A man in a blue shirt." in prompt and "Plain light grey background" in prompt
    assert job["plan"]["model_prompt"] == prompt
    names = {c["name"]: c["passed"] for c in job["agent"]["checks"]}
    assert names == {"person at the end": True, "background colour": False}
    assert job["agent"]["attempts"] == 2 and len(video_engine.calls) == 2
    assert video_engine.calls[1].seed == video_engine.calls[0].seed + 1
    assert "not better" in job["agent"]["notes"][-1]
    assert job["agent"]["description"].startswith("A man")


def test_group_box_and_generic_animal_label() -> None:
    dogs = [[0, 0, 1000, 300], [10, 10, 200, 290], [210, 10, 400, 290], [410, 10, 600, 290], [610, 10, 800, 290]]
    assert len(pa._drop_group_boxes(dogs)) == 4
    assert pa.label_matches("animal", "sheep") and not pa.label_matches("animal", "children")
