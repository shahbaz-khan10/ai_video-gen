"""Prompt compiler: turns the user's full prompt into one optimized prompt per scene and per model.

Why: the user's prompt is written for people (titles, "SCENE 2 (7-15 seconds):", character sheets, "keep the
same wolf in every scene", a moral). Video clips are generated one by one and each model reads a limited
number of tokens (CLIP 77 for RealVisXL, UMT5 512 for Wan). Sending the whole story to every clip blends
scenes together; cutting it at a fixed length silently loses instructions.

What it does:
  1. keeps the original prompt verbatim (``ScenePlan.original_prompt``);
  2. splits it into segments and classifies each one (title, moral, heading, scene marker, character sheet,
     continuity directive, story request, environment, character description, action, dialogue);
  3. separates global context (environment, character appearance, continuity) from scene actions;
  4. builds a prompt per target (each video scene, or the image) from prioritised components;
  5. fits each prompt into the model's real token budget, measured with the model's own tokenizer,
     compressing low-priority components first and omitting only as a last resort;
  6. reports, for every instruction, whether it was included, compressed, not supported by the model, or not
     included because of the token budget, and shows the final prompt of every target.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field

from app.schemas.scene_plan import (
    CompiledPrompt,
    Instruction,
    PromptComponent,
    SceneBeat,
    ScenePlan,
)
from app.services.scene_planner import (
    ANIMAL_FORMS,
    CAMERA_MOVES,
    LIGHTING,
    NOUN_RE,
    PERSON_FORMS,
    PLACES,
    QUOTED_TEXT,
    SHOTS,
    STOPWORDS,
    TIMES,
    WEATHER,
    RulePlanner,
    _first,
    _place_in,
    content_words,
    count_phrase,
    limitations_for,
)

Measure = Callable[[str], int]

# --- segment classification --------------------------------------------------------------------

SCENE_MARK = re.compile(r"^\s*(?:scene|shot)\s*(\d{1,2})\b\s*(\([^)]*\))?\s*[:.\-–—]?\s*", re.IGNORECASE)
SECONDS_RANGE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:s|sec|secs|seconds)?\s*(?:-|–|—|to)\s*(\d+(?:\.\d+)?)\s*(?:s|sec|secs|seconds)\b", re.IGNORECASE)
SECONDS_SINGLE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:s|sec|secs|seconds)\b", re.IGNORECASE)
LIST_NUMBER = re.compile(r"^\s*(?:\d{1,2}[.)]|[-*•])\s+")
LABEL = re.compile(r"^\s*([A-Za-z][A-Za-z \-]{1,30}?)\s*(?:\([^)]*\))?\s*:\s*(.*)$")
TITLE = re.compile(r"^\s*(?:video\s+|story\s+|film\s+)?title\s*:", re.IGNORECASE)
MARKDOWN = re.compile(r"\*\*|__|`|^#{1,6}\s*")
DIALOGUE_HEAD = re.compile(r"^(?:dialogue|dialog|speech|voice[- ]?over|narration|lines|script|says)\b", re.IGNORECASE)
REQUIREMENTS_HEAD = re.compile(r"\b(?:requirements?|visual style|style|quality|notes?|rules|technical|instructions?)\b", re.IGNORECASE)
OPEN_QUOTES = "\"“"
# Things a silent video cannot contain. "speaking into the camera" is visible, "a frightened voice" is not.
AUDIO = re.compile(
    r"\b(?:sound effects?|sounds?|music|soundtrack|audio|voices?|lip[- ]?sync(?:ed|ing)?|narration|narrator|"
    r"accent|tone of voice|ambient noise)\b",
    re.IGNORECASE,
)
CAMERA_SENTENCE = re.compile(
    r"^(?:the\s+)?camera\b|\b(?:handheld|hand-held|close[- ]?up|zoom(?:s|ing)? (?:in|out)|dolly|tracking shot|"
    r"camera (?:movement|moves|shakes|captures|pans|tilts|follows|zooms|pushes|pulls|cuts))\b",
    re.IGNORECASE,
)
QUALITY = re.compile(
    r"\b(?:ultra[- ]?realistic|hyper[- ]?realistic|photo[- ]?realistic|realistic|lifelike|4k|8k|uhd|full hd|hd|"
    r"high[- ](?:quality|resolution|detail)|cinematic|quality|detailed|sharp|film grain)\b",
    re.IGNORECASE,
)
RESOLUTION_ASK = re.compile(r"\b(?:4k|8k|uhd|full hd|1080p|2160p|1440p|720p)\b", re.IGNORECASE)
NEGATIVE_START = re.compile(r"^(?:no|without|avoid|never|don'?t|do not)\b", re.IGNORECASE)
NEGATIVE_POSITIVE = {  # what a "no ..." becomes when the sampler has no negative prompt (FastWan)
    r"cartoon|animated|animation|anime|drawing|cgi|3d render": "live-action footage",
    r"blur|blurry": "sharp focus",
}
NEGATIVE_CONTINUITY = re.compile(r"\b(?:face|character|person|people|outfit|clothes|clothing)\s+(?:changes?|swaps?)\b", re.IGNORECASE)
DURATION_LINE = re.compile(
    r"\b(?:total\s+)?(?:duration|length|runtime)\b[^.]*?\d+\s*(?:s|sec|secs|seconds|minutes?)\b"
    r"|^\s*(?:exactly\s+)?\d+\s*[- ]?(?:second|minute)s?(?:\s+(?:long|video|clip))?\s*\.?$",
    re.IGNORECASE,
)
MORAL = re.compile(r"^\s*(?:moral|lesson|message)(?: of the story)?\s*[:\-–]", re.IGNORECASE)
CONTINUITY = re.compile(
    r"\b(?:maintain|keep|preserve|consistent|consistency|identical|unchanged)\b.*"
    r"\b(?:same|consistent|throughout|every (?:scene|shot|clip)|all (?:scenes|shots)|whole video|identical|unchanged)\b"
    r"|\b(?:same|consistent)\b.*\bthroughout\b",
    re.IGNORECASE,
)
STORY_REQUEST = re.compile(r"^\s*(?:please\s+)?(?:create|make|generate|produce|render|show me|film)\b", re.IGNORECASE)
QUOTE = re.compile(r"[\"“”][^\"“”]{1,300}[\"“”]")
SPEECH = re.compile(r"\s*,?\s*\b(?:and\s+)?(?:said|says|saying|shouted|whispered|replied|asked|exclaimed)\b\s*,?\s*$", re.IGNORECASE)
NAMED = re.compile(r"\b(?:named|called)\s+([A-Z][a-z]+)")
PRONOUN_START = re.compile(r"^((?:[A-Z][a-z]+(?: [a-z]+){0,3},\s*)?)(he|she|it)\b", re.IGNORECASE)
DESCRIPTIVE = re.compile(
    r"^(?:(?:once upon a time|one day|long ago),?\s*)?there (?:is|are|was|were)\b"
    r"|\b(?:is|are|was|were)\s+(?!\w+ing\b)(?:\w+\s+){0,2}?(?:a|an|very|so|tall|small|big|old|young|wearing|dressed|covered|white|black|grey|gray|brown|green|blue|red|yellow|pink|golden|fluffy)\b"
    r"|\b(?:has|have)\s+(?!\w+(?:ed|en)\b)",
    re.IGNORECASE,
)
PLURAL_SUBJECT = re.compile(r"^(?:together,?\s*)?(?:they|all the \w+|both)\b", re.IGNORECASE)
# Words that steer the prompt but are not visual content; ignored when checking what reached the model.
META_WORDS = set(
    "scene scenes shot shots seconds second exactly create make generate produce cinematic story video film clip "
    "clips multi-scene multi important very main only keep maintain same throughout every whole consistency "
    "consistent identical exact featuring feature character characters appearance environment lighting".split()
)
CAMERA_WORDS = re.compile(
    r"^(?:(?:extreme |very )?(?:wide|close[- ]up|medium|long|aerial|establishing|tracking|static)\s+)?"
    r"(?:(?:cinematic|establishing|aerial|drone|tracking|wide)\s+)*(?:shot|view|angle)\s+(?:of\s+)?",
    re.IGNORECASE,
)
FILLERS = re.compile(
    r"\b(?:a|an|the|is|are|was|were|be|with|of|that|which|who|also|very|really|beautiful|surrounded by|"
    r"featuring|there|some|few)\b",
    re.IGNORECASE,
)


@dataclass
class Segment:
    text: str  # as written, trimmed
    kind: str  # title | moral | heading | marker | sheet | continuity | request | environment | description | action
    content: str  # the visual part (quotes, labels and markers removed)
    scene: int | None = None  # explicit scene number
    seconds: float | None = None
    character: str | None = None  # character a sheet or description is about
    unsupported: list[str] = field(default_factory=list)  # parts no model can show (quoted speech, text)
    skipped: str | None = None  # deliberately not used for this target, and why
    global_: bool = False  # from a requirements section: applies to every scene, never to one moment


@dataclass
class CastMember:
    id: str
    label: str  # e.g. "grey wolf"
    appearance: list[str] = field(default_factory=list)  # sheet / description sentences
    names: list[str] = field(default_factory=list)


@dataclass
class Draft:
    """One scene before compiling: its action text and the segments it came from."""

    index: int
    action: str
    segments: list[Segment]
    seconds: float | None = None
    cast: list[str] = field(default_factory=list)
    place: str | None = None
    time: str | None = None
    camera: str | None = None


# --- segmentation --------------------------------------------------------------------------------


def _character_noun(text: str) -> str | None:
    m = re.search(rf"\b({NOUN_RE})\b", text, re.IGNORECASE)
    if not m:
        return None
    noun = m.group(1).lower()
    return PERSON_FORMS.get(noun) or ANIMAL_FORMS.get(noun) or noun


def segment(prompt: str) -> list[Segment]:
    """Lines and sentences of the prompt, classified. Understands markdown, section headings ("Dialogue:",
    "Visual requirements:"), quotes that span lines, SCENE markers and numbered character sheets."""
    names = set(NAMED.findall(prompt))
    segments: list[Segment] = []
    scene: int | None = None
    section: str | None = None  # "dialogue" | "requirements" | None
    quote: list[str] = []  # lines of a quotation still open
    for raw_line in prompt.replace("\r\n", "\n").split("\n"):
        line = LIST_NUMBER.sub("", MARKDOWN.sub("", raw_line).strip()).strip()
        if not line:
            continue
        if quote:  # inside a quotation that started on an earlier line
            quote.append(line)
            if any(q in line for q in "\"”"):
                text = " ".join(quote)
                segments.append(Segment(text, "dialogue", "", scene=scene, unsupported=[text]))
                quote = []
            continue
        if TITLE.match(line):
            segments.append(Segment(line, "title", "", unsupported=[line]))
            continue
        if MORAL.match(line):
            segments.append(Segment(line, "moral", "", unsupported=[line]))
            continue
        label = LABEL.match(line.rstrip("."))
        if label and not label.group(2) and not _character_noun(label.group(1)):
            section = "dialogue" if DIALOGUE_HEAD.match(label.group(1)) else (
                "requirements" if REQUIREMENTS_HEAD.search(label.group(1)) else None
            )
            segments.append(Segment(line, "heading", "", scene=scene, character=section))
            continue
        if line[0] in OPEN_QUOTES:  # a spoken line, possibly continuing on the next lines
            closes = line.count("\"") >= 2 or "”" in line
            if closes:
                segments.append(Segment(line, "dialogue", "", scene=scene, unsupported=[line]))
            else:
                quote = [line]
            continue
        if section == "dialogue":
            section = None  # narration resumes after the quoted lines
        for sentence in re.split(r"(?<=[.!?])\s+(?=[A-Z\"“(])", line):
            sentence = sentence.strip()
            if not sentence:
                continue
            mark = SCENE_MARK.match(sentence)
            seconds = None
            if mark:
                scene = int(mark.group(1))
                section = None
                timing = mark.group(2) or ""
                rng = SECONDS_RANGE.search(timing)
                single = SECONDS_SINGLE.search(timing)
                seconds = float(rng.group(2)) - float(rng.group(1)) if rng else float(single.group(1)) if single else None
                rest = sentence[mark.end():].strip()
                segments.append(Segment(sentence[: mark.end()].strip(" :"), "marker", "", scene=scene, seconds=seconds))
                if not rest:
                    continue
                sentence = rest
            seg = _classify(sentence, scene, names)
            seg.global_ = section == "requirements"
            segments.append(seg)
    if quote:
        text = " ".join(quote)
        segments.append(Segment(text, "dialogue", "", scene=scene, unsupported=[text]))
    return segments


def _classify(sentence: str, scene: int | None, names: set[str] | frozenset[str] = frozenset()) -> Segment:
    text = sentence.strip()
    body = text.rstrip(".!?").strip()
    label = LABEL.match(body)
    if label and not label.group(2):
        return Segment(text, "heading", "", scene=scene)  # "CHARACTER CONSISTENCY (VERY IMPORTANT):"
    if label:
        noun = _character_noun(label.group(1))
        if noun and len(label.group(1).split()) <= 3:
            return Segment(text, "sheet", label.group(2).strip(), scene=scene, character=noun)
    unsupported: list[str] = []
    content = body
    quotes = QUOTE.findall(content)
    if quotes:
        unsupported.extend(quotes)
        content = SPEECH.sub("", QUOTE.sub("", content)).strip(" ,")
    elif QUOTED_TEXT.search(content):
        unsupported.append(QUOTED_TEXT.search(content).group(0))
    if DURATION_LINE.search(content):
        return Segment(text, "duration", content, scene=scene)
    if NEGATIVE_START.match(content):
        return Segment(text, "negative", content, scene=scene)
    if CONTINUITY.search(content):
        return Segment(text, "continuity", content, scene=scene, character=_character_noun(content))
    if AUDIO.search(content):
        # Keep the visible part: "lip-sync and realistic facial expressions" -> "realistic facial expressions".
        parts = [p.strip(" ,.") for p in re.split(r",|\band\b", content) if p.strip(" ,.")]
        visible = [p for p in parts if not AUDIO.search(p) and len(p.split()) > 1 and not re.match(r"^(?:natural|english|clear)\b\s*\w*$", p, re.I)]
        heard = [p for p in parts if AUDIO.search(p)]
        if visible:
            return Segment(text, "quality", ", ".join(visible), scene=scene, unsupported=heard)
        return Segment(text, "audio", "", scene=scene, unsupported=[content])
    if CAMERA_SENTENCE.search(content) and not re.match(r"^(?:he|she|they|a|an|the)\s+(?!camera)\w+", content, re.I):
        shot = re.sub(r"^(?:the\s+)?camera\s+", "", content, flags=re.IGNORECASE).strip()
        return Segment(text, "camera", shot or content, scene=scene)
    leftover = QUALITY.sub("", content)
    if QUALITY.search(content) and len(re.findall(r"[a-z]{3,}", leftover, re.I)) <= 1:
        return Segment(text, "quality", content, scene=scene)
    if STORY_REQUEST.match(content) and scene is None:
        return Segment(text, "request", content, scene=scene)
    noun = _character_noun(content)
    named = next((n for n in names if re.search(rf"\b{re.escape(n)}\b", content)), None)
    refers = noun or named or re.match(r"^(?:[A-Z][a-z]+(?: [a-z]+){0,3},\s*)?(?:he|she|it|they|together|both|all the)\b", content, re.IGNORECASE)
    if not refers:
        return Segment(text, "environment", content, scene=scene, unsupported=unsupported)
    if DESCRIPTIVE.search(content):
        return Segment(text, "description", content, scene=scene, character=noun, unsupported=unsupported)
    return Segment(text, "action", content, scene=scene, character=noun, unsupported=unsupported)


# --- cast ------------------------------------------------------------------------------------------


def build_cast(prompt: str, segments: list[Segment]) -> tuple[dict[str, CastMember], dict[str, str]]:
    """Characters with a stable label and their appearance text; names map to character ids."""
    plan = RulePlanner.plan(prompt)
    cast: dict[str, CastMember] = {}
    for c in plan.characters:
        key = _character_noun(c.description or c.id) or c.id
        label = (c.description or c.id).replace("_", " ")
        cast.setdefault(key, CastMember(id=key, label=label))
    names: dict[str, str] = {}
    for m in NAMED.finditer(prompt):
        before = _last_noun(prompt[: m.start()])
        if before and before in cast:
            names[m.group(1)] = before
            cast[before].names.append(m.group(1))
    for seg in segments:
        if seg.kind == "sheet" and seg.character:
            member = cast.setdefault(seg.character, CastMember(id=seg.character, label=seg.character))
            member.appearance.append(seg.content.rstrip("."))
            # The sheet's own wording ("medium-sized grey wolf") is the best label.
            m = re.search(rf"((?:[\w-]+\s+){{0,3}}){re.escape(seg.character)}\b", seg.content, re.IGNORECASE)
            if m and m.group(1).strip():
                label = re.sub(r"^(?:one|a|an|the)\s+", "", m.group(0).strip(), flags=re.IGNORECASE)
                member.label = label.lower()
        elif seg.kind == "description" and seg.character and seg.character in cast:
            cast[seg.character].appearance.append(_appearance(seg.content))
    for member in cast.values():  # "small white sheep - One small white sheep, fluffy wool" -> "fluffy wool"
        cleaned = []
        for a in member.appearance:
            a = re.sub(rf"^(?:one|a|an|the)?\s*{re.escape(member.label)}\b[,\s]*", "", a, flags=re.IGNORECASE).strip(" ,.")
            if a:
                cleaned.append(a)
        member.appearance = cleaned
    return cast, names


STORY_OPENER = re.compile(r"^(?:(?:once upon a time|long ago|one day),?\s*)?(?:there (?:is|are|was|were)\s+)?", re.IGNORECASE)


def _appearance(text: str) -> str:
    """'Once upon a time, there was a little rabbit named Ruby who lived in a forest' -> 'a little rabbit who lived in a forest'."""
    text = NAMED.sub("", text)
    text = STORY_OPENER.sub("", text.strip())
    return re.sub(r"\s+", " ", text).strip(" ,.")


def _last_noun(text: str) -> str | None:
    found = list(re.finditer(rf"\b({NOUN_RE})\b", text, re.IGNORECASE))
    if not found:
        return None
    noun = found[-1].group(1).lower()
    return PERSON_FORMS.get(noun) or ANIMAL_FORMS.get(noun) or noun


def _refs(text: str, cast: dict[str, CastMember], names: dict[str, str]) -> list[str]:
    hits: list[tuple[int, str]] = []
    for key in cast:
        for form in {key, *(f for f, s in {**PERSON_FORMS, **ANIMAL_FORMS}.items() if s == key)}:
            m = re.search(rf"\b{re.escape(form)}\b", text, re.IGNORECASE)
            if m:
                hits.append((m.start(), key))
    for name, key in names.items():
        m = re.search(rf"\b{re.escape(name)}\b", text)
        if m:
            hits.append((m.start(), key))
    ordered: list[str] = []
    for _, key in sorted(hits):
        if key not in ordered:
            ordered.append(key)
    return ordered


def _resolve(
    text: str, cast: dict[str, CastMember], names: dict[str, str], subject: str | None, person: str | None = None
) -> str:
    """Names and a leading he/she/it become the character's description, which the model understands."""
    m = PRONOUN_START.match(text)
    if m:
        who = person if m.group(2).lower() in ("he", "she") and person else subject
        if who and who in cast:
            text = f"{m.group(1)}the {cast[who].label}{text[m.end():]}"
    for name, key in names.items():
        text = re.sub(rf"\b{re.escape(name)}\b", f"the {cast[key].label}", text)
    text = re.sub(r"\bthe the\b", "the", text)
    return text[0].upper() + text[1:] if text else text


