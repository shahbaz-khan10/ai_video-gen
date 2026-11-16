"""Prompt agent: looks at pictures with Florence-2-base (MIT, 0.23B, ~0.44 GB VRAM) so generation follows the prompt.

1. Image-to-video: describes the uploaded photo (people, clothes, objects, background) and adds that description
   to the video prompt, so the model is told what must stay the same. Measured on the Phase K photos: it named the
   grey background, the crossed arms and the blue shirt, and counted 4 sheep correctly (docs/phase_k/agent).
2. After generation: counts what the prompt asked for (e.g. "three sheep") in the image, or in the first and last
   video frames, and checks that a plain background kept its colour. A failed check is reported on the job and the
   generation is retried once with another seed.

It does not make generation faster: a check costs about 1-3 s on the GPU (7 s on the CPU), and a retry costs a
whole generation. Florence-2 runs on the GPU only when enough VRAM is free, otherwise on the CPU, and is unloaded
after each job so the video model keeps its memory.
"""

from __future__ import annotations

import logging
import re
import threading
from dataclasses import dataclass, field
from typing import Any

from app.core.config import Settings

logger = logging.getLogger(__name__)

MODEL_ID = "florence-community/Florence-2-base"
# Sentences of the caption that describe mood or expression: they would fight the motion the user asks for.
_DROP = re.compile(
    r"\b(mood|appears? to be|seems? to|expression|looking (?:directly )?at the camera|focus is|overall|atmosphere|"
    r"conveys?|suggests?|smil\w*|serious|confident|relaxed|happy|sad)\b",
    re.IGNORECASE,
)
_LEAD = re.compile(r"^(?:the image (?:is|shows)(?: a)?(?: close-up)?(?: portrait)?(?: of)?|this is (?:a|an))\s*", re.IGNORECASE)
BACKGROUND_SHIFT_LIMIT = 40.0  # mean RGB distance (0-441) of the border strip between first and last frame


@dataclass
class Check:
    name: str
    expected: str
    found: str
    passed: bool


@dataclass
class AgentReport:
    description: str | None = None
    checks: list[Check] = field(default_factory=list)
    attempts: int = 1
    notes: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(c.passed for c in self.checks)


class PromptAgent:
    def __init__(self, settings: Settings) -> None:
        self._cache_dir = str(settings.image_model_cache_dir)
        self._lock = threading.Lock()
        self._model: Any = None
        self._processor: Any = None
        self._device = "cpu"

    # --- availability / memory -------------------------------------------------------

    def available(self) -> bool:
        try:
            from huggingface_hub import try_to_load_from_cache
        except ImportError:
            return False
        return isinstance(try_to_load_from_cache(MODEL_ID, "model.safetensors", cache_dir=self._cache_dir), str)

    def _load(self) -> None:
        if self._model is not None:
            return
        import torch
        from transformers import AutoProcessor, Florence2ForConditionalGeneration

        free = torch.cuda.mem_get_info()[0] / 2**30 if torch.cuda.is_available() else 0.0
        self._device = "cuda" if free >= 1.5 else "cpu"
        dtype = torch.float16 if self._device == "cuda" else torch.float32
        hub = {"cache_dir": self._cache_dir, "local_files_only": True}
        self._processor = AutoProcessor.from_pretrained(MODEL_ID, **hub)
        self._model = Florence2ForConditionalGeneration.from_pretrained(MODEL_ID, torch_dtype=dtype, **hub).to(self._device).eval()

    def unload(self) -> None:
        with self._lock:
            if self._model is None:
                return
            self._model = None
            self._processor = None
            from app.services import memory

            memory.release()

    def _run(self, task: str, image: Any, text: str = "") -> Any:
        import torch

        with self._lock:
            self._load()
            dtype = torch.float16 if self._device == "cuda" else torch.float32
            inputs = self._processor(text=task + text, images=image.convert("RGB"), return_tensors="pt").to(self._device, dtype)
            with torch.inference_mode():
                ids = self._model.generate(**inputs, max_new_tokens=256, num_beams=3, do_sample=False)
            raw = self._processor.batch_decode(ids, skip_special_tokens=False)[0]
            return self._processor.post_process_generation(raw, task=task, image_size=image.size)[task]

    # --- understanding -----------------------------------------------------------------

    def subjects(self, image: Any) -> dict[str, int]:
        """People and animals Florence-2 detects, e.g. {'person': 1} or {'sheep': 4}."""
        result = self._run("<OD>", image)
        counts: dict[str, int] = {}
        for label in (result.get("labels", []) if isinstance(result, dict) else []):
            label = str(label).lower()
            words = label.split()
            # Whole words only: "human beard" must not count as a bear.
            key = "person" if any(label == p or label.endswith(" " + p) for p in PERSON_LABELS) else next(
                (an for an in ANIMALS if an in words or an + "s" in words), None
            )
            if key:
                counts[key] = counts.get(key, 0) + 1
        return counts

    def describe(self, image: Any) -> str:
        """What is in the picture, without mood or facial expression (those would fight the motion prompt)."""
        caption = str(self._run("<MORE_DETAILED_CAPTION>", image))
        return clean_caption(caption)

    def count(self, image: Any, phrase: str) -> int:
        """How many ``phrase`` objects Florence-2 detects. Object detection (<OD>) is used: on video frames phrase
        grounding merged all sheep into one box, while <OD> counted 4 on the photo and 4 -> 3 on the 5 s video
        where sheep had merged. On generated images it labelled sheep "animal" and added one box around a whole
        group of dogs; both are handled (docs/phase_k/agent)."""
        result = self._run("<OD>", image)
        if not isinstance(result, dict):
            return 0
        boxes = [b for b, label in zip(result.get("bboxes", []), result.get("labels", []))
                 if label_matches(str(label).lower(), phrase)]
        return len(_drop_group_boxes(_dedupe(boxes)))

    def subjects(self, image: Any) -> dict[str, int]:
        """People and animals Florence-2 detects, e.g. {'person': 1} or {'sheep': 4}."""
        result = self._run("<OD>", image)
        counts: dict[str, int] = {}
        for label in (result.get("labels", []) if isinstance(result, dict) else []):
            label = str(label).lower()
            words = label.split()
            # Whole words only: "human beard" must not count as a bear.
            key = "person" if any(label == p or label.endswith(" " + p) for p in PERSON_LABELS) else next(
                (an for an in ANIMALS if an in words or an + "s" in words), None
            )
            if key:
                counts[key] = counts.get(key, 0) + 1
        return counts

    def describe(self, image: Any) -> str:
        """What is in the picture, without mood or facial expression (those would fight the motion prompt)."""
        caption = str(self._run("<MORE_DETAILED_CAPTION>", image))
        return clean_caption(caption)

