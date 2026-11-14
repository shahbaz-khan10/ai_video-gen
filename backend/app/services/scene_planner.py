"""Scene planner: turns a prompt into a validated ``ScenePlan`` and builds the exact model prompts.

Two layers:
  * ``RulePlanner`` (always available, instant): clause splitting and whole-word extraction of counts,
    people/animals, clothing, positions, actions, places, weather, time, lighting, camera and style.
  * an optional LLM layer (``app.services.llm_planner``) that fills characters/positions/actions/scenes
    with real language understanding; its output is merged into and checked against the rule layer.

Whatever the layers produce, ``validate`` lists every clause of the user's prompt with the plan fields
that cover it and whether it reaches the model within the model's text limit. Requests the models cannot
honour reliably are reported in ``limitations``; nothing is dropped silently.
"""

from __future__ import annotations

import re
from collections.abc import Callable

from app.schemas.scene_plan import (
    Camera,
    Character,
    Environment,
    Instruction,
    SceneBeat,
    SceneObject,
    ScenePlan,
)

# --- lexicons (whole words only) ---------------------------------------------------------

NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
    "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
    "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
    "hundred": 100, "dozen": 12, "couple": 2, "pair": 2,
}

# singular -> plural (irregulars spelled out; the rest add "s"/"es")
PERSON_NOUNS = {
    "man": "men", "woman": "women", "person": "people", "child": "children", "boy": "boys", "girl": "girls",
    "kid": "kids", "baby": "babies", "student": "students", "pupil": "pupils", "teacher": "teachers",
    "farmer": "farmers", "worker": "workers", "doctor": "doctors", "nurse": "nurses", "soldier": "soldiers",
    "officer": "officers", "policeman": "policemen", "player": "players", "dancer": "dancers",
    "friend": "friends", "guard": "guards", "driver": "drivers", "chef": "chefs", "cook": "cooks",
    "waiter": "waiters", "customer": "customers", "tourist": "tourists", "villager": "villagers",
    "musician": "musicians", "singer": "singers", "athlete": "athletes", "runner": "runners",
    "businessman": "businessmen", "businesswoman": "businesswomen", "engineer": "engineers",
    "scientist": "scientists", "shopkeeper": "shopkeepers", "vendor": "vendors", "fisherman": "fishermen",
    "grandmother": "grandmothers", "grandfather": "grandfathers", "mother": "mothers", "father": "fathers",
    "son": "sons", "daughter": "daughters", "brother": "brothers", "sister": "sisters", "king": "kings",
    "queen": "queens", "warrior": "warriors", "astronaut": "astronauts", "pilot": "pilots", "monk": "monks",
    "priest": "priests", "imam": "imams", "child labourer": "child labourers", "family member": "family members",
    "reporter": "reporters", "journalist": "journalists", "presenter": "presenters", "anchor": "anchors",
    "host": "hosts", "cameraman": "cameramen", "photographer": "photographers", "firefighter": "firefighters",
    "detective": "detectives", "survivor": "survivors", "hero": "heroes", "villain": "villains",
    "stranger": "strangers", "traveler": "travelers", "traveller": "travellers", "explorer": "explorers",
    "hunter": "hunters", "artist": "artists", "painter": "painters", "boss": "bosses", "employee": "employees",
    "manager": "managers", "passenger": "passengers", "captain": "captains", "sailor": "sailors",
    "knight": "knights", "wizard": "wizards", "witch": "witches", "prince": "princes", "princess": "princesses",
    "cowboy": "cowboys", "robot": "robots", "alien": "aliens", "zombie": "zombies", "lady": "ladies",
    "gentleman": "gentlemen", "teenager": "teenagers", "toddler": "toddlers", "athlete": "athletes",
    "boxer": "boxers", "climber": "climbers", "biker": "bikers", "scientist": "scientists",
}
GROUP_NOUNS = {"crowd", "audience", "family", "team", "class", "group", "army", "people"}
ANIMAL_NOUNS = {
    "dog": "dogs", "puppy": "puppies", "retriever": "retrievers", "labrador": "labradors", "cat": "cats",
    "kitten": "kittens", "horse": "horses", "cow": "cows", "bird": "birds", "monkey": "monkeys",
    "lion": "lions", "tiger": "tigers", "elephant": "elephants", "sheep": "sheep", "goat": "goats",
    "fish": "fish", "deer": "deer", "wolf": "wolves", "fox": "foxes", "bear": "bears", "eagle": "eagles",
    "duck": "ducks", "chicken": "chickens", "camel": "camels", "rabbit": "rabbits", "parrot": "parrots",
    "dolphin": "dolphins", "shark": "sharks", "butterfly": "butterflies", "dragon": "dragons",
}

