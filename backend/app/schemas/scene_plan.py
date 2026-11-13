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
    description: str = Field(min_length=1, max_length=4000)
    characters: list[str] = Field(default_factory=list, description="Character ids present in this scene.")
    action: str | None = None
    camera: str | None = None
    duration_seconds: float | None = Field(None, ge=1, le=120)


InstructionStatus = Literal["included", "compressed", "unsupported", "omitted_budget"]


class Instruction(BaseModel):
    """One instruction (sentence or line) of the user's prompt and what happened to it.

    included        understood and present in the prompt(s) sent to the model
    compressed      understood; sent in shortened form (to fit the token budget, or without unrenderable words)
    unsupported     understood but not something the models can show (a title, a moral, spoken words)
    omitted_budget  not sent because it did not fit the model's token budget
    """

    text: str
    covered_by: list[str] = Field(default_factory=list, description="Plan fields that represent this instruction.")
    reaches_model: bool = Field(True, description="True when the instruction is in at least one model prompt.")
    status: InstructionStatus = "included"
    note: str | None = Field(None, description="Why this status, in plain words.")
    targets: list[str] = Field(default_factory=list, description="Compiled prompts that contain it, e.g. 'scene 2'.")


class PromptComponent(BaseModel):
    name: str = Field(description="action, characters, setting, camera, lighting, style or continuity")
    status: Literal["included", "compressed", "omitted"]
    text: str = Field(description="What was sent ('' when omitted).")
    full_text: str = Field(description="The component before compression.")


class CompiledPrompt(BaseModel):
    """The exact prompt one model call receives, measured with that model's tokenizer."""

    target: str = Field(description="'image', 'video' or 'scene N'.")
    model: str = Field(description="Tokenizer used for the budget, e.g. 'umt5 (Wan2.1)' or 'clip (RealVisXL)'.")
    text: str
    tokens: int
    budget: int
    measured: bool = Field(description="True when counted with the model's real tokenizer.")
    components: list[PromptComponent] = []


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
    compiled: list[CompiledPrompt] = Field(default_factory=list, description="One entry per model call (per scene for long videos).")