def clean_caption(caption: str) -> str:
    sentences = re.split(r"(?<=[.!?])\s+", caption.strip())
    kept = [s for s in sentences if s and not _DROP.search(s)]
    if kept:
        kept[0] = _LEAD.sub("", kept[0])
        kept[0] = kept[0][:1].upper() + kept[0][1:]
    return " ".join(kept).strip()


PEOPLE_WORDS = {"people", "person", "persons", "men", "man", "women", "woman", "children", "child", "kids", "kid", "boys",
                "boy", "girls", "girl", "friends", "students", "players", "workers", "family"}
PERSON_LABELS = ("man", "woman", "person", "boy", "girl", "child")


def label_matches(label: str, phrase: str) -> bool:
    words = phrase.lower().split()
    if any(w in PEOPLE_WORDS for w in words):
        return any(label == p or label.endswith(" " + p) for p in PERSON_LABELS)
    if label == "animal" and any(w in ANIMALS or w.rstrip("s") in ANIMALS for w in words):
        return True  # Florence-2 often labels farm animals just "animal"
    noun = words[-1] if words else phrase
    stem = noun[:-1] if noun.endswith("s") and not noun.endswith("ss") else noun
    return stem in label.split() or stem + "s" in label.split()


def _dedupe(boxes: list[list[float]], iou_limit: float = 0.6) -> list[list[float]]:
    """Grounding sometimes returns the same object twice; overlapping boxes count once."""
    kept: list[list[float]] = []
    for b in boxes:
        if all(_iou(b, k) < iou_limit for k in kept):
            kept.append(b)
    return kept


def _contains(outer: list[float], inner: list[float], slack: float = 0.9) -> bool:
    x1, y1 = max(outer[0], inner[0]), max(outer[1], inner[1])
    x2, y2 = min(outer[2], inner[2]), min(outer[3], inner[3])
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    area = (inner[2] - inner[0]) * (inner[3] - inner[1])
    return area > 0 and inter / area >= slack


def _drop_group_boxes(boxes: list[list[float]]) -> list[list[float]]:
    """A box that contains two or more other boxes is a box around the group, not one more object."""
    return [b for b in boxes if sum(1 for o in boxes if o is not b and _contains(b, o)) < 2]


def _iou(a: list[float], b: list[float]) -> float:
    x1, y1, x2, y2 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def border_colour(image: Any) -> tuple[float, float, float, float]:
    """Mean RGB of the top strip and the upper side strips (not the bottom, where the subject usually is), plus
    its spread: a low spread means a plain background."""
    import numpy as np

    a = np.asarray(image.convert("RGB"), dtype=np.float32)
    h, w = a.shape[:2]
    m = max(2, int(min(h, w) * 0.06))
    upper = int(h * 0.6)
    strip = np.concatenate([a[:m].reshape(-1, 3), a[:upper, :m].reshape(-1, 3), a[:upper, -m:].reshape(-1, 3)])
    mean = strip.mean(axis=0)
    return float(mean[0]), float(mean[1]), float(mean[2]), float(strip.std(axis=0).mean())


PLAIN_SPREAD = 22.0
ANIMALS = ("sheep", "dog", "cat", "cow", "horse", "goat", "bird", "duck", "chicken", "deer", "elephant", "lion",
           "tiger", "bear", "rabbit", "wolf", "fox", "camel", "zebra", "giraffe", "monkey", "fish")


def colour_name(rgb: tuple[float, float, float]) -> str:
    r, g, b = rgb
    lightness = (max(rgb) + min(rgb)) / 2
    if max(rgb) - min(rgb) < 25:
        return "white" if lightness > 225 else "light grey" if lightness > 160 else "grey" if lightness > 90 else "dark grey" if lightness > 40 else "black"
    hue = {"red": r, "green": g, "blue": b}
    main = max(hue, key=hue.get)
    if r > 150 and g > 150 and b < 120:
        return "yellow"
    return f"{'light ' if lightness > 170 else 'dark ' if lightness < 70 else ''}{main}"


def colour_distance(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    return float(sum((x - y) ** 2 for x, y in zip(a[:3], b[:3])) ** 0.5)


def count_targets(plan: Any) -> list[tuple[str, int]]:
    """(phrase, expected count) for every character with an explicit count of 2 or more, e.g. ('sheep', 3)."""
    targets = []
    for c in getattr(plan, "characters", None) or []:
        if c.count and 2 <= c.count <= 12:
            phrase = c.id.replace("_group", "").replace("_", " ")
            targets.append((phrase, int(c.count)))
    return targets