PLACES = {
    # place: (canonical, setting)
    "classroom": ("classroom", "indoor"), "school": ("school", None), "office": ("office", "indoor"),
    "kitchen": ("kitchen", "indoor"), "restaurant": ("restaurant", "indoor"), "cafe": ("cafe", "indoor"),
    "library": ("library", "indoor"), "hospital": ("hospital", "indoor"), "bedroom": ("bedroom", "indoor"),
    "living room": ("living room", "indoor"), "studio": ("studio", "indoor"), "mosque": ("mosque", None),
    "church": ("church", None), "temple": ("temple", None), "museum": ("museum", "indoor"),
    "forest": ("forest", "outdoor"), "jungle": ("jungle", "outdoor"), "beach": ("beach", "outdoor"),
    "village": ("village", "outdoor"), "city": ("city", "outdoor"), "street": ("street", "outdoor"),
    "park": ("park", "outdoor"), "desert": ("desert", "outdoor"), "mountain": ("mountains", "outdoor"),
    "mountains": ("mountains", "outdoor"), "river": ("river", "outdoor"), "lake": ("lake", "outdoor"),
    "ocean": ("ocean", "outdoor"), "sea": ("sea", "outdoor"), "field": ("field", "outdoor"),
    "farm": ("farm", "outdoor"), "market": ("market", "outdoor"), "bazaar": ("bazaar", "outdoor"),
    "garden": ("garden", "outdoor"), "road": ("road", "outdoor"), "highway": ("highway", "outdoor"),
    "bridge": ("bridge", "outdoor"), "stadium": ("stadium", None), "space": ("outer space", None),
    "underwater": ("underwater", "outdoor"), "rooftop": ("rooftop", "outdoor"), "harbor": ("harbor", "outdoor"),
    "home": ("home", None), "house": ("house", None), "valley": ("valley", "outdoor"),
    "meadow": ("meadow", "outdoor"), "countryside": ("countryside", "outdoor"), "grassland": ("grassland", "outdoor"),
    "pasture": ("pasture", "outdoor"), "hill": ("hills", "outdoor"), "hills": ("hills", "outdoor"),
    "river bank": ("river bank", "outdoor"), "riverbank": ("river bank", "outdoor"), "waterfall": ("waterfall", "outdoor"),
}
WEATHER = {
    r"snow(?:ing|y|fall| is falling| falling)?": "snow", r"rain(?:ing|y|fall)?": "rain",
    r"fog(?:gy)?|mist(?:y)?|haze|hazy": "fog", r"storm(?:y)?|thunder\w*|lightning": "storm",
    r"sunny|clear sky": "sunny", r"cloudy|overcast": "overcast", r"windy|wind": "windy",
}
TIMES = {
    r"midnight|at night|night(?:time)?": "night", r"sunset|golden hour": "sunset", r"sunrise|dawn": "sunrise",
    r"dusk|twilight|blue hour": "dusk", r"morning": "morning", r"noon|midday": "noon",
    r"afternoon": "afternoon", r"evening": "evening",
}
LIGHTING = {
    r"neon": "neon light", r"candle\w*": "candlelight", r"moonlight|moonlit": "moonlight",
    r"firelight|campfire|fireplace": "firelight", r"lantern\w*|lamp\w*": "lamp light",
    r"dim(?:ly)? lit|dark": "low light", r"bright(?:ly)? lit|bright": "bright light", r"spotlight": "spotlight",
}
CAMERA_MOVES = {
    r"follow(?:s|ing)?(?: \w+){0,3} from behind": "follows the subject from behind",
    r"follow(?:s|ing)?": "follows the subject",
    r"track(?:s|ing)?(?: \w+){0,3} from the side": "tracks the subject from the side",
    r"track(?:s|ing)?|tracking shot": "tracking shot",
    r"pan(?:s|ning)? (?:left|right|across)": "pans", r"tilt(?:s|ing)? (?:up|down)": "tilts",
    r"zoom(?:s|ing)? in|push(?:es|ing)? in|dolly in": "pushes in", r"zoom(?:s|ing)? out|pull(?:s|ing)? back|dolly out": "pulls back",
    r"orbit(?:s|ing)?|circl(?:es|ing) around": "orbits the subject", r"aerial|drone": "aerial shot",
    r"handheld": "handheld", r"static camera|locked[- ]off|still camera": "static camera",
}
SHOTS = {
    r"extreme close[- ]up": "extreme close-up", r"close[- ]up": "close-up", r"medium shot": "medium shot",
    r"full[- ]body": "full body shot", r"wide shot|wide[- ]angle|establishing shot": "wide shot",
    r"portrait": "portrait",
}
ANGLES = {
    r"low[- ]angle": "low angle", r"high[- ]angle": "high angle", r"eye[- ]level": "eye level",
    r"top[- ]down|overhead|bird'?s[- ]eye": "top-down", r"from behind": "from behind",
    r"from the side|side view|profile": "from the side", r"front view|facing the camera": "front view",
}
STYLES = {
    r"photo-?realistic|realistic|photograph\w*|real life": "photorealistic", r"cinematic|film still|movie": "cinematic",
    r"anime": "anime", r"cartoon|animated|pixar|3d animation": "cartoon", r"documentary": "documentary",
    r"black and white|monochrome": "black and white", r"vintage|retro": "vintage", r"oil painting|watercolou?r|painting": "painting",
}
OBJECTS = [
    "blackboard", "whiteboard", "desk", "table", "chair", "bench", "car", "bus", "truck", "bicycle", "bike",
    "motorcycle", "train", "boat", "ship", "phone", "laptop", "computer", "book", "bag", "basket", "cart",
    "vegetables", "fruit", "umbrella", "lamp", "window", "door", "bed", "sofa", "tree", "trees", "pine trees",
    "flowers", "waves", "rock", "rocks", "fire", "campfire", "tent", "guitar", "ball", "kite", "cup", "camera",
]
POSITION = re.compile(
    r"\b(at the (?:front|back|rear|center|centre|left|right|corner|top|bottom)(?: of [^,.;]+?)?"
    r"|(?:standing |sitting )?(?:beside|next to|in front of|behind|near|under|above|on top of|between) [^,.;]+?"
    r"|on the (?:left|right)(?: side)?(?: of [^,.;]+?)?|in the (?:background|foreground|middle|center|centre)"
    r"|at (?:separate|their|the) desks?)(?=[,.;]|\s+(?:and|while|teaching|holding|looking|with)\b|$)",
    re.IGNORECASE,
)
# Clothing may contain "and" ("a white shirt and black trousers"), so it ends at the next verb instead.
CLOTHING = re.compile(
    r"\b(?:wearing|wears|wear|dressed in) ([^,.;]+?)(?=\s+(?:stands?|standing|sits?|sitting|walks?|walking|runs?|running|is|are|"
    r"while|with|holding|teaching|dances?|dancing|looks?|looking|rides?|riding)\b|[,.;]|$)",
    re.IGNORECASE,
)
NEGATION = re.compile(r"\b(?:no|without|never show|must not (?:show|have|include)|don'?t show|not show) ([a-z][a-z \-]{1,40}?)(?=[,.;]|\s+(?:and|but|in|on|at)\b|$)", re.IGNORECASE)
SEQUENCE_SPLIT = re.compile(r"\s*(?:,\s*(?:and\s+)?then\s+|;\s*|\bthen\b\s*|\bafter that\b,?\s*|\bfinally\b,?\s*|\bnext\b,\s*)", re.IGNORECASE)
STOPWORDS = set(
    "a an the and or of to in on at by for with from into onto is are was were be been being this that these those "
    "it its their his her him he she they them there here must should can will would may very so as while who which "
    "what also all any each every some such just only one about over under up down out off".split()
)
QUOTED_TEXT = re.compile(r"[\"“”'‘’][^\"“”'‘’]{2,}[\"“”'‘’]|\b(?:sign|text|caption|words?|letters?|logo) (?:that )?(?:says|reading|reads|saying)\b", re.IGNORECASE)


