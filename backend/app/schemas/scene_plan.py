"""Structured scene specification produced from a user's prompt.

The plan never replaces the user's words: ``original_prompt`` is kept verbatim, every clause of it is
listed in ``instructions`` with how it is covered, and anything a model cannot do is listed in
``limitations`` instead of being silently dropped.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Character(BaseModel):
    id: str = Field(description="Stable label, e.g. 'teacher' or 'student_group'.")
    kind: Literal["person", "group", "animal", "creature"] = "person"
    count: int | None = Field(None, ge=1, le=500, description="How many, when the prompt says so.")
    description: str = ""
    age: str | None = None
    clothing: str | None = None
    position: str | None = None
    action: str | None = None


class SceneObject(BaseModel):
    name: str
    position: str | None = None


class Environment(BaseModel):
    location: str | None = None
    setting: Literal["indoor", "outdoor"] | None = None
    background: list[str] = []
    weather: str | None = None
    time_of_day: str | None = None
    lighting: str | None = None


class Camera(BaseModel):
    shot_type: str | None = None
    angle: str | None = None
    movement: str | None = None


class SceneBeat(BaseModel):
    """One scene of a story. Long videos are generated scene by scene."""

    index: int = Field(ge=1)
    description: str = Field(min_length=1, max_length=600)
    characters: list[str] = Field(default_factory=list, description="Character ids present in this scene.")
    action: str | None = None
    camera: str | None = None
    duration_seconds: float | None = Field(None, ge=1, le=120)


class Instruction(BaseModel):
    """One clause of the user's prompt and where it went."""

    text: str
    covered_by: list[str] = Field(default_factory=list, description="Plan fields that represent this clause.")
    reaches_model: bool = Field(True, description="False if the model's text limit cuts this clause off.")
    status: Literal["planned", "partial", "unplanned"] = "planned"


class ScenePlan(BaseModel):
    original_prompt: str
    planner: str = Field(description="'rules' or 'rules+llm:<model>'.")
    main_subject: str | None = None
    people_count: int | None = Field(None, description="Total people asked for, when stated.")
    characters: list[Character] = []
    objects: list[SceneObject] = []
    environment: Environment = Environment()
    camera: Camera = Camera()
    style: str | None = None
    scenes: list[SceneBeat] = []
    instructions: list[Instruction] = []
    limitations: list[str] = Field(default_factory=list, description="Requests the current models cannot honour reliably.")
    model_prompt: str | None = Field(None, description="Exactly what the generation model receives.")