# --- scenes ---------------------------------------------------------------------------------------


def draft_scenes(
    segments: list[Segment],
    cast: dict[str, CastMember],
    names: dict[str, str],
    *,
    max_scenes: int,
    user_scenes: list[tuple[str, float | None]] | None = None,
) -> list[Draft]:
    """Scene drafts from explicit markers, the user's edited list, or one scene per action."""
    if user_scenes:
        drafts = []
        for i, (description, seconds) in enumerate(user_scenes, 1):
            seg = _classify(description, i)
            drafts.append(Draft(i, description.strip().rstrip("."), [seg], seconds))
    elif any(s.scene is not None for s in segments):
        by_scene: dict[int, Draft] = {}
        for seg in segments:
            if seg.scene is None:
                continue
            d = by_scene.setdefault(seg.scene, Draft(seg.scene, "", []))
            if seg.kind == "marker":
                d.seconds = seg.seconds
            d.segments.append(seg)
        drafts = [by_scene[k] for k in sorted(by_scene)]
        for d in drafts:
            d.action = " ".join(s.content.rstrip(".") + "." for s in d.segments if s.content and s.kind in ("action", "environment", "description")).strip()
    else:
        drafts = []
        for seg in segments:
            if seg.kind == "action":
                drafts.append(Draft(len(drafts) + 1, seg.content.rstrip("."), [seg]))
            elif seg.kind in ("environment", "description", "camera") and drafts and not seg.global_:
                drafts[-1].segments.append(seg)  # detail of the moment just described
        if not drafts:
            visual = [s for s in segments if s.kind in ("environment", "description", "request")]
            drafts = [Draft(1, " ".join(s.content.rstrip(".") + "." for s in visual).strip() or "A scene", visual)]
        while len(drafts) > max_scenes:  # merge the shortest neighbours until the duration allows
            k = min(range(len(drafts) - 1), key=lambda i: len(drafts[i].action) + len(drafts[i + 1].action))
            a, b = drafts[k], drafts.pop(k + 1)
            a.action = f"{a.action}, then {b.action[0].lower()}{b.action[1:]}"
            a.segments += b.segments
        for i, d in enumerate(drafts, 1):
            d.index = i

    subject: str | None = next(iter(cast), None)
    person: str | None = next((k for k in cast if cast[k].names), subject)
    place = time = None
    previous: list[str] = []
    for d in drafts:
        text = " ".join(s.content for s in d.segments) or d.action
        refs = _refs(text, cast, names)
        d.action = _resolve(d.action, cast, names, subject, person) if d.action else d.action
        if refs:
            subject = refs[0]
            person = next((r for r in refs if cast[r].names), person)
        # A character stays in the shot while the place does not change ("a wolf appears" keeps the sheep).
        new_place = _place_in(text)
        if len(refs) == 1 and previous and (new_place is None or new_place == place):
            refs = refs + [p for p in previous if p not in refs][:1]
        d.cast = refs or previous or ([subject] if subject else [])
        previous = d.cast
        place = new_place or place
        time = _first(TIMES, text) or time
        d.place, d.time = place, time
        shot = next((s.content for s in d.segments if s.kind == "camera"), None)
        d.camera = shot or _first(SHOTS, text) or _first(CAMERA_MOVES, text)
    return drafts


