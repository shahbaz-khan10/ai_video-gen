"""Optional language-model layer for scene planning (Qwen3-1.7B, Apache-2.0, runs on the CPU).

It reads the prompt like a person would (who is doing what, where, with which camera, in which order) and
returns JSON that is merged into the rule plan. Guard rails:
  * explicit numbers found by the rule layer always win (small LLMs miscount);
  * characters the rules found are never dropped;
  * any failure, missing weights or slow answer falls back to the rule plan and says so in ``planner``.
"""

from __future__ import annotations

import importlib.util
import json
import logging
import re
import threading
import time
from typing import Any

from pydantic import ValidationError

from app.schemas.scene_plan import Camera, Character, Environment, SceneBeat, SceneObject, ScenePlan

logger = logging.getLogger(__name__)

DEFAULT_MODEL_ID = "Qwen/Qwen3-1.7B"

SYSTEM = """You are a film pre-production assistant. Turn the user's description into a JSON scene specification.
Rules:
- Use only what the user wrote or clearly implies. Never invent extra characters, places or events.
- Keep every concrete detail: counts, clothing, colours, positions (front/back/left/right/beside), actions,
  weather, time of day, lighting, camera angle and movement.
- "characters" are people or animals. Use one entry per distinct role; a group of identical people is one
  entry with "count".
- "scenes": for a single moment use exactly one scene. For a story, split it into the events in order.
  Each scene "description" must be a complete, self-contained visual sentence that names the characters
  with their appearance (not "he" or "him") and the place.
Reply with JSON only, no commentary."""

SCHEMA_HINT = """{
  "main_subject": "string",
  "characters": [{"id": "short_label", "kind": "person|group|animal", "count": 1, "description": "string",
                   "age": "string or null", "clothing": "string or null", "position": "string or null",
                   "action": "string or null"}],
  "objects": [{"name": "string", "position": "string or null"}],
  "environment": {"location": "string or null", "setting": "indoor|outdoor|null", "background": ["string"],
                  "weather": "string or null", "time_of_day": "string or null", "lighting": "string or null"},
  "camera": {"shot_type": "string or null", "angle": "string or null", "movement": "string or null"},
  "scenes": [{"index": 1, "description": "string", "characters": ["short_label"], "action": "string or null",
              "camera": "string or null"}]
}"""