def _plural_forms(table: dict[str, str]) -> dict[str, str]:
    """word form -> singular, for every singular and plural form."""
    forms: dict[str, str] = {}
    for singular, plural in table.items():
        forms[singular] = singular
        forms[plural] = singular
    return forms


PERSON_FORMS = _plural_forms(PERSON_NOUNS)
ANIMAL_FORMS = _plural_forms(ANIMAL_NOUNS)
NUMBER_RE = r"\d+|" + "|".join(sorted(NUMBER_WORDS, key=len, reverse=True))
NOUN_RE = "|".join(sorted({*PERSON_FORMS, *ANIMAL_FORMS}, key=len, reverse=True))
COUNTED = re.compile(rf"\b(?:a\s+)?({NUMBER_RE})\s+(?:of\s+)?((?:[a-z-]+\s+){{0,2}}?)({NOUN_RE})\b", re.IGNORECASE)
SINGLE = re.compile(rf"\b(a|an)\s+((?:[\w-]+\s+){{0,3}}?)({NOUN_RE})\b", re.IGNORECASE)


def _first(patterns: dict[str, str], text: str) -> str | None:
    for pattern, value in patterns.items():
        if re.search(rf"\b(?:{pattern})\b", text, re.IGNORECASE):
            return value
    return None


# "-ing" words that describe how someone looks, not something they do next.
DESCRIPTIVE_ING = r"(?:wearing|holding|carrying|having|dressed|smiling|looking)"


