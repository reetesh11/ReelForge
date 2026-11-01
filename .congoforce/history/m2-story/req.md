---
class: feature
size: large
title: Add Story stage (story.yaml, versions, Ollama structuring, editor UI)
---
# Requirements — Add Story stage (story.yaml, versions, Ollama structuring, editor UI)

## Problem
A ReelForge user needs to turn free-text storyline notes into a validated, editable `story.yaml` (characters, 4–8 scenes, dialogue) and approve it before later stages run. This milestone adds the schema, versioning, local-LLM structuring, import/export and the editing UI on top of the merged M1 backbone (`src/reelforge/` API, jobs, artifacts, `adapters/ollama.py` health-only today, `web/` shell).

## Requirements
- R1. When a `story.yaml` is loaded, the system shall validate it against a Pydantic schema with fields version, title, language, style, aspect, fps, target_seconds, brand_kit, characters, product, scenes, music, captions, as in the Product Spec.
- R2. If a story contains an unknown field or an invalid value, then the system shall reject it with a message naming the field and shall not drop anything silently.
- R3. When YAML is loaded and saved, the system shall parse it in safe mode and preserve comments and key order (ruamel.yaml round-trip); it shall export a JSON Schema for the editor.
- R4. When a story is saved via `PUT /api/v1/projects/{id}/story`, the system shall validate it and create a `story_versions` row, with exactly one marked current.
- R5. When `POST /api/v1/projects/{id}/story:approve` is called, the system shall lock the story and move the project to `STORY_APPROVED`.
- R6. When an approved story is edited, the system shall return the stage to `DRAFT` for the affected items only and mark only their dependants stale.
- R7. The system shall provide an Ollama adapter (`POST /api/chat` with JSON-schema `format`, temperature 0.2–0.4, `keep_alive: 0` when a heavy job is next, default model `qwen3:8b` set in `models.toml`, health via `GET /api/tags`).
- R8. If LLM output fails Pydantic validation, then the system shall run exactly one repair round sending the validation errors back; if still invalid, it shall surface the error and save no story version.
- R9. When `POST …/story:structure` is called, the `structure_story` task shall turn free text (plus optional characters, locations, product placement, dialogue, style, language, target length, library picks) into 4–8 scenes sized to the target, with speakers assigned and character look text in a fixed form.
- R10. If information is missing, then `structure_story` shall return gap questions instead of invented details; dialogue it suggests shall be flagged "suggested" until accepted.
- R11. The system shall load prompts from versioned `prompts/*.md` files with few-shot examples.
- R12. When a valid `story.yaml` is imported, the system shall create a version without calling the LLM; when exported, it shall return the current version byte-for-byte.
- R13. The system shall use a mock LLM returning a canned valid story in tests, and the real Ollama adapter only when selected.
- R14. The Story UI shall provide an input screen (storyline box, collapsible optional boxes, "Structure my story"), inline gap questions, and an editor with a Form view (character and scene cards, reorder, add/delete, running length estimate), a Monaco YAML view with live validation errors, a version list and "Approve story".
- R15. While the editor is open, the Form and YAML views shall stay in sync.

## Acceptance criteria
- AC-1: Given a storyline with 2 characters and 5 scenes on the mock LLM, `story:structure` produces a `story.yaml` that passes schema validation and can be re-saved via PUT as a new `story_versions` row (current flag moves to the new row).
- AC-2: A `story.yaml` with an unknown field (e.g. `foo: 1`) or invalid value (e.g. `fps: "abc"`) is rejected via PUT and import with an error message naming the field; no version is created.
- AC-3: Loading then saving a YAML containing comments leaves comments and key order unchanged (string-equal output).
- AC-4: With an LLM stub returning invalid output, exactly 2 LLM calls occur (original plus one repair containing the validation errors); if the second is invalid, the API returns an error and the version count is unchanged.
- AC-5: After `story:approve` (project state `STORY_APPROVED`), editing one scene via PUT returns the stage to `DRAFT` and marks only that scene's dependants stale; other scenes' items are not stale.
- AC-6: Importing a valid `story.yaml` creates a version with zero LLM calls; export returns bytes identical to the stored current version.
- AC-7: Given input lacking required details, the structure response contains gap questions and no invented values for those fields; suggested dialogue carries a "suggested" flag until accepted.
- AC-8: UI test against the mock backend: editing a field in Form view updates the YAML view text, and editing the YAML updates the form.
- AC-9: AC-1 to AC-6 tests pass with outbound network blocked (the Ollama adapter is not contacted on the mock backend); Ollama adapter unit tests use a stubbed HTTP transport and assert request shape (`format`, temperature in 0.2–0.4, `keep_alive`, model from `models.toml`).
- AC-10: YAML containing an unsafe tag (e.g. `!!python/object`) is rejected, and the exported JSON Schema is served for the editor.

## Out of scope
- Templates menu, hook check, caption/hashtag suggestions (v1.1).
- Cast generation and real library-picker data (M3; empty state allowed).
- Real-model quality of structuring (manual check with `qwen3:8b` on the Mac).

## Assumptions
- `m1-backbone` is merged: project model, state machine, task engine, DB, API skeleton and frontend shell exist; the Ollama adapter currently only does health and unload and is extended here.
- The Product Spec field definitions in the repo root docs are the source of truth for the schema; the Technical Spec wins on design.
- "Affected items" are the scenes/characters changed and what depends on them, per the dependency rules in the Technical Spec.

## Suggested split
1. Story schema and versions: Pydantic `story.yaml`, ruamel round-trip, JSON Schema, `story_versions`, PUT/approve/stale handling, import/export (R1–R6, R12; AC-2, 3, 5, 6, 10).
2. Ollama adapter and mock LLM: adapter, repair round, `models.toml`, mock backend (R7, R8, R13; AC-4, AC-9).
3. `structure_story` task: prompts, gap questions, suggested dialogue, `story:structure` endpoint (R9–R11; AC-1, 7).
4. Story UI: input screen, form and Monaco views, versions, approve (R14, R15; AC-8).

## Open questions
- none
