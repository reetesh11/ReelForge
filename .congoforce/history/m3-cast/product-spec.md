# Product spec — Add Cast stage with Draw Things/mflux adapters and character library

## User-facing behaviour

### Existing surface this builds on
- Project page (`web/src/routes/ProjectPage.tsx`) shows the stage stepper (Story, Cast, Voices, Key frames, Shots, Assembly) and the story editor. The Cast step exists in the stepper; after M3 it becomes usable once the story is approved (`STORY_APPROVED`).
- Settings page (`web/src/routes/SettingsPage.tsx`, heading "Settings & status") lists dependencies as green/amber/red rows, each with a detail line and an optional "Fix: ..." line. This is the "Status panel" named in R14. Draw Things already appears here.
- `reelforge doctor` prints checks with pass/fail and blocking/warning severity.
- API under `/api/v1`, with `:action` suffix routes for story (`story:approve`, `story:structure`) and 202 job responses for long work.
- `models.toml` has `[models.image]` with `license` and `license_url`. The image model is currently Apache-2.0 (FLUX.1 schnell), so by default no licence warning shows. Kontext [dev] is a non-commercial example.
- There is no Library screen, no Cast screen and no `/library` route yet.

### Cast screen (Project page, Cast step)
Reachable from the stepper's Cast step. Locked with the existing locked state until the story is approved.

Layout: one row per story character. Each row shows:
- Character name and aliases.
- The **character bible line** in an editable text box (labelled "Character bible line"), with a status badge: Not approved / Approved.
- A candidate grid of 4 images (9:16 thumbnails). Each tile shows its seed on hover/focus and has two controls: "Enlarge" (opens a larger view with prompt, seed, model) and "Compare" (select up to 2 tiles to view side by side). One tile can be selected at a time as the chosen candidate (keyboard and mouse).
- Actions: **Approve this one**, **Regenerate 4 more**, **Edit look text and regenerate**, **Upload my own image**, **Refine selected (img2img)**, and **Use from library**.
- Approve and Refine are disabled until a candidate is selected. Refine opens a short text box ("What small change?") and then produces a new candidate (appended to the grid, same character, derived from the selected image).

Row states:
- Empty (no candidates yet): "No candidates yet" and a primary "Generate candidates" button.
- Generating: progress shown by elapsed time, e.g. "Generating image 2 of 4 - 38 s elapsed", plus a **Cancel** button. Finished images appear as they complete. Cancel stops after the current image; the finished images stay, and the row says "Stopped after 2 of 4 images".
- Ready: grid with 4 (or more, after Refine) candidates.
- Approved: the master image is shown with an "Approved" badge and the licence line; actions change to "Change approval" (reopens candidates) and "Replace from library".
- Failed: "Couldn't generate images." with the reason and a Retry button; finished images are kept.

Bible line: on the first generation the LLM turns the look text into one fixed-format line (shown in the box). The user can edit it. "Edit look text and regenerate" saves the edited text, and the next generation uses the edited line. If the LLM is unavailable, the raw look text is shown in the box and used, with a note "Using your look text as written."

Stage footer: "Approve cast" is not a separate action. When the last character is approved, the stage becomes `CAST_APPROVED` and the stepper marks Cast approved. A line shows "N of M characters approved".

### Licence warning
When the image model's licence in `models.toml` is non-commercial or empty/unfilled:
- Settings & status shows an amber row/line under Draw Things (or a separate "Image model licence" row) with the text "Image model licence: <licence> - not for commercial use. See <license_url>." For an unfilled licence: "Image model licence is not filled in. Check <model id> before commercial use."
- The Cast screen shows the same warning as a banner above the rows and again in the confirmation shown when the user clicks Approve this one, with buttons "Approve anyway" and "Cancel". Approval is never blocked.
- Every candidate and master artifact stores the licence name and url in its metadata.

### Draw Things unreachable
When the health probe `GET /` fails, the Cast screen shows, in place of the Generate controls:
- Heading text exactly: "Draw Things isn't reachable on port 7860" (the port is taken from the configured URL; default 7860).
- A **Retry** button that re-checks reachability.
- Setup steps: 1. Install Draw Things from the Mac App Store. 2. Open it and turn on the HTTP API server in settings. 3. Set the port to 7860 and keep the app open. 4. Click Retry.
- If mflux is selected in Settings and configured, a line "Use mflux instead" with a button; generation then runs through mflux. If mflux is not configured, no mflux option is shown at all.
Existing candidates and approved masters stay visible and usable while Draw Things is down.

### Upload my own image
Opens a file picker (PNG or JPEG). On success the row's candidates are replaced by the single uploaded image (selected, ready to approve) and the original candidates are no longer shown in the grid. Rejected files show a message and change nothing.

