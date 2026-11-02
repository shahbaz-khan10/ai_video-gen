"""Intelligent Prompt Understanding and Scene Planning Engine.

Converts natural-language prompts into a structured scene breakdown and generates
optimized, model-specific positive and negative prompts for professional photorealism.
Ensures zero silently dropped instructions, handles multi-person counts, anatomical anchors,
and camera/lighting/environment conditioning.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from app.schemas.generation import VisualStyle


class ShotType(StrEnum):
    EXTREME_CLOSE_UP = "macro extreme close-up"
    PORTRAIT = "intimate head and shoulders portrait"
    MEDIUM_SHOT = "medium shot from waist up"
    FULL_BODY = "full-body shot with feet visible"
    WIDE_SHOT = "wide-angle establishing environmental photograph"
    GROUP_SHOT = "wide-angle group photography shot"


@dataclass
class PersonDescription:
    index: int
    gender: str | None = None
    age_group: str | None = None
    clothing: str | None = None
    position: str | None = None
    activity: str | None = None
    raw_mention: str = ""

    def to_prompt_fragment(self) -> str:
        parts = []
        if self.age_group and self.gender:
            parts.append(f"{self.age_group} {self.gender}")
        elif self.gender:
            parts.append(self.gender)
        elif self.age_group:
            parts.append(f"{self.age_group} person")
        else:
            parts.append("person")

        if self.position:
            parts.append(self.position)
        if self.activity:
            parts.append(self.activity)
        if self.clothing:
            parts.append(f"wearing {self.clothing}")
        return " ".join(parts)


@dataclass
class StructuredScenePlan:
    raw_prompt: str
    scene_category: str  # "indoor", "outdoor", "studio", "street", "nature"
    environment_details: str
    people_count: int
    people: list[PersonDescription] = field(default_factory=list)
    lighting_type: str = "natural ambient lighting"
    time_of_day: str | None = None
    weather: str | None = None
    camera_shot: ShotType = ShotType.MEDIUM_SHOT
    camera_gear: str = "35mm prime lens, f/2.8, fine film grain, natural depth of field"
    composition: str = "balanced rule of thirds, distinct subjects, natural proportions"
    photography_style: str = "authentic raw 35mm photograph, photojournalism, realistic skin texture"
    key_objects: list[str] = field(default_factory=list)
    optimized_positive_prompt: str = ""
    negative_prompt: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "scene": {
                "category": self.scene_category,
                "environment": self.environment_details,
                "weather": self.weather,
                "time_of_day": self.time_of_day,
                "lighting": self.lighting_type,
            },
            "people": {
                "count": self.people_count,
                "individuals": [
                    {
                        "person_id": p.index,
                        "description": p.to_prompt_fragment(),
                        "clothing": p.clothing,
                        "activity": p.activity,
                        "position": p.position,
                    }
                    for p in self.people
                ],
            },
            "composition": {
                "shot_type": str(self.camera_shot),
                "camera": self.camera_gear,
                "spatial_arrangement": self.composition,
                "objects": self.key_objects,
            },
            "prompts": {
                "positive": self.optimized_positive_prompt,
                "negative": self.negative_prompt,
            },
        }


# Word-to-number mapping for people counts
NUMBER_WORDS = {
    "one": 1,
    "single": 1,
    "solo": 1,
    "two": 2,
    "couple": 2,
    "pair": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
}

BASE_PHOTOREALISTIC_NEGATIVE = (
    "bad anatomy, deformed face, distorted eyes, cross-eyed, malformed iris, unnatural pupils, "
    "disfigured body, extra limbs, missing arms, missing legs, extra fingers, mutated hands, "
    "fused fingers, too many fingers, missing fingers, poorly drawn hands, poorly drawn face, "
    "cloned face, identical faces on different people, merged bodies, conjoined twins, "
    "plastic skin, porcelain skin, airbrushed, cartoon, 3d render, anime, cgi, illustration, painting, "
    "oversaturated, blurry, out of focus, low quality, watermark, signature, bad proportions, "
    "unnatural poses, floating limbs"
)


class PromptUnderstandingEngine:
    """Understands natural-language prompts and builds structured photorealistic scenes."""

    @classmethod
    def parse_people_count(cls, prompt: str) -> tuple[int, list[str]]:
        """Extracts the number of requested people and any specific individual fragments."""
        lower = prompt.lower()

        # Check explicit digit numbers (e.g. "5 people", "10 persons", "3 women")
        digit_match = re.search(r"\b(\d+)\s*(?:people|persons|individuals|men|women|friends|colleagues|workers|children|family members)\b", lower)
        if digit_match:
            count = int(digit_match.group(1))
            return count, []

        # Check number words (e.g. "five people", "two men", "a family of four")
        for word, val in NUMBER_WORDS.items():
            pattern = rf"\b{word}\s+(?:people|persons|individuals|men|women|friends|colleagues|workers|children|family members|subjects)\b"
            if re.search(pattern, lower):
                return val, []

        # Family check
        family_match = re.search(r"\bfamily of (\w+|\d+)\b", lower)
        if family_match:
            num = family_match.group(1)
            val = int(num) if num.isdigit() else NUMBER_WORDS.get(num, 4)
            return val, []

        if "family" in lower:
            return 4, []

        # Check for multiple individual person mentions
        person_count = 0
        fragments = []
        sentences = [s.strip() for s in re.split(r"[,.;]+", prompt) if s.strip()]
        for sentence in sentences:
            s_lower = sentence.lower()
            if any(term in s_lower for term in ("person", "man", "woman", "girl", "boy", "individual", "colleague")):
                person_count += 1
                fragments.append(sentence)

        if person_count > 0:
            return min(person_count, 12), fragments

        # Check singular terms
        if any(w in lower for w in ("portrait", "a person", "a man", "a woman", "a girl", "a boy", "a professional", "a model")):
            return 1, []

        return 0, []

    @classmethod
    def extract_environment(cls, prompt: str) -> tuple[str, str]:
        """Detects environment category and specific setting."""
        lower = prompt.lower()

        indoor_locations = {
            "office": "modern office space with desks, clean interior architecture, and large windows",
            "restaurant": "cozy indoor restaurant dining room with tables, ambient dinnerware, and interior lighting",
            "cafe": "artisan cafe with coffee counter, seating, and warm interior decor",
            "kitchen": "contemporary domestic kitchen with countertops and appliances",
            "living room": "comfortable residential living room with sofa and modern furniture",
            "studio": "professional photography studio with controlled backdrop and soft lighting",
            "conference room": "corporate conference room with meeting table and presentation equipment",
            "classroom": "educational classroom with desks, chairs, and learning materials",
            "library": "quiet library interior with wooden bookshelves and study tables",
        }
        for key, desc in indoor_locations.items():
            if key in lower:
                return "indoor", desc

        outdoor_locations = {
            "park": "public city park with green grass, lush trees, paved walkways, and open sky",
            "street": "realistic urban city street with sidewalks, authentic architecture, and road details",
            "beach": "natural coastal ocean beach with sand, breaking waves, and horizon",
            "city": "bustling urban cityscape with authentic buildings and pavements",
            "forest": "natural forest setting with tall trees, natural underbrush, and dappled sun",
            "mountain": "open mountainous landscape with rugged terrain and scenic natural backdrop",
            "garden": "vibrant botanical garden with flowers, pathways, and lush foliage",
        }
        for key, desc in outdoor_locations.items():
            if key in lower:
                return "outdoor", desc

        return "ambient", "authentic real-world environment matching the scene context"

    @classmethod
    def extract_lighting(cls, prompt: str) -> str:
        lower = prompt.lower()
        if "daylight" in lower or "natural light" in lower or "sunlight" in lower:
            return "natural directional daylight, soft ambient fill, authentic environmental illumination"
        if "golden hour" in lower or "sunset" in lower or "sunrise" in lower:
            return "warm golden hour lighting, low angled sun rays, rich amber tones and long soft shadows"
        if "studio" in lower or "softbox" in lower or "rim light" in lower:
            return "professional studio strobe lighting with softbox diffusion and subtle rim backlight"
        if "neon" in lower or "night" in lower or "dark" in lower:
            return "nighttime ambient lighting with practical light sources, subtle color contrast, and deep shadows"
        if "overcast" in lower or "cloudy" in lower:
            return "diffuse soft overcast lighting, gentle shadows, true-to-life muted contrast"
        return "authentic natural lighting, soft organic shadows, true-to-life skin illumination"

    @classmethod
    def extract_camera_and_shot(cls, prompt: str, people_count: int) -> tuple[ShotType, str]:
        lower = prompt.lower()
        if "close-up" in lower or "macro" in lower or "face only" in lower:
            return ShotType.EXTREME_CLOSE_UP, "85mm f/1.4 portrait lens, tight framing, creamy background bokeh, ultra-detailed facial features"
        if "portrait" in lower and people_count <= 1:
            return ShotType.PORTRAIT, "85mm f/1.8 prime lens, waist-to-head framing, natural shallow depth of field, sharp subject focus"
        if "full-body" in lower or "full length" in lower:
            return ShotType.FULL_BODY, "50mm prime lens, full-body framing from head to toe, realistic body proportions and anatomical posture"
        if people_count >= 3:
            return ShotType.GROUP_SHOT, "35mm wide-angle lens, f/4 aperture for deep group focus, eye-level candid shot, spacious composition"
        if people_count == 2:
            return ShotType.MEDIUM_SHOT, "50mm lens, f/2.8, balanced two-shot composition, eye-level natural perspective"
        return ShotType.MEDIUM_SHOT, "35mm prime lens, f/2.8 aperture, natural eye-level perspective, authentic photography framing"

    @classmethod
    def plan_scene(cls, prompt: str, style: VisualStyle = VisualStyle.CINEMATIC) -> StructuredScenePlan:
        """Transforms a raw prompt into a comprehensive, structured scene plan."""
        people_count, fragments = cls.parse_people_count(prompt)
        category, environment = cls.extract_environment(prompt)
        lighting = cls.extract_lighting(prompt)
        shot_type, camera_gear = cls.extract_camera_and_shot(prompt, people_count)

        # Parse individual people if multi-person
        people_list: list[PersonDescription] = []
        if people_count > 0:
            if fragments and len(fragments) >= people_count:
                for idx, frag in enumerate(fragments[:people_count], 1):
                    p = PersonDescription(index=idx, raw_mention=frag)
                    p_lower = frag.lower()
                    if "sit" in p_lower:
                        p.position = "seated"
                    elif "stand" in p_lower:
                        p.position = "standing"
                    elif "walk" in p_lower:
                        p.position = "walking"

                    if "laptop" in p_lower:
                        p.activity = "working with a laptop"
                    elif "discuss" in p_lower or "talk" in p_lower:
                        p.activity = "engaged in discussion"
                    elif "present" in p_lower:
                        p.activity = "presenting"

                    people_list.append(p)
            else:
                for idx in range(1, people_count + 1):
                    people_list.append(PersonDescription(index=idx))

        # Detect key objects
        lower = prompt.lower()
        key_objects = []
        object_vocab = ["laptop", "table", "window", "chair", "bicycle", "car", "phone", "coffee cup", "book", "camera", "desk"]
        for obj in object_vocab:
            if obj in lower:
                key_objects.append(obj)

        # Spatial composition
        if people_count >= 5:
            composition = f"wide group arrangement, all {people_count} individuals clearly visible and spaced naturally, distinct outfits, natural candid poses, sharp group focus"
        elif people_count >= 2:
            composition = f"balanced multi-person framing, distinct non-overlapping subjects, authentic interaction and spacing"
        elif people_count == 1:
            composition = "single subject centered, balanced rule of thirds, natural body posture, sharp focus"
        else:
            composition = "environmental landscape framing, balanced architectural proportions, leading lines"

        # Construct optimized positive prompt
        positive_parts = []
        # Photography foundation
        positive_parts.append("authentic raw 35mm color photograph")

        # Core subject matter with exact prompt preserved
        clean_user_prompt = prompt.strip()
        positive_parts.append(clean_user_prompt)

        # Multi-person explicit anatomical anchor
        if people_count >= 2:
            positive_parts.append(f"showing {people_count} distinct individuals with different unique faces and varied clothing, natural anatomical proportions, sharp hands and fingers")
        elif people_count == 1:
            positive_parts.append("detailed human anatomy, natural skin texture with visible pores, lifelike eyes with realistic reflections, anatomically correct hands")

        # Environment & Lighting
        positive_parts.append(environment)
        positive_parts.append(lighting)

        # Camera & Optics
        positive_parts.append(camera_gear)
        positive_parts.append("shot on professional camera, sharp focus, natural color grading, no airbrushing")

        optimized_positive = ", ".join(dict.fromkeys(positive_parts))  # preserve order, remove duplicates

        # Negative prompt
        negative = BASE_PHOTOREALISTIC_NEGATIVE
        if people_count >= 2:
            negative += ", identical faces, cloned people, twins, merged people, shared clothing, overlapping bodies"

        return StructuredScenePlan(
            raw_prompt=prompt,
            scene_category=category,
            environment_details=environment,
            people_count=people_count,
            people=people_list,
            lighting_type=lighting,
            camera_shot=shot_type,
            camera_gear=camera_gear,
            composition=composition,
            key_objects=key_objects,
            optimized_positive_prompt=optimized_positive,
            negative_prompt=negative,
        )
