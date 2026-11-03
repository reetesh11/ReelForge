# ReelForge Phase 1 / M3 — Cast

Binding inputs: `ReelForge — Requirements Document.md`, `ReelForge — Product Spec.md` (Stage 2 Cast, Cast library, Core concepts, Manual edit options for Cast), `ReelForge — Technical Spec.md` (Draw Things adapter and spike S1 finding, mflux fallback, task `gen_candidates`, data model `characters` / `project_characters`, API cast endpoints). The Technical Spec wins on design; the Requirements Document wins on acceptance. Parent: `phases/phase-1-foundation-story-cast.md`. Requires `m1-backbone.md` and `m2-story.md` merged.

## Requirements
- R1. Draw Things adapter over HTTP at the configured URL: `POST /sdapi/v1/txt2img` and `/sdapi/v1/img2img` with `init_images` (base64); health via `GET /`; model pinned from `models.toml` (an unknown model returns 422 and fails `doctor`); one call per image (no `batch_size` / `batch_count` batching; seeds `s, s+1, s+2, s+3` for 4 candidates), progress by elapsed time, cancel between images.
- R2. mflux CLI fallback adapter run as a subprocess in its own uv venv, used when Draw Things is unreachable or lacks a needed mode; selectable in Settings.
- R3. `gen_candidates` task: from a character's look text and the story style, 4 candidates (9:16, plain background, front-facing) as artifacts with prompt, seed and model; look-text normalisation by the LLM into one fixed-format "character bible line", shown and editable.
- R4. Cast screen: one row per story character; candidate grid with enlarge and compare; Approve this one, Regenerate 4 more, Edit look text and regenerate, Upload my own image; "Refine selected" (small edit via img2img keeping the character); seed and prompt kept per candidate.
- R5. Approval creates the master artifact and saves the character to the library (name, aliases, look text, master image, seed, model, created date, tags) with a `character.json` mirror under `library/characters/`; `POST …/cast/{key}:generate`, `:approve`, `:use-library`; stage `CAST_APPROVED` when every character is approved.
- R6. Library: `GET/POST /api/v1/library/characters`, `GET/PATCH /{cid}`; Library screen with cards; "Use characters from library" and "Swap for a library character"; reuse copies the same master image, look text, seed and voice reference into the new project.
- R7. Project-level variants: changing a library character's look in a project creates a linked variant (`parent_character_id`); the library character is never edited by a project.
- R8. Licence handling: a model with a non-commercial or unfilled licence in `models.toml` (FLUX.1 Kontext [dev]) triggers a warning in the Status panel and before approval; recorded in each artifact for later `credits.json`.

## Acceptance criteria
- AC-1: Given an approved cast saved to the library, a second project reuses those characters with identical master image, look text, seed and voice reference.
- AC-2: Editing a character's outfit in a project creates a linked variant and leaves the library character unchanged.
- AC-3: Generating candidates makes exactly 4 image calls with seeds `s..s+3`, each stored as an artifact with prompt, seed and model; the same inputs a second time are served from the cache without calls.
- AC-4: If Draw Things is unreachable the Cast screen shows "Draw Things isn't reachable on port 7860" with Retry and setup steps, and the mflux fallback is offered when configured.
- AC-5: Uploading an own image replaces candidates, is type-checked by content and size-limited, and is stored under `uploads/` with a generated name.
- AC-6: Cancelling candidate generation stops after the current image and keeps the images already made.
- AC-7: The licence warning appears for a non-commercial model and does not block approval.
- AC-8: Steps for AC-1..AC-3 complete with no outbound network connection (mock adapter).
- AC-9: Manual check on the reference Mac with the real adapter: 4 candidates render and one edit via Kontext keeps the character recognisable (human visual check).

## Out of scope
- 3-view character sheets, ensembles, voice design and voice setup beyond storing a voice reference (v1.1 / Phase 2).
- Key frames, product placement, shots.
- Training LoRAs.

## Open questions
- None.