class LLMPlanner:
    def __init__(self, model_id: str = DEFAULT_MODEL_ID, cache_dir: str | None = None, timeout_s: float = 180.0) -> None:
        self.model_id = model_id
        self.cache_dir = cache_dir
        self.timeout_s = timeout_s
        self._lock = threading.Lock()
        self._model: Any = None
        self._tokenizer: Any = None

    @property
    def name(self) -> str:
        return f"llm:{self.model_id.split('/')[-1]}"

    def available(self) -> bool:
        if importlib.util.find_spec("transformers") is None or importlib.util.find_spec("huggingface_hub") is None:
            return False
        from huggingface_hub import try_to_load_from_cache

        found = try_to_load_from_cache(self.model_id, "config.json", cache_dir=self.cache_dir)
        return isinstance(found, str)

    def _load(self) -> None:
        if self._model is not None:
            return
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        hub = {"cache_dir": self.cache_dir, "local_files_only": True}
        self._tokenizer = AutoTokenizer.from_pretrained(self.model_id, **hub)
        # bfloat16 halves RAM (~3.4 GB); recent CPUs (AVX-512 BF16, e.g. Zen 4) run it natively.
        self._model = AutoModelForCausalLM.from_pretrained(self.model_id, dtype=torch.bfloat16, **hub)
        self._model.eval()

    def unload(self) -> None:
        with self._lock:
            self._model = None
            self._tokenizer = None

    def raw_plan(self, prompt: str, mode: str, duration_seconds: float | None, rule_plan: ScenePlan) -> dict:
        """Returns the model's parsed JSON. Raises on failure (callers fall back to the rule plan)."""
        import torch

        with self._lock:
            self._load()
            task = f"Mode: {mode}."
            if mode == "text-to-video" and duration_seconds and duration_seconds > 5:
                suggested = max(1, min(8, round(duration_seconds / 15)))
                task += f" Target length: {int(duration_seconds)} seconds, so plan about {suggested} scene(s) in story order."
            hints = rule_plan.model_dump(include={"people_count", "characters", "environment", "camera"}, exclude_none=True)
            user = (
                f"{task}\nDescription: {prompt}\n\nFacts already extracted by rules (keep them, fix them only if "
                f"clearly wrong):\n{json.dumps(hints)}\n\nJSON schema:\n{SCHEMA_HINT}"
            )
            messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]
            text = self._tokenizer.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True, enable_thinking=False
            )
            inputs = self._tokenizer(text, return_tensors="pt")
            started = time.monotonic()
            deadline = started + self.timeout_s

            from transformers import StoppingCriteria, StoppingCriteriaList

            class _Deadline(StoppingCriteria):
                def __call__(self, *_args, **_kwargs) -> bool:
                    return time.monotonic() > deadline

            with torch.inference_mode():
                output = self._model.generate(
                    **inputs,
                    max_new_tokens=900,
                    do_sample=False,
                    stopping_criteria=StoppingCriteriaList([_Deadline()]),
                )
            reply = self._tokenizer.decode(output[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)
            logger.info("LLM planner answered in %.1fs (%d tokens)", time.monotonic() - started, output.shape[1] - inputs["input_ids"].shape[1])
        return _parse_json(reply)


def _parse_json(reply: str) -> dict:
    reply = re.sub(r"<think>.*?</think>", "", reply, flags=re.DOTALL)
    start, end = reply.find("{"), reply.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("no JSON object in the model reply")
    return json.loads(reply[start : end + 1])


def merge(rule_plan: ScenePlan, data: dict, planner_name: str) -> ScenePlan:
    """LLM fields fill in language understanding; rule-extracted numbers and characters are never lost."""
    def _clean(items: list, model: type) -> list:
        cleaned = []
        for item in items or []:
            if isinstance(item, dict):
                try:
                    cleaned.append(model.model_validate({k: v for k, v in item.items() if v not in ("", None)}))
                except ValidationError:
                    continue
        return cleaned

    characters = _clean(data.get("characters"), Character)
    rule_by_id = {c.id.rstrip("s"): c for c in rule_plan.characters}
    for c in characters:
        rule = rule_by_id.get(c.id.rstrip("s"))
        if rule and rule.count:
            c.count = rule.count  # explicit numbers from the prompt beat the model's guess
    have = {c.id.rstrip("s") for c in characters}
    characters += [c for key, c in rule_by_id.items() if key not in have]

    env_data = data.get("environment") if isinstance(data.get("environment"), dict) else {}
    try:
        environment = Environment.model_validate({k: v for k, v in env_data.items() if v not in ("", None)})
    except ValidationError:
        environment = rule_plan.environment
    rule_env = rule_plan.environment.model_dump(exclude_none=True)
    environment = environment.model_copy(update={k: v for k, v in rule_env.items() if not getattr(environment, k)})

    cam_data = data.get("camera") if isinstance(data.get("camera"), dict) else {}
    try:
        camera = Camera.model_validate({k: v for k, v in cam_data.items() if v not in ("", None)})
    except ValidationError:
        camera = rule_plan.camera
    camera = camera.model_copy(update={k: v for k, v in rule_plan.camera.model_dump(exclude_none=True).items() if not getattr(camera, k)})

    scenes = _clean(data.get("scenes"), SceneBeat)
    # Measured: Qwen3-1.7B merged a 4-event story into one scene. Never accept fewer scenes than the rules found.
    if len(scenes) < len(rule_plan.scenes):
        scenes = rule_plan.scenes
    scenes = [s.model_copy(update={"index": i + 1}) for i, s in enumerate(scenes)]
    people = sum(c.count or 1 for c in characters if c.kind in ("person", "group")) or rule_plan.people_count
    if rule_plan.people_count:
        people = rule_plan.people_count

    return rule_plan.model_copy(
        update={
            "planner": f"rules+{planner_name}",
            "main_subject": data.get("main_subject") or rule_plan.main_subject,
            "people_count": people,
            "characters": characters,
            "objects": _clean(data.get("objects"), SceneObject) or rule_plan.objects,
            "environment": environment,
            "camera": camera,
            "scenes": scenes,
        }
    )
