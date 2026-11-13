# Prompt Token Limit & Scene Prompt Compiler — Fix Report

Branch `shahbaz_ai_vdeo` (base `3027636`). All token counts in this report come from the models' **own tokenizers** loaded from the local model cache: CLIP from `SG161222/RealVisXL_V5.0_Lightning/tokenizer` and UMT5 from `Wan-AI/Wan2.1-T2V-1.3B-Diffusers/tokenizer` (`backend/app/services/prompt_tokens.py`). No character-count estimates.

## 1. Audit (before any code change)

Script: `backend/scripts/audit_prompt_tokens.py` → `docs/prompt_compiler/audit_before.txt` / `audit_before.json`.

### 1.1 Real measurements of the old pipeline

| Prompt | Chars | CLIP tokens (budget 75) | UMT5 tokens (budget 512) | Scenes planned | Longest video prompt sent (UMT5) | Image prompt (CLIP) |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| Phase 4 meadow test | 429 | 77 | 87 | **1** | 111 | 79 → CLIP silently drops "story ., photorealistic" |
| Wolf/sheep, structured with `SCENE 1 (0-7 seconds)` | 926 | 204 | 242 | **1** | 185 | 206 → CLIP silently drops the whole sheep description, "maintain…", all scenes |
| Rabbit story (user's) | 684 | 140 | 155 | **1** | 170 | 142 → CLIP drops everything after "a long branch" |
| Classroom | 58 | 13 | 14 | 1 | 30 | 22 (fits) |

### 1.2 Root causes

1. **"Cut off by the model's text limit" was wrong for video.** The video encoder (UMT5) accepts 512 tokens and no video prompt ever exceeded 185. The text that went missing was cut by **our own code**: when a story is not split into scenes, the single scene description is `". ".join(clauses)[:600]` (`backend/app/services/scene_planner.py:350`; beats also `[:600]` at `:362`, and `SceneBeat.description` has `max_length=600` in `backend/app/schemas/scene_plan.py:50`). For the wolf/sheep prompt this removed SCENE 2–4 and the sheep's action; for the rabbit story, the last three sentences.
2. **The flag was computed by word matching, not tokenization.** `validate()` (`scene_planner.py:405`) marks `reaches_model=False` when a clause's words are not all found in the model prompt, and the UI labels that "cut off by the model's text limit" (`src/components/studio/scene-plan-panel.tsx:80`). It never consulted a tokenizer.
3. **Images had the opposite error: real truncation, not reported.** CLIP reads 77 tokens (75 + start/end). `DiffusersImageEngine._fit_prompt` (`backend/app/services/image_engine.py:305`) always keeps the user's whole prompt as the first part, so CLIP itself truncates it inside the pipeline. `GenerationService.plan` validates image plans without a tokenizer (`generation_service.py:261-270`), so the UI claimed everything reached the model.
4. **Scene structure was not recognised.** `SCENE 1 (0-7 seconds):` headings, numbered character sheets (`1. WOLF: …`), and narrative sentences with named or `it` subjects did not create scenes (`_beats`, `scene_planner.py:344`), so the whole story became one scene and every clip received the whole (truncated) story.
5. **"Partly understood / not understood" came from a keyword overlap ratio** (`scene_planner.py:400-403`): words outside the small lexicons ("maintain", "environment", "appearance", "kindness") lowered the score, so valid directives such as *"Maintain the same environment, character appearance and lighting throughout"* were reported as **not understood** even though repeating the descriptions in every clip is exactly how the system honours them.
6. **Global context and scene content were mixed.** Environment descriptions and character sheets were only kept if they happened to fall inside the first 600 characters; scenes did not get their own place, cast and action.

## 2. The fix: prompt compiler

New module `backend/app/services/prompt_compiler.py`, used for every image and video plan and job.

1. **Original prompt preserved** verbatim in `ScenePlan.original_prompt`; nothing is cut at a character limit any more (the `[:600]` truncations are removed and `SceneBeat.description` allows 4000 characters).
2. **Segmentation** of the prompt into title, moral, heading, `SCENE N (a-b seconds)` marker, numbered character sheet (`1. WOLF: …`), continuity directive ("Maintain/keep the same … throughout"), story request ("Create a 30-second …"), environment, character description, action and dialogue.
3. **Global context vs scene content**: environment and character sheets are global and repeated in each clip; actions belong to their scene. Names ("Ruby") and leading pronouns (`he/she/it`) are replaced by the character's description, which the model understands; `she/he` resolve to the named character, `it` to the last one mentioned.
4. **Scenes**: from explicit markers (with their durations), from the user's edited scene list, or one per action sentence (merged only when the duration allows fewer scenes). A character stays in the shot while the place does not change (the sheep remains when the wolf appears).
5. **One prompt per target** (`scene N` for long videos, `video` for a single clip, `image`) built from prioritised components: action > characters (with appearance) > setting > camera > lighting > style > continuity.
6. **Real token budget**: each prompt is measured with the model's own tokenizer — UMT5 for video (budget 511 = 512 − end token), CLIP for images (75 = 77 − start/end). If it does not fit, the lowest-priority component is compressed first (sentence → keyword phrases → fewer phrases; style → its short name), then omitted; the scene's action is cut only as a last resort. Every component reports `included / compressed / omitted` with its full text.
7. **Images** show one moment: up to two moments fit one picture; for a longer story the first moment is used and the other moments are reported with that reason.
8. **Honest instruction report**: every sentence/line of the prompt gets one of `included` (*Understood and included*), `compressed` (*Understood but compressed*), `unsupported` (*Not supported by the model*), `omitted_budget` (*Not included because of the token budget*), plus a plain-language note and the prompts that contain it. The message "Shorten the prompt or move key details earlier" is gone.
9. **Fallback**: if a model's tokenizer is not on disk (weights not downloaded, generation unavailable anyway), a word/punctuation count is used and every compiled prompt is marked `measured: false` / "estimated" in the UI.

The image engine compiles with the pipeline's own CLIP tokenizer at generation time, so the prompt shown to the user is exactly what CLIP reads. The prompt length limit was raised from 1000 to 4000 characters (`PROMPT_MAX_CHARS`, `PROMPT_MAX`), since a long structured prompt is now compiled per scene instead of being sent whole.

## 3. Changed files

| File | Change |
| --- | --- |
| `backend/app/services/prompt_compiler.py` | **New**: segmentation, cast, scenes, components, budget fitting, instruction report |
| `backend/app/services/prompt_tokens.py` | **New**: loads CLIP/UMT5 tokenizers from the local model cache; budgets |
| `backend/app/schemas/scene_plan.py` | New statuses, `note`, `targets`; `PromptComponent`, `CompiledPrompt`; `ScenePlan.compiled`; scene text up to 4000 chars |
| `backend/app/services/scene_planner.py` | Removed the 600-char cuts and the "shorten the prompt" message; `limitations_for()` extracted; legacy `validate` maps to the new statuses; places `meadow, countryside, grassland, pasture, hills, river bank, waterfall` |
| `backend/app/services/generation_service.py` | `plan()` and `_plan_video()` use the compiler with the real tokenizer (`_budget`, `_compile`); scene prompts come from the compiled targets |
| `backend/app/services/image_engine.py` | Image prompt compiled with the pipeline's CLIP tokenizer |
| `backend/app/schemas/generation.py`, `src/components/studio/prompt-editor.tsx` | Prompt limit 1000 → 4000 characters |
| `src/types/api.ts`, `src/components/studio/scene-plan-panel.tsx` | New statuses with labels and notes; per-target prompt viewer with measured token count and component status |
| `backend/scripts/audit_prompt_tokens.py` | **New**: before/after measurement with the real tokenizers |
| `backend/tests/test_prompt_compiler.py` | **New**: 13 logic tests + 3 real-tokenizer tests |
| `backend/tests/test_scene_planner.py`, `test_video_jobs.py`, `test_generation.py`, `test_health.py` | Updated for the new statuses and limit |

## 4. Real tokenizer measurements after the fix

`docs/prompt_compiler/audit_after.txt` / `audit_after.json` (30 s video; image):

| Prompt | Video scenes | UMT5 tokens per scene (budget 511) | Components cut (video) | Image CLIP tokens (budget 75) | Image components cut |
| --- | ---: | --- | --- | ---: | --- |
| Phase 4 meadow | 2 | 96, 100 | none | 74 | style → short name |
| Wolf/sheep structured | 4 (7/8/8/7 s) | 83, 101, 103, 108 | none | 65 | none (first moment only) |
| Rabbit story | 9 | 57–74 | none | 58 | none (first moment only) |
| Classroom | 1 | 44 | none | 50 | none |

Running backend (API `POST /generations/scene-plan`, Phase 4 prompt, 15 s): scene 1 = 96/511, scene 2 = 100/511, `model: umt5 (Wan2.1)`, `measured: true` (`docs/prompt_compiler/phase4_scene_plan_api.json`).

## 5. Before / after examples

**Wolf/sheep, scene 3 — before** (one scene for the whole video; the same text for every clip, cut at 600 characters, SCENE 2–4 missing):
> Create an exactly 30-second cinematic 3D animated wildlife story featuring ONLY TWO main characters: one grey wolf and one white sheep. CHARACTER CONSISTENCY (VERY IMPORTANT): … SCENE 1 (0-7 seconds): Wide cinematic establishing shot of the beautiful green meadow. The white sheep is peacefully eating fresh green grass. SCENE 2 (7-15 sec

**After — scene 3 (103 UMT5 tokens):**
> The sheep notices the wolf and runs toward the river. Characters: small white sheep — fluffy white wool, pink face, black eyes; medium-sized grey wolf — dark grey fur, white chest, yellow eyes, pointed ears, long bushy tail. Setting: river, the beautiful green meadow. Style: cinematic film still, anamorphic lens, dramatic motivated lighting, film grain. Continuity: the same characters, setting and lighting as the other shots.

**Rabbit — before:** 1 scene; title, dialogue and "Moral:" sent to all 14 clips; the last sentences reported as "cut off by the model's text limit".
**After:** 9 scenes, e.g. *"The little rabbit quickly called her forest friends."* (the old planner would have resolved "She" to the bird); "Ruby" never reaches the model; title and moral → *Not supported by the model*; the quote → *Understood but compressed* ("shown without the spoken words").

**Image of the structured prompt — before:** 206 CLIP tokens; CLIP silently dropped everything after the wolf sheet. **After:** 65 tokens, first moment (meadow, sheep eating), the later moments reported as *Not supported by the model — a still image shows one moment*.

**Instruction statuses — before vs after (meadow prompt):** "A beautiful green countryside meadow…" *partial* → *included*; "Maintain the same environment, character appearance and lighting throughout" *not understood* → *included* (note: applied by repeating descriptions in every clip prompt); "Create a cinematic multi-scene story" *partial* → *included*.

## 6. Test results

| Test | Result |
| --- | --- |
| Backend suite (Docker) | **240 passed**, 6 skipped (3 real-tokenizer tests skip without the model cache) |
| Compiler tests with the model cache mounted (real CLIP + UMT5) | **16 passed** (13 logic + 3 real-tokenizer) |
| Frontend: `tsc --noEmit`, `npm test`, ESLint | clean, 26 passed, 0 errors (5 old warnings) |
| Browser (Edge via Playwright): Plan scenes for the meadow and wolf/sheep prompts, image plan | New statuses, notes and per-scene prompts with token counts shown (`docs/prompt_compiler/compiler_*_panel.png`) |
| **Real generation, Phase 4 prompt, 15 s Draft, seed 42** | Completed in 4 min 39 s, 240 frames, 15.0 s (`phase4_meadow_15s.mp4`, `phase4_meadow_sheet.png`) |

Phase 4 checklist (frames checked manually):

| Requirement | Result |
| --- | --- |
| Meadow environment preserved | ✅ pine trees, distant mountains, river, wildflowers, blue sky with white clouds in both scenes |
| Sheep remains white | ✅ |
| Wolf remains grey | ✅ grey; ⚠ slightly purple-grey and more cartoon-like in the first clip of scene 2 |
| Wolf appears from behind a tree | ✅ wolf emerges from behind a tree trunk |
| Scene actions not lost | ✅ scene 1 sheep grazing; scene 2 wolf appears, sheep still present |
| Each scene gets its own optimized prompt | ✅ 96 and 100 UMT5 tokens, measured |
| No important instruction silently truncated | ✅ all 5 instructions *included*; no component cut |

## 7. Remaining limitations

- The compiler is rule-based English parsing. Unusual grammar can still be classified wrongly; the UI now shows exactly which prompt each instruction went into, so this is visible instead of hidden.
- Prompt adherence still depends on the models: exact counts above ~4, small details (hat colour), and identical character identity across separately generated clips are not guaranteed by Wan2.1/FastWan 1.3B or SDXL.
- Clips of the same scene are still joined with a crossfade (ghosting risk, Phase I bug B2) — not part of this fix.
- The legacy `PromptUnderstandingEngine` still provides the image negative prompt and the old `/generations/plan` endpoint.
- `next dev` in Docker on Windows does not see file changes on the bind mount; the frontend container must be restarted after frontend edits (it was during this work).