### Library screen
New route "Library" (linked from the main nav). Cards for each library character: master image, name, aliases, tags, created date, and "Variant of <parent name>" when `parent_character_id` is set. A card opens a detail view where name, aliases and tags can be edited (PATCH). Empty state: "No characters in your library yet. Approve a cast to save characters here."

On the Cast screen:
- "Use characters from library" (top of the screen) opens a picker to assign library characters to story characters. "Use from library" / "Swap for a library character" on a row does it for one character.
- Reuse copies the master image, look text, seed and voice reference (opaque, may be empty) into the project. The row becomes Approved with a "From library: <name>" note.
- Editing the look of a library-sourced character in the project (for example the outfit) and regenerating creates a linked variant in the library with a "Variant of" link, and the project switches to the variant. The original library character is never changed. The user sees: "This changes a library character, so a copy was made."

### API
New routes under `/api/v1`; existing shapes only gain fields when non-empty.
- `POST /projects/{id}/cast/{key}:generate` returns 202 with a job body (same shape as `story:structure`). Optional body: `look_text` (edited bible line), `seed`, `regenerate` (true for "4 more"), `refine` (`from_candidate`, `instruction`), `backend` (`draw_things` or `mflux`).
- `POST /projects/{id}/cast/{key}:approve` with `candidate_id`; returns the cast state and the project stage.
- `POST /projects/{id}/cast/{key}:use-library` with `character_id`.
- `GET /projects/{id}/cast` returns characters with bible line, candidates (id, prompt, seed, model, licence, image URL), approval state and licence warning.
- Upload endpoint for own image (multipart), per character.
- `GET /library/characters`, `POST /library/characters`, `GET /library/characters/{cid}`, `PATCH /library/characters/{cid}`. Library fields: id, name, aliases, look_text, master image, seed, model, created date, tags, voice_reference, parent_character_id (omitted when empty).
- The normalised bible line is returned by the cast API for each character.
- Errors use the existing error body shape; unknown character key returns 404; approve with an unknown candidate returns 404; approve before story approved returns 409.

### Files
Approval writes `library/characters/<cid>/character.json` mirroring the library record. Uploads are stored under `uploads/` with a generated name.

## Acceptance criteria
- AC-1: Project A approves its cast; all characters are in the library. Project B uses those library characters through `:use-library`. For each character, master image bytes (same content hash), look text, seed and voice reference in project B equal the library record exactly, and the voice reference is equal even when empty.
- AC-2: In a project with a library-sourced character, editing the outfit in the look text and regenerating creates a new variant whose `parent_character_id` equals the library id. `GET /library/characters/{cid}` afterwards returns the same name, aliases, look text, master image, seed, model, tags and created date as before the edit. The library list gains the variant as a new entry.
- AC-3: With the mock adapter and seed `s`, `gen_candidates` makes exactly 4 image calls with seeds `s, s+1, s+2, s+3`, one call each, in that order. Each result is an artifact whose metadata has prompt, seed and model. A second run with identical inputs (look text, style, seed, model) makes 0 adapter calls and returns the same 4 artifact ids. Changing any input (for example editing the bible line) makes new calls.
- AC-4: With Draw Things unreachable, the Cast screen shows exactly "Draw Things isn't reachable on port 7860", a "Retry" button, and the four setup steps listed above. The mflux option is shown only if mflux is selected and configured in Settings. With mflux not configured, the text "mflux" appears nowhere on the Cast screen.
- AC-5: Uploading a valid PNG or JPEG returns success and replaces the row's candidates with the upload. A file whose content is not PNG or JPEG (for example a text file named `x.png`) is rejected with 415 and "That file isn't a PNG or JPEG image." A file over the limit (default 10 MB, configurable) is rejected with 413 and "That image is larger than 10 MB." Rejected uploads leave candidates unchanged. The stored file is under `uploads/` with a generated name (not the client filename, no client path parts), and the client filename never appears in the stored path.
- AC-6: Cancelling a 4-image run after image 2 completes leaves exactly 2 candidate artifacts, makes no further adapter calls, marks the job cancelled, and the row shows "Stopped after 2 of 4 images". The 2 finished images stay visible and selectable.
- AC-7: With an image model whose licence is non-commercial (or unfilled), the warning text appears in the Settings & status panel and on the Cast screen, and again in the approval confirmation. Approving still succeeds and the character is saved to the library. Every candidate artifact and the master artifact has the licence name and url in its metadata. With a permissive licence no warning shows anywhere.
- AC-8: The flows in AC-1, AC-2 and AC-3 pass with the mock adapter and the mock LLM, with no outbound network connection (tests fail if any non-loopback socket is opened).
- AC-9: Against a stub HTTP server, the Draw Things adapter sends exactly one `POST /sdapi/v1/txt2img` (or `/img2img` with base64 `init_images`) per image. Each request body has the model from `models.toml`, and has neither `batch_size` nor `batch_count`. If the stub returns 422 for the model, `reelforge doctor` reports the image model check as failed (blocking) with the model id in the detail, and exits non-zero.
- AC-10: `:approve` on a character while at least one other story character is unapproved leaves the stage at `STORY_APPROVED`. `:approve` on the last unapproved character sets the stage to `CAST_APPROVED`, and the stepper shows Cast approved. Changing an approval back (reopening a character) moves the stage back to `STORY_APPROVED`.
- AC-11: `GET /projects/{id}/cast` returns for each character a non-empty `bible_line` after generation, produced by the LLM in the fixed format. After the user sends an edited line, the next generation's prompt (recorded in each new artifact) contains the edited line and not the LLM original.
- AC-12: With Draw Things unreachable and mflux selected in Settings, `:generate` produces 4 candidates through the mflux adapter. The adapter runs a subprocess with an argument list and never `shell=True` (verified with a fake command). Candidates record model and licence as for Draw Things. If mflux is not selected, generation fails with the unreachable message and does not start mflux.
- AC-13 (manual, reference Mac, human visual check): With the real Draw Things adapter, 4 candidates render for a character, and one Refine selected (Kontext img2img) edit keeps the character recognisable. The reviewer records pass/fail in the task notes.
- AC-14: All existing M1 and M2 frozen tests pass unchanged. Existing response bodies (projects, stages, story, jobs, health) gain new keys only when they have a non-empty value.
- AC-15 (implied by R12, R9): Approving a candidate creates the master artifact and a library record with name, aliases, look text, master image, seed, model, created date and tags, and writes `library/characters/<cid>/character.json` whose content equals the library record. Approving a character already in the library from the same project does not create a duplicate.
- AC-16 (implied by R6): Candidate progress is exposed as elapsed seconds and "image n of 4" through the job progress and the existing events, not as a percentage of model steps.