def _place_in(text: str) -> str | None:
    """The place named first in the text (by position, not by lexicon order)."""
    found = [(m.start(), canonical) for word, (canonical, _) in PLACES.items()
             for m in [re.search(rf"\b{re.escape(word)}\b", text, re.IGNORECASE)] if m]
    return min(found)[1] if found else None


def split_clauses(prompt: str) -> list[str]:
    """Sentences, further split on sequence markers ("then", ";") and on comma lists of -ing actions."""
    clauses: list[str] = []
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", prompt.strip()):
        sentence = sentence.strip().rstrip(".!?").strip()
        if not sentence:
            continue
        for part in SEQUENCE_SPLIT.split(sentence):
            part = part.strip(" ,")
            if not part:
                continue
            # "walking through a village, meeting an old farmer, and returning home" -> separate beats
            # ...but ", wearing a yellow raincoat" describes the subject; it is not a new moment.
            pieces = re.split(rf",\s*(?:and\s+)?(?=(?!{DESCRIPTIVE_ING}\b)\w+ing\b)", part)
            clauses.extend(p.strip(" ,") for p in pieces if p.strip(" ,"))
    return clauses


SYNONYMS = {
    "seated": "sitting", "sits": "sitting", "sit": "sitting", "stands": "standing", "stand": "standing",
    "walks": "walking", "runs": "running", "kids": "children", "pupils": "students",
    "realistic": "photorealistic", "photo": "photorealistic", "photograph": "photorealistic",
}


def content_words(text: str) -> list[str]:
    words = re.findall(r"[a-z][a-z\-']+", text.lower())
    return [SYNONYMS.get(w, w) for w in words if w not in STOPWORDS and len(w) > 2]