# --- components and budget ------------------------------------------------------------------------


def _phrases(text: str) -> list[str]:
    """'A beautiful green meadow surrounded by tall pine trees, distant mountains and a river' ->
    ['green meadow', 'tall pine trees', 'distant mountains', 'river']."""
    parts = re.split(r",|;|\band\b|\bwith\b|\bsurrounded by\b|\bunder\b", text, flags=re.IGNORECASE)
    out = []
    for p in parts:
        p = FILLERS.sub(" ", p)
        p = re.sub(r"\s+", " ", p).strip(" .")
        if p and p.lower() not in {x.lower() for x in out}:
            out.append(p)
    return out


def _variants(full: str, *, keep_min: int = 1) -> list[str]:
    """Full text, then the same content as keyword phrases, then fewer phrases."""
    phrases = _phrases(full)
    variants = [full]
    if phrases:
        variants.append(", ".join(phrases))
        for n in range(len(phrases) - 1, keep_min - 1, -1):
            variants.append(", ".join(phrases[:n]))
    seen: list[str] = []
    for v in variants:
        if v and v not in seen:
            seen.append(v)
    return seen


@dataclass
class Component:
    name: str
    priority: int  # lower = more important
    variants: list[str]  # full first
    level: int = 0  # index into variants; len(variants) means omitted
    required: bool = False

    @property
    def text(self) -> str:
        return self.variants[self.level] if self.level < len(self.variants) else ""

    @property
    def status(self) -> str:
        if self.level == 0:
            return "included"
        return "omitted" if self.level >= len(self.variants) else "compressed"