## Edge cases and errors
- Story not approved: Cast step is locked; API calls return 409 with "Approve the story first."
- Story has no characters: Cast screen says "This story has no characters to cast." and no rows.
- Generate pressed twice on the same row while a job runs: second request returns the existing job (no duplicate run); the button is disabled.
- Cancel before the first image finishes: 0 artifacts, row returns to its previous state.
- Draw Things goes down mid-run: images already made are kept, the job fails with the unreachable message and Retry resumes with the remaining seeds.
- Draw Things lacks a needed mode (for example img2img): Refine shows "This Draw Things setup can't edit images" and offers mflux only if configured.
- `models.toml` model rejected with 422 at run time: row shows "Draw Things doesn't have the model <id>" and points to Settings; `doctor` fails the same way.
- LLM unavailable for bible line: raw look text used and noted (see above).
- Upload: empty file, zero bytes, corrupt image with a valid header, and images with a wrong extension but correct content (accepted, since type is judged by content) are handled; very large dimensions beyond a sane limit are rejected with the size message.
- Duplicate uploads of the same file replace candidates each time; old uploads stay on disk.
- Approving the same candidate twice is idempotent.
- Editing the story after cast approval: the existing staleness mechanism marks Cast as stale; approved masters are not deleted.
- Variant naming: the variant keeps the name with suffix " (variant)" unless the user renames it.
- Library PATCH may change only name, aliases, tags; look text, master image, seed and model are not patchable (400). Unknown id returns 404.
- Library with 0 characters: empty state above. Use-library on a missing id: 404 and message "That library character no longer exists."
- Offline: generation with the mock adapter needs no network; real adapters talk only to loopback.

## Out of scope
- 3-view character sheets, ensembles, voice design and voice setup beyond storing a voice reference (v1.1 / Phase 2).
- Key frames, product placement, shots.
- Training LoRAs.
- Deleting library characters (no delete endpoint is required).
- Editing the voice reference from the UI.

## Open questions
- Where should the licence warning live: as part of the Draw Things row in Settings & status, or as its own "Image model licence" row? The spec assumes its own row; confirm.
- Is a library character deletion or archive needed in Phase 1? The spec assumes no.
- Should the "Library" nav entry be global (not project-scoped)? The spec assumes a global route.
- Maximum accepted image dimensions for uploads (the spec only fixes the 10 MB limit); please confirm a limit, or leave it to tech-spec.
- When a look change on a library-sourced character is made, should the user be asked before the variant is created? The spec assumes no prompt, only an informational message.