class RulePlanner:
    """Deterministic extraction. Fast and predictable; complex grammar is left to the LLM layer."""

    @staticmethod
    def plan(prompt: str, style: str | None = None) -> ScenePlan:
        text = prompt.strip()
        lower = text.lower()
        clauses = split_clauses(text)

        characters: list[Character] = []
        seen: set[str] = set()
        for match in COUNTED.finditer(text):
            number, adjectives, noun = match.group(1).lower(), match.group(2).strip(), match.group(3).lower()
            singular = PERSON_FORMS.get(noun) or ANIMAL_FORMS.get(noun) or noun
            if singular in seen:
                continue
            count = int(number) if number.isdigit() else NUMBER_WORDS.get(number)
            seen.add(singular)
            characters.append(_character(text, singular, count, adjectives, match))
        for match in SINGLE.finditer(text):
            noun = match.group(3).lower()
            singular = PERSON_FORMS.get(noun) or ANIMAL_FORMS.get(noun) or noun
            if singular in seen:
                continue
            seen.add(singular)
            characters.append(_character(text, singular, 1, match.group(2).strip(), match))
        for group in GROUP_NOUNS:
            if group not in seen and re.search(rf"\b(?:a|the)\s+(?:\w+\s+)?{group}\b", lower) and group != "people":
                seen.add(group)
                characters.append(Character(id=group, kind="group", description=group))

        person_counts = [c.count for c in characters if c.kind in ("person", "group") and c.count]
        people_count = sum(person_counts) if person_counts else None

        location = setting = None
        other_places: list[str] = []
        for word, (canonical, kind) in PLACES.items():
            if re.search(rf"\b{re.escape(word)}\b", lower):
                if location is None:
                    location, setting = canonical, kind
                elif canonical != location:
                    other_places.append(canonical)  # e.g. "school" alongside "classroom"
        if setting is None and location is not None:
            setting = "indoor" if re.search(r"\b(?:inside|indoors|room|hall)\b", lower) else None

        objects = []
        for name in OBJECTS:
            if re.search(rf"\b{re.escape(name)}\b", lower):
                if name == "camera" and re.search(r"\bthe camera\b\s+\w+", lower):
                    continue  # "the camera follows" is camera direction, not an object in the scene
                position = None
                pos = re.search(rf"\b{re.escape(name)}\b[^,.;]*?\b({POSITION.pattern})", text, re.IGNORECASE)
                if pos:
                    position = pos.group(1)
                objects.append(SceneObject(name=name, position=position))

        environment = Environment(
            location=location,
            setting=setting,
            background=other_places + [o.name for o in objects if o.name in {"trees", "pine trees", "waves", "flowers", "rocks"}],
            weather=_first(WEATHER, lower),
            time_of_day=_first(TIMES, lower),
            lighting=_first(LIGHTING, lower),
        )
        movement = _first(CAMERA_MOVES, lower)
        angle = _first(ANGLES, lower)
        if movement and angle and angle in movement:
            angle = None  # "follows the subject from behind" already says it
        camera = Camera(shot_type=_first(SHOTS, lower), angle=angle, movement=movement)

        main = characters[0] if characters else None
        main_subject = (main.description or main.id) if main else (location or (clauses[0] if clauses else None))

        scenes = _beats(clauses, main_subject)
        return ScenePlan(
            original_prompt=text,
            planner="rules",
            main_subject=main_subject,
            people_count=people_count,
            characters=characters,
            objects=objects,
            environment=environment,
            camera=camera,
            style=style or _first(STYLES, lower),
            scenes=scenes,
        )


