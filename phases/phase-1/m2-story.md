# ReelForge Phase 1 / M2 — Story

Binding inputs: `ReelForge — Requirements Document.md`, `ReelForge — Product Spec.md` (Stage 1 Story input, story.yaml format, Manual edit options for Story), `ReelForge — Technical Spec.md` (Ollama adapter, Where local LLMs are used, Pipeline engine task `structure_story`, API story endpoints, Frontend). The Technical Spec wins on design; the Requirements Document wins on acceptance. Parent: `phases/phase-1-foundation-story-cast.md`. Requires `m1-backbone.md` merged.

## Requirements
- R1. `story.yaml` Pydantic schema (version, title, language, style, aspect, fps, target_seconds, brand_kit, characters, product, scenes, music, captions) exactly as in the Product Spec; unknown fields rejected with a message naming the field; ruamel.yaml round-trip keeps comments and order; YAML parsed in safe mode; JSON Schema exported for the editor.
- R2. Story versions: every save creates a `story_versions` row (one current); `PUT /api/v1/projects/{id}/story` validates and saves; `POST …/story:approve` locks the story and moves the project to `STORY_APPROVED`; editing after approval drops the stage back and marks dependants stale.
- R3. Ollama adapter (`POST /api/chat` with JSON-schema `format`, temperature 0.2–0.4, `keep_alive: 0` when a heavy job is next, default model `qwen3:8b`, health via `GET /api/tags`) with Pydantic validation and one automatic repair round that sends the validation errors back.
- R4. `structure_story` task via `POST …/story:structure`: free text (plus optional characters, locations, product placement, dialogue, style, language, target length, library picks) becomes 4–8 scenes sized to the target, speakers assigned, character look text in a fixed form, gap questions instead of guesses; suggested dialogue is marked "suggested"; prompts live in versioned `prompts/*.md` files with few-shot examples.
- R5. Import and export of `story.yaml`; an imported file skips the LLM and opens in the editor.
- R6. Story UI: input screen (storyline box, collapsible optional boxes, "Structure my story"), gap questions inline, story editor with synced Form view (character and scene cards, reorder, add/delete, running length estimate) and Monaco YAML view with live validation errors, version list, "Approve story".
- R7. Prompt wiring: the mock LLM returns a canned valid story for tests; the real Ollama adapter is used only when selected.

## Acceptance criteria
- AC-1: Given a storyline with 2 characters and 5 scenes on the mock LLM, the system produces a `story.yaml` that passes schema validation, can be edited in form and YAML views, and re-saved as a new version.
- AC-2: A `story.yaml` with an unknown field or an invalid value is rejected with a message naming the field; nothing is silently dropped.
- AC-3: Round-trip: loading and saving a YAML with comments leaves comments and key order unchanged.
- AC-4: Invalid LLM output triggers exactly one repair round with the validation errors; if still invalid, the user sees the error and no story version is saved.
- AC-5: Editing a story field after approval returns the stage to `DRAFT` for the affected items only; unrelated items are not marked stale.
- AC-6: An imported valid `story.yaml` creates a version without calling the LLM; export returns the current version byte-for-byte.
- AC-7: Gap questions appear for missing information instead of invented details, and suggested dialogue is flagged until accepted.
- AC-8: Form view and YAML view stay in sync (edit in one, see it in the other) (UI test against the mock backend).
- AC-9: Steps for AC-1..AC-6 complete with no outbound network connection.

## Out of scope
- Templates menu, hook check, caption/hashtag suggestions (v1.1).
- Cast generation and the library picker's real data (M3; the picker may show an empty state).
- Real-model quality of the structuring (manual check on the Mac with `qwen3:8b`).

## Open questions
- None.
