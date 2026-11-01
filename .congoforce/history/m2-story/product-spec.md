# Product spec — Add Story stage (story.yaml, versions, Ollama structuring, editor UI)

## User-facing behaviour

Today the project page (`web/src/routes/ProjectPage.tsx`) shows the title, the stage stepper and the placeholder "This stage arrives in a later milestone." This milestone replaces that placeholder, for the Story stage, with the Story screens below. The `story.yaml` field definitions in `ReelForge — Product Spec.md` (section "story.yaml format") are the schema source of truth.

### Story input screen (project has no story version yet)
- Large required **Storyline** box.
- Collapsible optional boxes, collapsed by default: Characters, Backgrounds/locations, Product placement, Dialogue, Style, Language (Hindi / English / Hinglish), Target length (seconds, default 12, max 60), and "Use characters from library".
- The library picker shows the empty state "No saved characters yet. They appear here after Cast (coming later)." and never blocks structuring.
- Primary button **Structure my story**, disabled while the Storyline box is empty (whitespace only counts as empty) and while a structuring job is running. While running it shows "Structuring your story…".
- Secondary link **Import story.yaml**: the user picks a file; a valid file creates a version without the LLM and opens the editor.
- No "Start from template" menu (v1.1).

### Gap questions
- If the LLM finds missing information, the result screen lists questions inline, each with a text field, e.g. "What is the potato wearing?", with **Answer** (re-structures with the answers added) and **Skip** per question.
- Fields the user has not answered stay empty or absent in the story; no values are invented for them.
- Questions and the story draft appear together when the LLM produced both. If the draft cannot be valid yet because required details are missing, only the questions appear and no version is saved.

### Suggested dialogue
- When the user gave no dialogue and the LLM proposes lines, each such line shows a "suggested" badge in Form view, and is marked `suggested: true` on the scene in YAML.
- Per line the user can **Accept** (removes the flag) or edit it (editing also accepts it). Approve story is allowed with unaccepted suggestions only after a confirmation: "N lines are still marked suggested. Approve anyway?" (see Open questions).

### Story editor
- Header: title, version selector, running length estimate, **Approve story**.
- Tabs/toggle **Form** and **YAML**. Both always show the same unsaved draft; the draft is saved as a new version with **Save**.
- **Form view**: character cards (key, name, look, voice) with add/delete; scene cards (setting, action, framing, speaker, line, duration, product-in-shot toggle, continue_from, end_card) with drag-to-reorder, add and delete. Top-level fields (title, language, style, aspect, fps, target_seconds, brand_kit, product, music, captions) in a collapsible "Story settings" card.
- **YAML view**: Monaco editor with syntax highlighting, the exported JSON Schema for completion/hover, and live validation errors shown inline and in a list below the editor, each naming the field (e.g. `scenes[2].fps: unknown field`).
- **Running length estimate**: "Estimated length: 11.5 s of 12 s target", sum of scene durations; scenes without a duration are counted as 0 and the text adds "(2 scenes have no duration yet)". Over target shows in amber: "Over target by 1.5 s".
- Reordering scenes keeps scene ids; adding a scene assigns the next unused id (`s6`).
- **Version list** (side panel): "v3 (current)", earlier versions with timestamp and an "Approved" mark where relevant. Selecting an old version opens it read-only with **Restore as new version** (creates a new version; nothing is deleted).
- **Export story.yaml** downloads the current saved version exactly as stored. **Import story.yaml** is also available here and creates a new version.
- **Approve story**: saves nothing new; locks the current saved version and moves the project to Story approved. Disabled with the tooltip "Save your changes first" when the draft differs from the saved version, and disabled while the YAML has validation errors.
- After approval: banner "Story approved. Editing it will mark dependent items for update." Fields remain editable; saving an edit returns the Story stage to Draft (stepper shows Story not approved) and shows the affected items with an amber "needs update" badge.

### Staleness after editing an approved story
Per the Product Spec "Manual edit options" table:
- Editing a scene's `line` makes that scene's voice and shot stale.
- Editing a character's `look` makes that character stale (and, later, key frames/shots using it).
- Editing a scene's other fields makes that scene's items stale.
- Items belonging to unchanged scenes or characters are untouched. In M2 no cast/voice/shot artifacts exist yet, so the visible result is the stage returning to Draft and the dependency record being written; the amber badge appears on any existing dependent artifact.

### API behaviour (user-visible contract)
- `PUT /api/v1/projects/{id}/story` with YAML text: 200 returns the new version (number, current flag); 422 returns errors, each with the field path and message; no version is created on error.
- `POST /api/v1/projects/{id}/story:structure`: returns 202 with a job; on completion the job result holds either a new version, or gap questions (and optionally a draft), or an error.
- `POST /api/v1/projects/{id}/story:approve`: 200 with the project in `STORY_APPROVED`. Approving with no saved story returns 409 "There is no story to approve yet."
- Import and export endpoints for `story.yaml` (paths chosen by tech spec); export returns the stored text unchanged.
- The JSON Schema for the editor is served by the API (path chosen by tech spec).

## Acceptance criteria