def _character(text: str, singular: str, count: int | None, adjectives: str, match: re.Match) -> Character:
    kind = "animal" if singular in ANIMAL_FORMS.values() or singular in ANIMAL_NOUNS else "person"
    # Details live in the rest of the clause that mentions this character.
    start = match.start()
    end_match = re.search(r"[.;!?]", text[match.end():])
    clause = text[start : match.end() + (end_match.start() if end_match else len(text))]
    clothing = CLOTHING.search(clause)
    position = POSITION.search(clause)
    action = re.search(
        r"\b(?:is |are )?((?:stands?|sits?|sitting|standing|walks?|walking|runs?|running|dances?|dancing|"
        r"teach(?:es|ing)?|holds?|holding|carr(?:y|ies|ying)|looks?|looking|talks?|talking|smiles?|smiling|jumps?|"
        r"jumping|rides?|riding|plays?|playing|reads?|reading|writes?|writing|works?|working|cooks?|cooking|"
        r"swims?|swimming|flies|flying|eats?|eating|sleeps?|sleeping|meets?|meeting|helps?|helping|"
        r"returns?|returning|waves?|waving|fights?|fighting|sings?|singing|cries|crying|laughs?|laughing)\b[^,.;]*)",
        clause,
        re.IGNORECASE,
    )
    description = " ".join(part for part in (adjectives, singular) if part).strip()
    plural_label = (PERSON_NOUNS.get(singular) or ANIMAL_NOUNS.get(singular) or f"{singular}s") if count and count > 1 else singular
    return Character(
        id=plural_label.replace(" ", "_"),
        kind="group" if count and count > 1 and kind == "person" else kind,
        count=count,
        description=f"{adjectives} {plural_label}".strip() if count and count > 1 else description,
        clothing=clothing.group(1).strip() if clothing else None,
        position=position.group(1).strip() if position else None,
        action=action.group(1).strip() if action else None,
    )


ACTION_START = re.compile(rf"^(?:(?!{DESCRIPTIVE_ING}\b)\w+ing|then|after|finally|next)\b", re.IGNORECASE)
# "She makes tea", "In the evening she reads a book": the subject doing something new. Descriptions of how
# the subject looks ("she is wearing", "he has a beard") are not actions and stay in the same scene.
TIME_LEAD = r"(?:(?:then|later|next|finally|afterwards|after that|in the \w+|at \w+|by \w+|that \w+)\s*,?\s+)?"
PRONOUN_ACTION = re.compile(
    rf"^{TIME_LEAD}(he|she|they)\s+(?!(?:is|are|was|were|has|have|had|wears|looks|seems|appears)\b)[a-z]+",
    re.IGNORECASE,
)


def _beats(clauses: list[str], subject: str | None) -> list[SceneBeat]:
    """Story beats: clauses that start with an action ("meeting an old farmer") or a pronoun doing something
    ("she makes tea") inherit the subject, so every scene prompt names who it is about."""
    story = [c for c in clauses if ACTION_START.match(c) or PRONOUN_ACTION.match(c)]
    # One action clause ("teaching ten students") is a single moment, not a story.
    if len(story) < 2:
        return [SceneBeat(index=1, description=". ".join(clauses) or "scene")]
    beats: list[SceneBeat] = []
    lead = [c for c in clauses if c not in story]
    for clause in lead[:1] + story:
        description = clause
        if clause in story and subject:
            pronoun = PRONOUN_ACTION.match(clause)
            if pronoun:
                start, end = pronoun.span(1)
                description = f"{clause[:start]}the {subject}{clause[end:]}"
            else:
                description = f"{subject} {clause}"
        beats.append(SceneBeat(index=len(beats) + 1, description=description))
    return beats


# --- validation ---------------------------------------------------------------------------

