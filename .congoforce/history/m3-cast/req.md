---
class: feature
size: large
title: Add Cast stage with Draw Things/mflux adapters and character library
---
# Requirements — Add Cast stage with Draw Things/mflux adapters and character library

## Problem
After the story is written (M2), a ReelForge user needs a consistent look for each character. They must generate candidate images locally, pick or refine one, and save it as a reusable library character. Today `adapters/drawthings.py` is a 35-line stub and no cast, library or licence handling exists.

## Requirements
- R1. When an image is requested, the Draw Things adapter shall call `POST /sdapi/v1/txt2img` (or `/img2img` with base64 `init_images`) once per image, with the model pinned from `models.toml`, and shall not use `batch_size` or `batch_count`.
- R2. When `GET /` on the configured Draw Things URL fails, or a needed mode is missing, the system shall offer the mflux CLI adapter (subprocess with an argument list, own uv venv) if it is selected in Settings.
- R3. If `models.toml` names a model Draw Things rejects with 422, then `doctor` shall fail and report it.
- R4. When `gen_candidates` runs for a character, the system shall produce 4 candidates (9:16, plain background, front-facing) with seeds `s, s+1, s+2, s+3`. Each candidate is an artifact recording prompt, seed, model and licence.
- R5. When `gen_candidates` runs, the system shall have the LLM normalise the look text into one fixed-format "character bible line", shown to the user and editable.
- R6. While candidates are generating, progress shall be reported by elapsed time. When the user cancels, the system shall stop after the current image and keep finished images.
- R7. The Cast screen shall show one row per story character with a candidate grid (enlarge, compare) and the actions Approve this one, Regenerate 4 more, Edit look text and regenerate, Upload my own image, Refine selected (img2img).
- R8. When the user uploads an image, the system shall check its type by content, enforce a size limit, store it under `uploads/` with a generated name, and replace the candidates.
- R9. When a candidate is approved, the system shall create the master artifact, save the character to the library (name, aliases, look text, master image, seed, model, created date, tags), and write a `character.json` mirror under `library/characters/`.
- R10. The API shall expose `POST …/cast/{key}:generate`, `:approve`, `:use-library`, and `GET/POST /api/v1/library/characters` and `GET/PATCH /api/v1/library/characters/{cid}`.
- R11. When every story character is approved, the project stage shall become `CAST_APPROVED`.
- R12. When a library character is reused or swapped in, the system shall copy its master image, look text, seed and voice reference into the project.
- R13. When a project changes a library character's look, the system shall create a linked variant with `parent_character_id` and shall never modify the library character.
- R14. While a model with a non-commercial or unfilled licence in `models.toml` (e.g. FLUX.1 Kontext [dev]) is in use, the system shall show a warning in the Status panel and before approval, without blocking approval, and record the licence in each artifact.
- R15. If Draw Things is unreachable, then the Cast screen shall show "Draw Things isn't reachable on port 7860" with Retry and setup steps, plus the mflux fallback when configured.
- R16. When `gen_candidates` is run again with identical inputs, the system shall serve the artifacts from cache with no adapter calls.

## Acceptance criteria
- AC-1: Given an approved cast saved to the library, a second project that uses those characters gets identical master image, look text, seed and voice reference (compared with the library records).
- AC-2: Editing a character's outfit in a project creates a variant whose `parent_character_id` is the library id. The library character's fields are unchanged afterwards (via `GET /library/characters/{cid}`).
- AC-3: With the mock adapter, generating candidates for seed `s` makes exactly 4 image calls with seeds `s, s+1, s+2, s+3`. Each result is an artifact holding prompt, seed and model. A second run with the same inputs makes 0 calls.
- AC-4: With Draw Things unreachable, the Cast screen shows the text "Draw Things isn't reachable on port 7860", a Retry control and setup steps. The mflux option appears only when configured.
- AC-5: Uploading a PNG or JPEG succeeds and replaces candidates. A file with a wrong content type (for example a text file named `.png`) or over the size limit is rejected. The stored file is under `uploads/` with a generated name, not the client filename.
- AC-6: Cancelling a 4-image run after image 2 leaves 2 artifacts and makes no further adapter calls.
- AC-7: With a non-commercial licence model, the warning shows in the Status panel and before approval, approval still succeeds, and each artifact's metadata includes the licence.
- AC-8: AC-1 to AC-3 pass with no outbound network connection, using the mock adapter.
- AC-9: The Draw Things adapter sends one request per image with the pinned model and no `batch_size` or `batch_count`. An unknown model 422 makes `doctor` fail. Verified against a stub HTTP server.
- AC-10: `:approve` on the last unapproved character sets the stage to `CAST_APPROVED`. Before then, the stage is not `CAST_APPROVED`.
- AC-11: The LLM-normalised bible line is returned by the API and, once edited, is used in the next generation's prompt.
- AC-12: When Draw Things is unreachable and mflux is selected, generation runs through the mflux adapter (subprocess, argument list, no `shell=True`) in tests with a fake command.
- AC-13 (manual, reference Mac, human visual check): with the real adapter, 4 candidates render, and one Kontext edit keeps the character recognisable.
- AC-14: Existing M1 and M2 frozen tests still pass. Existing response shapes gain new fields only when non-empty.

## Out of scope
- 3-view character sheets, ensembles, voice design and voice setup beyond storing a voice reference (v1.1 / Phase 2).
- Key frames, product placement, shots.
- Training LoRAs.

## Assumptions
- M1 and M2 are merged; reuse the job queue, GPU lease, artifact store and fingerprint cache.
- Model IDs live only in `models.toml` and the adapter, per standards.
- A voice reference is stored as an opaque field, possibly empty, in Phase 1.
- The upload size limit is a configurable default (10 MB).
- Tests use the `mock` backend; the real Draw Things check is manual.

## Suggested split
1. **Image adapters and `gen_candidates`**: R1–R6, R16, and the licence recording in R14. Covers AC-3, AC-6, AC-9, AC-11, AC-12.
2. **Cast API, approval and Cast screen**: R7–R11, R15, and the warning UI in R14. Covers AC-4, AC-5, AC-7, AC-10. Needs 1.
3. **Library and reuse**: R12, R13, the library endpoints and Library screen. Covers AC-1, AC-2. Needs 2.
4. **Hardening**: AC-8, AC-13, AC-14 end-to-end checks, plus the Playwright flow.

## Open questions
- none