- AC-1: With the mock LLM, a storyline naming 2 characters and 5 scenes sent to `story:structure` yields a `story.yaml` with exactly 2 characters and 5 scenes that passes schema validation and is saved as a `story_versions` row marked current. Re-saving the same text (or an edit) via PUT creates a further row; afterwards exactly one row for the project has the current flag, and it is the newest one.
- AC-2: PUT and import both reject a `story.yaml` containing an unknown field (`foo: 1`) or an invalid value (`fps: "abc"`). The response is 422 and each error lists the field path and reason, e.g. "foo: unknown field" and "fps: must be an integer". Nothing is silently dropped or coerced; the version count is unchanged. All errors are reported at once, not just the first. The editor shows the same messages.
- AC-3: Loading then saving a YAML that contains comments, blank-line-free key order and quoting leaves the output string-equal to the input (comments and key order unchanged), whether through PUT or through the form-to-YAML path with no edits.
- AC-4: With an LLM stub that always returns output failing schema validation, exactly 2 LLM calls occur: the original and one repair call whose prompt contains the validation errors. If the repair output is also invalid, the API job fails with a message such as "The model's story didn't match the schema after one repair attempt: <field errors>", the UI shows it with a **Try again** button, and the story version count is unchanged. If the repair output is valid, it is saved and exactly 2 calls were made.
- AC-5: After `story:approve` (project `STORY_APPROVED`), a PUT that changes one scene returns the project stage to `DRAFT`, and only that scene's dependants (per the rules above) are stale; dependants of other scenes and of unchanged characters are not stale. A PUT that changes nothing semantically still creates a version but leaves nothing stale.
- AC-6: Importing a valid `story.yaml` creates a new current version with zero LLM calls and opens the editor on it. Exporting returns bytes identical to the stored current version's text (comments, order, whitespace included).
- AC-7: Given input lacking required details (e.g. no setting for a scene, or an unnamed outfit), the structure result contains gap questions for those items and leaves those fields empty or absent, with no invented values. Dialogue the LLM suggested carries `suggested: true` and the "suggested" badge until the user accepts it; accepting removes the flag on save.
- AC-8: UI test on the mock backend: typing a new value in a Form field (e.g. scene 1 action) updates the YAML view text for that field immediately; editing the YAML text (e.g. changing the title) updates the matching form field. If the YAML is invalid, the Form view keeps the last valid state, shows "YAML has errors; fix them to keep editing in Form view" and does not lose the YAML text.
- AC-9: AC-1 to AC-6 behaviours run with outbound network blocked and the mock backend selected; the Ollama adapter is never contacted. Ollama adapter tests with a stubbed HTTP transport assert the request: `POST /api/chat`, `format` is the story JSON schema, `options.temperature` between 0.2 and 0.4, `keep_alive: 0` only when a heavy job is next (otherwise not 0), `model` from `models.toml` (default `qwen3:8b`). Health uses `GET /api/tags` and reports "Ollama isn't reachable" / "qwen3:8b isn't pulled" with the fix action when failing.
- AC-10: YAML with an unsafe tag (e.g. `!!python/object:os.system`) is rejected by PUT and import with 422 and a message "unsafe or unsupported YAML tag"; no version is created and nothing is executed. The JSON Schema for `story.yaml` is available from the API and is the one the Monaco editor uses for validation and completion.
- AC-11 (implied by R4/R5): Exactly one version per project is current at all times; approving marks the current version approved; an edit after approval creates a new, unapproved current version and the earlier approved version remains in the list.
- AC-12 (implied by R9): The structured story has 4 to 8 scenes whose summed durations are within the target length (default 12 s, up to 60 s); each speaker refers to a defined character key; each character `look` is a single line in the fixed form used by the Product Spec example (shape/colour, features, headwear, outfit).

## Edge cases and errors
- Empty storyline: button disabled; direct API call returns 422 "storyline is required".
- Malformed YAML (syntax error): 422 with line and column; the editor underlines it.
- Empty file imported or PUT with empty text: 422 "story.yaml is empty".
- Invalid values to name: `language` outside hindi/english/hinglish, `aspect` not `9:16` format, non-positive `fps` or `target_seconds`, duplicate scene ids, `speaker` or `continue_from` referencing a missing key, `target_seconds` over 60.
- Ollama down or model not pulled during structuring: job fails with "Ollama isn't reachable on port 11434." (or "qwen3:8b isn't pulled.") and actions Retry and Open setup steps; no version saved.
- LLM output returns more than 8 or fewer than 4 scenes: counts as a validation failure and goes through the single repair round.
- Slow structuring: progress state "Structuring your story…" with elapsed time; the user can leave the page and return, the job continues.
- Unsaved changes when leaving the editor: confirm "You have unsaved changes. Leave anyway?".
- Concurrent save from two tabs: last save wins and creates a version; no data loss because versions are kept.
- Approve while a structure job is running: rejected with 409 "A structuring job is running."
- Unknown project id: 404 "project not found" (existing behaviour).
- Very large YAML (over 1 MB): 413 with a clear message.

## Out of scope
- Templates menu, hook check, caption/hashtag suggestions (v1.1).
- Cast generation and real library-picker data (M3); the picker shows an empty state.
- Real-model output quality (manual check with `qwen3:8b` on the Mac).
- Diff preview before applying LLM changes, and undo/redo across the editor (not required by R1 to R15).
- Voice, key-frame and shot generation, and rendering of stale badges for artifacts that do not exist yet.

## Open questions
- Should Approve story be blocked outright, or allowed after confirmation, while lines are still marked "suggested"? The spec above assumes confirmation.
- Does answering a gap question re-run the full structuring (new version) or only patch the draft? The spec above assumes a re-run producing a new version.
- Should a PUT whose text is identical to the current version still create a new version? The spec above assumes yes (R4: every save creates a row).