def _plan_text(plan: ScenePlan) -> dict[str, str]:
    fields: dict[str, str] = {}
    for i, c in enumerate(plan.characters):
        fields[f"characters[{i}]"] = " ".join(
            filter(None, [c.id, c.description, c.clothing, c.position, c.action, c.age])
        )
    for i, o in enumerate(plan.objects):
        fields[f"objects[{i}]"] = " ".join(filter(None, [o.name, o.position]))
    env = plan.environment
    fields["environment"] = " ".join(filter(None, [env.location, env.weather, env.time_of_day, env.lighting, *env.background]))
    cam = plan.camera
    fields["camera"] = " ".join(filter(None, [cam.shot_type, cam.angle, cam.movement]))
    fields["style"] = plan.style or ""
    whole = set(content_words(plan.original_prompt))
    for s in plan.scenes:
        words = set(content_words(s.description))
        # A scene that just repeats the whole prompt proves nothing was understood; it doesn't count as coverage.
        if len(plan.scenes) == 1 and whole and len(words & whole) / len(whole) > 0.8:
            continue
        fields[f"scenes[{s.index - 1}]"] = " ".join(filter(None, [s.description, s.action, s.camera]))
    return fields


def validate(plan: ScenePlan, *, mode: str, model_prompt: str, fits: Callable[[str], bool] | None = None) -> ScenePlan:
    """Fills ``instructions`` (clause coverage), ``limitations`` and ``model_prompt``."""
    fields = _plan_text(plan)
    field_words = {name: set(content_words(text)) | {w.rstrip("s") for w in content_words(text)} for name, text in fields.items()}
    instructions: list[Instruction] = []
    for clause in split_clauses(plan.original_prompt):
        words = content_words(clause)
        if not words:
            continue
        hits = {name for name, ws in field_words.items() if any(w in ws or w.rstrip("s") in ws for w in words)}
        matched = [w for w in words if any(w in ws or w.rstrip("s") in ws for ws in field_words.values())]
        ratio = len(matched) / len(words)
        status = "included" if ratio >= 0.6 else "compressed" if matched else "unsupported"
        # Scene prompts may reword a clause ("She makes tea" -> "the girl makes tea"); its words must all arrive.
        reaches = fits(clause) if fits else (
            clause.lower() in model_prompt.lower() or set(words) <= set(content_words(model_prompt))
        )
        instructions.append(Instruction(text=clause, covered_by=sorted(hits), reaches_model=reaches, status=status))

    limitations = limitations_for(plan, mode=mode)
    return plan.model_copy(update={"instructions": instructions, "limitations": limitations, "model_prompt": model_prompt})


def limitations_for(plan: ScenePlan, *, mode: str) -> list[str]:
    """Requests the models cannot honour reliably, in plain words."""
    limitations: list[str] = []
    for c in plan.characters:
        if c.count and c.count > 4:
            limitations.append(
                f"Exact count ({c.count} {c.id.replace('_', ' ')}): image and video models approximate groups larger "
                "than about 4; expect roughly this many, not an exact number."
            )
    if any(c.position and re.search(r"\b(?:left|right)\b", c.position, re.IGNORECASE) for c in plan.characters):
        limitations.append("Left/right placement is approximate.")
    # Quoted lines next to "said/dialogue" are speech (reported per instruction), not text to draw.
    drawn_text = re.search(r"\b(?:sign|text|caption|banner|logo|title card|poster|label)\b", plan.original_prompt, re.IGNORECASE)
    if QUOTED_TEXT.search(plan.original_prompt) and (drawn_text or mode == "text-to-image"):
        limitations.append("Readable text, signs and logos are not reliably rendered.")
    negations = [m.group(1).strip() for m in NEGATION.finditer(plan.original_prompt)]
    if negations and mode == "text-to-image":
        limitations.append(
            "Negative instructions (" + ", ".join(negations) + ") are passed to the negative prompt; diffusion "
            "models can still draw them occasionally."
        )
    elif negations:
        limitations.append(
            "The fast video sampler has no negative prompt: 'no …' instructions (" + ", ".join(negations) + ") are "
            "turned into positive wording where possible (e.g. 'no cartoon' → live-action) and cannot be enforced otherwise."
        )
    if mode == "text-to-video" and re.search(r"\b(?:dialogue|said|says|voice|sound|music|lip[- ]?sync)\b|[\"“]", plan.original_prompt, re.IGNORECASE):
        limitations.append("The video is silent: speech, voice, lip-sync, music and sound effects are not generated.")
    if mode == "text-to-image":
        if plan.camera.movement:
            limitations.append(f"Camera movement ('{plan.camera.movement}') cannot be shown in a still image.")
        if len(plan.scenes) > 1:
            limitations.append("This prompt describes several moments; a still image shows only one. Use video for the story.")
    if mode == "text-to-video" and len(plan.scenes) > 1:
        # Each clip is generated separately from text only; with nothing but "a girl" to go on, the model
        # draws a different girl every time (measured: hair, age and clothes changed between scenes).
        # Measured (docs/consistency): with hair and clothing written out and repeated in every scene, FastWan kept
        # the same clothes in all scenes; without them clothes and face changed from scene to scene.
        vague = [c.id for c in plan.characters if c.kind == "person" and not c.clothing]
        if vague:
            limitations.append(
                "No clothing or hair is described for " + ", ".join(f"'{v}'" for v in vague) + ": each scene is "
                "generated separately, so the model may draw a different-looking character every time. Add a line "
                "such as 'He has short dark hair and wears a grey jacket over a blue shirt' to keep them consistent."
            )
        limitations.append(
            "Scenes are separate clips joined with cuts; the same character can still change slightly between scenes."
        )
    return limitations