def _fit(components: list[Component], measure: Measure, budget: int, render: Callable[[list[Component]], str]) -> str:
    """Compress the least important components first, then omit them; the action is cut only as a last resort."""
    order = sorted(components, key=lambda c: -c.priority)
    while measure(render(components)) > budget:
        for c in order:  # 1) next compression level of the least important component that has one
            if not c.required and c.level < len(c.variants) - 1:
                c.level += 1
                break
        else:
            for c in order:  # 2) omit the least important optional component
                if not c.required and c.level < len(c.variants):
                    c.level = len(c.variants)
                    break
            else:
                for c in sorted(components, key=lambda c: c.priority):  # 3) compress required ones
                    if c.level < len(c.variants) - 1:
                        c.level += 1
                        break
                else:
                    break
    return render(components)


def _render(components: list[Component]) -> str:
    parts = []
    for c in components:
        if not c.text:
            continue
        parts.append(c.text if c.name == "action" else f"{c.name.capitalize()}: {c.text}")
    return ". ".join(p.rstrip(".") for p in parts) + "."


def _component(name: str, text: str | None, priority: int, *, required: bool = False) -> Component | None:
    if not text:
        return None
    return Component(name, priority, _variants(text) if not required else [text, *_variants(text)[1:]], required=required)


def compile_targets(
    prompt: str,
    *,
    mode: str,
    style_text: str | None,
    style_name: str | None,
    duration_seconds: float | None,
    user_scenes: list[tuple[str, float | None]] | None,
    measure: Measure,
    budget: int,
    tokenizer_name: str,
    measured: bool,
) -> tuple[list[Draft], list[CompiledPrompt], list[Segment]]:
    segments = segment(prompt)
    cast, names = build_cast(prompt, segments)
    long_video = mode == "text-to-video" and (duration_seconds or 0) > 5
    # Long videos: at most one scene per 2 s. Images and single clips keep every moment separate here and
    # choose below (an image shows one moment; one clip plays them in order).
    max_scenes = max(1, min(24, int((duration_seconds or 0) // 2))) if long_video else 24
    drafts = draft_scenes(segments, cast, names, max_scenes=max_scenes, user_scenes=user_scenes if long_video else None)

    env_segments = [s for s in segments if s.kind == "environment" and s.scene is None and not drafts_contain(drafts, s)]
    if not env_segments:  # e.g. "SCENE 1: Wide establishing shot of the green meadow" sets the place for the story
        env_segments = [s for s in segments if s.kind == "environment" and _place_in(s.content)][:1] or [
            s for s in segments if s.kind == "environment"
        ][:1]
    # "Wide cinematic establishing shot of the green meadow" -> setting "the green meadow" (the shot is camera).
    environment = " ".join(
        CAMERA_WORDS.sub("", s.content).strip(" .").rstrip(".") + "." for s in env_segments
    ).strip(" .") or None
    continuity = any(s.kind == "continuity" for s in segments)
    plan = RulePlanner.plan(prompt)
    global_text = " ".join(s.content for s in segments if s.scene is None and s.kind in ("environment", "request", "continuity"))
    lighting = ", ".join(filter(None, [_first(LIGHTING, global_text), _first(WEATHER, global_text)])) or None
    global_camera = (
        "; ".join(s.content for s in segments if s.kind == "camera" and not drafts_contain(drafts, s))
        or _first(SHOTS, global_text) or _first(CAMERA_MOVES, global_text)
    )
    # Quality words and "no cartoon"-style requirements become part of the style (FastWan has no negative prompt).
    quality = [re.sub(r"\s{2,}", " ", RESOLUTION_ASK.sub("", s.content)).strip(" ,.") for s in segments if s.kind == "quality"]
    for seg in segments:
        if seg.kind == "negative":
            for pattern, positive in NEGATIVE_POSITIVE.items():
                if re.search(pattern, seg.content, re.IGNORECASE):
                    quality.append(positive)
    quality_text = ", ".join(dict.fromkeys(q for q in quality if q))
    if any(s.kind == "negative" and NEGATIVE_CONTINUITY.search(s.content) for s in segments):
        continuity = True
    style_full = ", ".join(filter(None, [style_text, quality_text])) or None

    targets: list[CompiledPrompt] = []
    if long_video:
        jobs = drafts
    elif mode == "text-to-image" and len(drafts) > 2:
        jobs = [_merge_all(drafts[:1])]
        for d in drafts[1:]:
            for seg in d.segments:
                seg.skipped = (
                    f"A still image shows one moment, so it uses the first moment of the story; this is moment {d.index}. "
                    "Use Text to Video to show the whole story."
                )
        for seg in segments:
            if seg.kind == "sheet" and seg.character not in jobs[0].cast:
                seg.skipped = "This character first appears in a later moment of the story, not in the one the image shows."
    else:
        jobs = [_merge_all(drafts)]
    for d in jobs:
        members = [cast[k] for k in d.cast if k in cast]
        characters = "; ".join(
            m.label + (" — " + ", ".join(dict.fromkeys(m.appearance)) if m.appearance else "") for m in members
        )
        if mode == "text-to-image" and count_phrase(plan):
            counted = {_character_noun(c.description or c.id) for c in plan.characters if c.count}
            rest = "; ".join(
                m.label + (" - " + ", ".join(dict.fromkeys(m.appearance)) if m.appearance else "")
                for m in members if m.id not in counted
            )
            characters = "; ".join(filter(None, [count_phrase(plan), rest]))
        setting_bits = []
        if d.place and (not environment or d.place.lower() not in environment.lower()):
            setting_bits.append(d.place)
        if environment and environment.lower() not in d.action.lower():
            setting_bits.append(environment)
        if d.time and d.time not in " ".join(setting_bits).lower():
            setting_bits.append(d.time)
        # Details written right after the action ("Behind him, the sky turns blood red") belong to this moment.
        details = " ".join(
            s.content.rstrip(".") + "." for s in d.segments
            if s.kind in ("environment", "description") and s.content and s.content not in d.action
        ) or None
        components = [
            c
            for c in (
                _component("action", d.action, 0, required=True),
                _component("characters", characters, 1),
                _component("details", details, 2),
                _component("setting", ", ".join(setting_bits), 3),
                _component("camera", d.camera or global_camera, 4),
                _component("lighting", lighting if lighting and lighting.lower() not in (environment or "").lower() else None, 5),
                _component("style", style_full, 6),
                _component(
                    "continuity",
                    "the same characters, setting and lighting as the other shots" if long_video and (continuity or len(jobs) > 1) else None,
                    7,
                ),
            )
            if c
        ]
        if style_full and style_name:  # compress style to its short name plus the user's quality words
            for c in components:
                if c.name == "style":
                    c.variants = list(dict.fromkeys([style_full, ", ".join(filter(None, [style_name, quality_text])), style_name]))
        text = _fit(components, measure, budget, _render)
        targets.append(
            CompiledPrompt(
                target=f"scene {d.index}" if long_video else ("image" if mode == "text-to-image" else "video"),
                model=tokenizer_name,
                text=text,
                tokens=measure(text),
                budget=budget,
                measured=measured,
                components=[PromptComponent(name=c.name, status=c.status, text=c.text, full_text=c.variants[0]) for c in components],
            )
        )
    return drafts, targets, segments


def drafts_contain(drafts: list[Draft], seg: Segment) -> bool:
    return any(seg is s for d in drafts for s in d.segments)


def _merge_all(drafts: list[Draft]) -> Draft:
    """One clip or one image: every moment in order, in a single prompt."""
    if len(drafts) == 1:
        return drafts[0]
    first = drafts[0]
    action = first.action.rstrip(".") + "".join(", then " + d.action[0].lower() + d.action[1:].rstrip(".") for d in drafts[1:] if d.action)
    cast: list[str] = []
    for d in drafts:
        cast += [c for c in d.cast if c not in cast]
    return Draft(1, action, [s for d in drafts for s in d.segments], None, cast, first.place, first.time, first.camera)


# --- reporting -------------------------------------------------------------------------------------


def report_instructions(
    segments: list[Segment],
    targets: list[CompiledPrompt],
    *,
    mode: str,
    duration_seconds: float | None,
) -> list[Instruction]:
    """One entry per instruction of the user's prompt with an exact status and where it went."""
    words_by_target = {t.target: set(content_words(t.text)) | {w.rstrip("s") for w in content_words(t.text)} for t in targets}
    budget_cut = {t.target for t in targets if any(c.status != "included" for c in t.components)}
    out: list[Instruction] = []
    for seg in segments:
        if seg.kind == "marker":
            seconds = f", {seg.seconds:g} s" if seg.seconds else ""
            out.append(Instruction(text=seg.text, status="included", note=f"Scene boundary (scene {seg.scene}{seconds}).", targets=[f"scene {seg.scene}"]))
            continue
        if seg.kind == "heading":
            note = {
                "dialogue": "Section heading: the quoted lines that follow are speech.",
                "requirements": "Section heading: the lines that follow apply to every scene.",
            }.get(seg.character or "", "Section heading: used to read the structure of the prompt.")
            out.append(Instruction(text=seg.text, status="included", note=note))
            continue
        if seg.kind == "dialogue":
            out.append(Instruction(
                text=seg.text, status="unsupported", reaches_model=False,
                note="Spoken words: the video models make silent clips and cannot render speech or lip-sync. "
                     "The speaker's actions and expressions are kept.",
            ))
            continue
        if seg.kind == "audio":
            out.append(Instruction(
                text=seg.text, status="unsupported", reaches_model=False,
                note="Sound: the video models generate silent video, so voice, music and sound effects cannot be made.",
            ))
            continue
        if seg.kind == "duration":
            asked = re.search(r"(\d+)\s*[- ]?(second|sec|s|minute)", seg.content, re.IGNORECASE)
            seconds = float(asked.group(1)) * (60 if asked and asked.group(2).lower().startswith("minute") else 1) if asked else None
            if seconds and duration_seconds and seconds != float(duration_seconds):
                note = f"The length comes from the Duration setting ({duration_seconds:g} s); the prompt asks for {seconds:g} s."
            else:
                note = "The length comes from the Duration setting" + (f" ({duration_seconds:g} s), which matches." if duration_seconds else ".")
            out.append(Instruction(text=seg.text, status="included", note=note))
            continue
        if seg.kind == "negative":
            mapped = [pos for pat, pos in NEGATIVE_POSITIVE.items() if re.search(pat, seg.content, re.IGNORECASE)]
            keeps = bool(NEGATIVE_CONTINUITY.search(seg.content))
            if mapped or keeps:
                bits = []
                if mapped:
                    bits.append("turned into a positive instruction (" + ", ".join(mapped) + ")")
                if keeps:
                    bits.append("character changes are prevented by repeating the same descriptions in every clip")
                note = "Applied: " + "; ".join(bits) + ". The fast video sampler has no negative prompt."
                out.append(Instruction(text=seg.text, status="included", note=note, targets=[t.target for t in targets]))
            else:
                out.append(Instruction(
                    text=seg.text, status="unsupported", reaches_model=False,
                    note="The fast video sampler has no negative prompt, so 'no …' cannot be enforced; images use it as a negative prompt.",
                ))
            continue
        if seg.kind in ("title", "moral"):
            out.append(Instruction(
                text=seg.text, status="unsupported",
                note="Not visual: the models cannot render a title or a moral as text. The story itself is used.",
            ))
            continue
        if seg.kind == "continuity":
            note = (
                "Applied by repeating the same character and setting descriptions in every clip prompt."
                if mode == "text-to-video" and len(targets) > 1
                else "Applied: one prompt describes the characters and setting."
            )
            out.append(Instruction(text=seg.text, status="included", note=note, targets=[t.target for t in targets]))
            continue
        words = [w for w in content_words(seg.content) if w not in META_WORDS]
        if seg.kind == "request":
            asked = re.search(r"(\d+)\s*-?\s*(?:second|sec)", seg.content, re.IGNORECASE)
            note = "Style and characters are taken from this request."
            if asked and duration_seconds and float(asked.group(1)) != float(duration_seconds):
                note += f" It asks for {asked.group(1)} s; the Duration setting ({duration_seconds:g} s) is used."
            elif asked:
                note += f" Length {asked.group(1)} s matches the Duration setting."
            hit = [t.target for t, ws in ((t, words_by_target[t.target]) for t in targets) if any(w in ws for w in words)]
            out.append(Instruction(text=seg.text, status="included", note=note, targets=hit))
            continue
        if not words:
            continue
        if seg.skipped:
            out.append(Instruction(text=seg.text, status="unsupported", note=seg.skipped, reaches_model=False))
            continue
        best_target, best = None, 0.0
        for t in targets:
            ws = words_by_target[t.target]
            ratio = sum(1 for w in words if w in ws or w.rstrip("s") in ws) / len(words)
            if ratio > best:
                best_target, best = t.target, ratio
        hits = [t.target for t in targets if sum(1 for w in words if w in words_by_target[t.target] or w.rstrip("s") in words_by_target[t.target]) / len(words) >= 0.5]
        if seg.kind == "quality":
            note = "Added to the style of every prompt."
            if RESOLUTION_ASK.search(seg.content):
                note += " Resolution is limited by the model: Draft 576×320 or Quality 832×480, not 4K."
            if seg.unsupported:
                note += " Not possible in silent video: " + "; ".join(seg.unsupported) + "."
            status = "compressed" if (RESOLUTION_ASK.search(seg.content) or seg.unsupported) else "included"
            out.append(Instruction(text=seg.text, status=status, note=note, targets=hits))
            continue
        if seg.kind == "camera":
            # Where it was actually used: the prompts whose camera component carries this direction.
            used = [t.target for t in targets if any(c.name == "camera" and seg.content in c.text for c in t.components)]
            status = "included" if used else ("omitted_budget" if budget_cut else "compressed")
            where = "every scene" if len(used) == len(targets) > 1 else ", ".join(used)
            note = f"Camera direction for {where}." if used else "Camera direction left out to fit the model's token budget."
            out.append(Instruction(text=seg.text, status=status, note=note, targets=used))
            continue
        if seg.unsupported:
            status, note = ("compressed" if best >= 0.5 else "unsupported"), (
                "Shown without the spoken or written words, which the models cannot render: " + "; ".join(seg.unsupported)
            )
        elif best >= 0.85:
            status, note = "included", None
        elif best >= 0.5:
            status = "compressed"
            note = "Shortened to fit the model's token budget." if best_target in budget_cut else "Included with simplified wording."
        else:
            status = "omitted_budget" if budget_cut else "unsupported"
            note = (
                "Not included: it did not fit in the model's token budget after compressing other details."
                if budget_cut
                else "Could not be turned into visual instructions."
            )
        out.append(Instruction(text=seg.text, status=status, note=note, targets=hits, reaches_model=status in ("included", "compressed")))
    return out


def compile_plan(
    prompt: str,
    *,
    mode: str,
    style_text: str | None,
    style_name: str | None = None,
    duration_seconds: float | None = None,
    user_scenes: list[tuple[str, float | None]] | None = None,
    measure: Measure,
    budget: int,
    tokenizer_name: str,
    measured: bool,
) -> ScenePlan:
    """The full plan: extraction (characters, place, camera), scenes, compiled prompts and instruction report."""
    drafts, targets, segments = compile_targets(
        prompt, mode=mode, style_text=style_text, style_name=style_name, duration_seconds=duration_seconds,
        user_scenes=user_scenes, measure=measure, budget=budget, tokenizer_name=tokenizer_name, measured=measured,
    )
    base = RulePlanner.plan(prompt)
    long_video = any(t.target.startswith("scene ") for t in targets)
    scenes = [
        SceneBeat(index=d.index, description=d.action or f"Scene {d.index}", characters=d.cast, camera=d.camera, duration_seconds=d.seconds)
        for d in drafts
    ] if long_video else [SceneBeat(index=1, description=_merge_all(drafts).action or "Scene", characters=_merge_all(drafts).cast)]
    # The summary shows what the compiled prompts use: place/lighting/camera from scene and setting text only,
    # never from a character description ("dark grey fur" is not "low light", "appears from behind a tree" is
    # not a camera angle).
    scene_text = " ".join(s.content for s in segments if s.kind in ("environment", "request", "continuity", "action"))
    setting_text = " ".join(s.content for s in segments if s.kind in ("environment", "request", "continuity"))
    first_place = next((d.place for d in drafts if d.place), None) or _place_in(scene_text)
    environment = base.environment.model_copy(update={
        "location": first_place or base.environment.location,
        "lighting": _first(LIGHTING, setting_text),
        "weather": _first(WEATHER, scene_text),
        "time_of_day": _first(TIMES, scene_text),
    })
    camera = base.camera.model_copy(update={
        "shot_type": _first(SHOTS, scene_text),
        "movement": _first(CAMERA_MOVES, scene_text),
        "angle": base.camera.angle if base.camera.angle and "behind" not in base.camera.angle else None,
    })
    plan = base.model_copy(update={"scenes": scenes, "planner": "rules+compiler", "environment": environment, "camera": camera})
    instructions = report_instructions(segments, targets, mode=mode, duration_seconds=duration_seconds)
    limitations = limitations_for(plan, mode=mode)
    over = [t for t in targets if any(c.status == "omitted" for c in t.components)]
    if over:
        limitations.append(
            "Some low-priority details were left out of " + ", ".join(t.target for t in over)
            + " to fit the model's token budget; see each prompt's components."
        )
    return plan.model_copy(update={
        "instructions": instructions,
        "limitations": limitations,
        "compiled": targets,
        "model_prompt": " | ".join(t.text for t in targets),
    })