def negative_terms(prompt: str) -> list[str]:
    """Things the user explicitly does not want ("no hats", "without people")."""
    return [m.group(1).strip() for m in NEGATION.finditer(prompt)]


# --- model prompts ------------------------------------------------------------------------

def count_phrase(plan: ScenePlan) -> str | None:
    """Explicit counts restated compactly ("1 male teacher, 10 students"), which helps models a little."""
    parts = [f"{c.count} {c.description or c.id}" for c in plan.characters if c.count and c.count > 1]
    singles = [f"one {c.description or c.id}" for c in plan.characters if c.count == 1 and c.kind == "person"]
    phrase = ", ".join(singles + parts)
    return phrase or None


def build_video_prompt(plan: ScenePlan, style_text: str | None, scene: SceneBeat | None = None) -> str:
    """A full scene description for Wan's UMT5 encoder (up to 512 tokens), with a continuity block that is
    repeated in every clip of a long video so characters, place and look stay the same."""
    body = scene.description if scene else plan.original_prompt
    lines = [body.rstrip(".") + "."]
    # The other scenes' text is deliberately left out: given the whole story, the model blended every scene
    # into each clip (a teapot in the bedroom, a kitchen instead of the park).
    cast = []
    for c in plan.characters:
        details = ", ".join(filter(None, [c.description or c.id, f"wearing {c.clothing}" if c.clothing else None]))
        if details:
            cast.append(details)
    if cast:
        lines.append("Characters: " + "; ".join(cast) + ".")
    env = plan.environment
    location, time_of_day = env.location, env.time_of_day
    if scene is not None and len(plan.scenes) > 1:
        # Each scene happens where (and when) its own text says, else where the previous scene was.
        location = time_of_day = None
        for beat in plan.scenes:
            location = _place_in(beat.description) or location
            time_of_day = _first(TIMES, beat.description) or time_of_day
            if beat.index == scene.index:
                break
        location = location or env.location
        time_of_day = time_of_day or env.time_of_day
    place = ", ".join(filter(None, [location, time_of_day, env.weather, env.lighting]))
    if place:
        lines.append(f"Setting: {place}.")
    cam = scene.camera if scene and scene.camera else ", ".join(filter(None, [plan.camera.movement, plan.camera.shot_type, plan.camera.angle]))
    if cam:
        lines.append(f"Camera: {cam}.")
    if style_text:
        lines.append(f"Style: {style_text}.")
    return " ".join(lines)


def build_image_prompt_parts(plan: ScenePlan, style_text: str | None) -> list[str]:
    """Parts in priority order for CLIP's 77-token budget: the user's words always come first."""
    parts = [plan.original_prompt]
    counts = count_phrase(plan)
    if counts:
        parts.append(counts)
    if style_text:
        parts.append(style_text)
    return parts
