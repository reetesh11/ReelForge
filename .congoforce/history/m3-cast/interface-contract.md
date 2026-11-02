# Interface contract — m3-cast

All HTTP routes are under the existing FastAPI app (`reelforge.api.app.create_app`). Errors use FastAPI's `{"detail": "<message>"}` body. Tests build the app as in `tests/acceptance/rf_helpers.py`: `make_settings`, `make_ctx(settings, adapter=...)`, `make_client`. The mock LLM is the default (`llm_backend="mock"`).

### Settings (`reelforge.config.Settings`, all optional)
- `backend: Literal["mock","real"] = "mock"`. Widened from `"mock"`. With `"mock"` the cast handler uses `ctx.adapter`. With `"real"` it uses the Draw Things or mflux adapters through the resolver.
- `image_fallback: Literal["none","mflux"] = "none"`. `"mflux"` means mflux is selected in Settings.
- `mflux_command: Path | None = None`. The mflux executable. mflux counts as configured only when `image_fallback == "mflux"` and `mflux_command` is set.
- `max_upload_mb: int = 10` (`>= 1`).
- `drawthings_url` already exists. The port in messages comes from it (default 7860).
- Env: `REELFORGE_BACKEND`, `REELFORGE_IMAGE_FALLBACK`, `REELFORGE_MFLUX_COMMAND`, `REELFORGE_MAX_UPLOAD_MB`. config.toml: `[runtime] image_fallback`, `[runtime] max_upload_mb`, `[tools.mflux] command`.

### Python: adapters
- `reelforge.adapters.drawthings.DrawThingsAdapter(url: str, *, model_id: str | None = None, timeout_s: float = 600.0)`. `name = "draw_things"`, `version = "dt-1"`.
  - `async run(task: TaskSpec, out_dir: Path, progress, cancel: CancelToken, *, ctx_job_id: str | None = None) -> list[ProducedFile]` is the standard `Adapter.run`. It makes exactly one HTTP request per call.
    - Without `task.input_paths`, it sends `POST {url}/sdapi/v1/txt2img`. With them, it sends `POST {url}/sdapi/v1/img2img` and adds `init_images: [base64 of input_paths[0]]` and `strength` (`task.params.get("strength", 0.6)`).
    - JSON body keys: `prompt`, `seed`, `width`, `height`, `steps`, `model`. The `model` value is `task.model.id`. `width`, `height` and `steps` come from `task.params`, defaulting to 576, 1024 and 4.
    - The body never contains `batch_size` or `batch_count`.
    - The response `{"images": [<base64 png>]}` becomes `out_dir/out.png`. The result is `[ProducedFile(path, ext="png", width, height)]`.
  - Errors, all `AdapterError`:
    - Connection failure: exactly `Draw Things isn't reachable on port <port>`.
    - HTTP 422: message `Draw Things doesn't have the model <task.model.id>`.
    - img2img endpoint 404: message `This Draw Things setup can't edit images`.
    - Any other non-2xx status: the message includes the status code.
  - `check() -> HealthReport` keeps its current behaviour for an unreachable server. When `model_id` is set and `GET /` succeeds, it also sends one `POST /sdapi/v1/txt2img` with `{"prompt": "health check", "seed": 0, "width": 64, "height": 64, "steps": 1, "model": model_id}`. A 422 gives `ok=False` with a detail containing `model_id`. A timeout counts as ok. A success is cached per `(url, model_id)` for the process.
  - `health()` and `capabilities()` (`{"image"}`) are unchanged in shape.
- `reelforge.adapters.mflux.MfluxAdapter(command: Path | str, *, timeout_s: float = 600.0)`. `name = "mflux"`, `version = "mflux-1"`. `run(...)` executes, through `run_command` with an argument list and no shell:
  `[command, "--model", task.model.id, "--prompt", prompt, "--seed", str(seed), "--width", str(w), "--height", str(h), "--steps", str(n), "--output", <out_dir>/out.png]`
  For img2img it appends `"--image-path", <path>, "--image-strength", <str(strength)>`.
  - The fake command in tests is any executable that writes a PNG to the `--output` path.
  - A non-zero exit raises `AdapterError`. A cancelled run raises `AdapterError("cancelled")`.
  - It returns `[ProducedFile(path, ext="png", width, height)]`.
- `reelforge.cast.licence.licence_warning(entry: ModelEntry) -> str | None`:
  - Empty `license` returns `"Image model licence is not filled in. Check <entry.id> before commercial use."`.
  - A licence that, lower-cased, contains `non-commercial`, `noncommercial`, `non commercial` or `-nc` returns `"Image model licence: <license> - not for commercial use. See <license_url>."`.
  - Otherwise it returns `None`.

### Doctor / CLI
- `reelforge.doctor.run_doctor(settings)` keeps its 11 check names. The `draw_things` check (blocking) now also validates the pinned `image` model from `settings.models_path` via `DrawThingsAdapter(url, model_id=...)`. If the stub returns 422, the check is `status="fail"` and `detail` contains the model id. `reelforge doctor` then exits non-zero (existing behaviour for blocking failures).
- `GET /health`: body keys are unchanged. When the image model has a licence warning it gains `"image_licence_warning": "<text from licence_warning>"`. The key is absent otherwise.

### HTTP: cast (`/api/v1/projects/{project_id}/cast...`)
- Common errors:
  - Unknown project: 404 `project not found`.
  - Stage is `DRAFT` (story not approved): 409 `Approve the story first.`
  - Unknown story character key: 404 `character not found`.
- `GET /api/v1/projects/{project_id}/cast` returns 200:
  ```
  {
    "stage": "STORY_APPROVED",
    "approved_count": 1,
    "total": 2,
    "image_backend": {"kind": "mock"|"draw_things", "reachable": true, "port": 7860, "mflux_available": false},
    "licence_warning": "<text>",
    "characters": [{
      "key": "tomato", "name": "Tamatar", "aliases": [], "look": "<story look>",
      "bible_line": "<str, empty before first generation>",
      "bible_source": "llm"|"user"|"raw"|"",
      "note": "Using your look text as written.",
      "state": "empty"|"generating"|"ready"|"approved"|"failed"|"stopped",
      "job_id": "<latest cast.generate job id>",
      "progress": {"completed": 2, "total": 4, "elapsed_s": 38.2, "message": "image 2 of 4"},
      "error": "<job error when state=failed>",
      "candidates": [{"id": "<artifact id>", "kind": "generated"|"refine"|"upload", "prompt": "...", "seed": 5,
                      "model": "<models.toml id>", "model_key": "image", "license": "...", "license_url": "...",
                      "image_url": "/media/<id>", "width": 576, "height": 1024}],
      "approved": false,
      "master_artifact_id": "<id>", "master_sha256": "<hex>", "seed": 5, "voice_reference": "",
      "library_character_id": "<cid>", "variant_of_library_id": "<cid>"
    }]
  }
  ```
  - Optional keys are omitted when empty: `licence_warning`, `note`, `job_id`, `progress`, `error`, `master_*`, `seed`, `library_character_id`, `variant_of_library_id`. In candidates, `license` and `license_url` are omitted when empty.
  - `image_backend.kind` is `"mock"` for `backend="mock"` (always reachable). Otherwise it is `"draw_things"`, with `reachable` from `GET /` on the URL. `mflux_available` is true only when mflux is configured.
  - `voice_reference` is always present (a string, possibly `""`).
  - `state="stopped"` means the latest job was cancelled with fewer images than total. `progress.completed` and `progress.total` then give the "Stopped after 2 of 4 images" numbers.
  - A story with no characters returns `characters: []`.
- `POST /api/v1/projects/{project_id}/cast/{key}:generate` takes body (all optional):
  `{"look_text": str, "seed": int, "regenerate": bool, "refine": {"from_candidate": "<artifact id>", "instruction": str}, "backend": "draw_things"|"mflux"}`
  - It returns 202 with a job body (same shape as `story:structure`). The payload includes `"stage": "cast"`, `"key"` and `"total"`.
  - A queued or running `cast.generate` job for the same project and key is returned as-is, so there is no second job.
  - `look_text` stores the edited bible line (`bible_source="user"`). If the character is library-sourced and the text differs from the stored bible line, a linked variant is created first (see Library below).
  - `seed` sets the base seed. Without it, a stable seed is derived from project and key.
  - Seeds: a fresh run uses `s..s+3`. `regenerate=true` continues from the next unused seed and appends 4. `refine` makes one image with the next unused seed using img2img from `from_candidate` and appends it (404 if `from_candidate` is not a candidate of this character).
  - Job lifecycle:
    - The job message is `image n of N` and `result` is `{"candidate_ids": [...], "completed": n, "total": N, "elapsed_s": float}`.
    - A cancelled job (`POST /api/v1/jobs/{id}/cancel`) ends `cancelled` with finished images kept and no further adapter calls.
    - A job that fails because Draw Things is unreachable (and mflux is not usable) ends `failed` with `error == "Draw Things isn't reachable on port <port>"`.
- `POST /api/v1/projects/{project_id}/cast/{key}:approve` takes `{"candidate_id": "<artifact id>"}` and returns 200:
  `{"project_stage": "STORY_APPROVED"|"CAST_APPROVED", "approved_count": n, "total": m, "character": <cast item>}`
  - An unknown candidate (not in this character's candidates) returns 404 `candidate not found`.
  - Approving the same candidate twice is idempotent (no new artifact, no new library row).
  - Approving creates a `cast_master` artifact, saves or updates the library character, and writes `library/characters/<cid>/character.json`.
  - The licence warning never blocks approval.
  - The stage becomes `CAST_APPROVED` when every story character is approved, and a `stage.changed` event is published.
- `POST /api/v1/projects/{project_id}/cast/{key}:reopen` takes no body. It clears this character's approval (the library character is untouched). If the stage was `CAST_APPROVED` it goes back to `STORY_APPROVED`. It returns the same body as `:approve`.
- `POST /api/v1/projects/{project_id}/cast/{key}:use-library` takes `{"character_id": "<cid>"}` and returns the same body as `:approve`.
  - An unknown id returns 404 `That library character no longer exists.`
  - A library character without a master image returns 409.
  - It copies the library master bytes into a new project `cast_master` artifact (same sha256). It copies look text (as `bible_line`), seed and `voice_reference` into the project. It marks the character approved and links `project_characters`. Stage rules are as for `:approve`.
- `POST /api/v1/projects/{project_id}/cast/{key}:upload` takes multipart form with a `file` part. It returns 201 with the cast item.
  - The type is judged by content (PNG or JPEG signature plus a parseable header with width and height). The client filename and content-type are ignored.
  - A non-image, empty or corrupt-header file returns 415 `That file isn't a PNG or JPEG image.`
  - A file over `max_upload_mb` MB, or an image with a side over 8192 px, returns 413 `That image is larger than <max_upload_mb> MB.`
  - Rejected uploads change nothing.
  - On success the file is stored as an artifact (`kind="cast_upload"`) under `<project data_dir>/uploads/` with a generated name `take_NNN.<png|jpg>`. The client name never appears in the path. The character's candidates become exactly `[that artifact]`, with `kind="upload"`.
- Artifact sidecar JSON (`<artifact path>.json`): the candidate and master artifacts include `prompt`, `seed`, `model` (registry key), `model_id`, and `license` / `license_url` when non-empty. M1 sidecars are unchanged.

### HTTP: library
`LibraryCharacter` JSON (the same object is mirrored in `character.json`):
`{"id", "name", "aliases": [], "look_text", "master_image_url": "/api/v1/library/characters/<id>/master", "master_sha256", "seed", "model", "model_id", "created_at", "tags": [], "voice_reference": "", "license", "license_url", "parent_character_id"}`
- `master_image_url`, `master_sha256`, `seed`, `model`, `model_id`, `license`, `license_url` and `parent_character_id` are omitted when empty.
- `GET /api/v1/library/characters` returns 200 with a list of `LibraryCharacter`, ordered by `created_at` then `id`.
- `POST /api/v1/library/characters` takes `{"name": str, "aliases"?: [], "look_text": str, "tags"?: [], "seed"?: int, "voice_reference"?: str, "master_artifact_id"?: str}` and returns 201 with a `LibraryCharacter`. If `master_artifact_id` names an existing artifact, its bytes are copied into the library folder. An unknown one returns 404.
- `GET /api/v1/library/characters/{cid}` returns 200 with a `LibraryCharacter`, or 404 `character not found`.
- `PATCH /api/v1/library/characters/{cid}` accepts only `name`, `aliases` and `tags`.
  - Any other key (for example `look_text`, `master_artifact_id`, `seed`, `model`) returns 400 `Only name, aliases and tags can be changed.`
  - An unknown id returns 404.
  - On success it returns 200 with the updated record and rewrites `character.json`.
- `GET /api/v1/library/characters/{cid}/master` returns the master image bytes (`image/png` or `image/jpeg`), or 404.
- Library rules:
  - Approving saves a library character (name, aliases from the story character, `look_text` = the bible line, master, seed, model, tags `[]`, empty `voice_reference` unless the project has one) and links it in `project_characters`.
  - Re-approving in the same project updates that project-created record (no duplicate).
  - A library-sourced character whose look text is edited, or whose candidate is approved, gets a new library row with `parent_character_id` = the original id and name `"<name> (variant)"`. The original row and its files are never written. The cast item then has `variant_of_library_id` = the original id and `library_character_id` = the variant id, and the UI shows "This changes a library character, so a copy was made."

### Web: routes and components
- `AppRoutes` adds a nav link `Library` (to `/library`) and routes `/library` (`LibraryPage`) and `/library/:characterId` (`LibraryDetail`). Existing links are unchanged.
- `ProjectPage` renders `<CastScreen projectId={...} />` after the story editor whenever `project.stage !== "DRAFT"`. If `GET .../cast` fails, nothing is shown for it.
- `web/src/cast/CastScreen.tsx` is `export function CastScreen({ projectId }: { projectId: string })`. Visible text and roles (exact):
  - Section `aria-label="Cast"` with heading `Cast`. Footer text `N of M characters approved` (for example `1 of 2 characters approved`). If there are no characters: `This story has no characters to cast.`
  - Licence banner (role `status`) with the API `licence_warning` text, shown only when present. It is repeated in the approval confirmation dialog (role `dialog`) with buttons `Approve anyway` and `Cancel` (a permissive licence shows no dialog and approves directly).
  - Unreachable panel (when `image_backend.kind === "draw_things"` and `reachable === false`):
    - Heading text exactly `Draw Things isn't reachable on port <port>`.
    - A `Retry` button that refetches `GET .../cast`.
    - An ordered list with the four steps: `Install Draw Things from the Mac App Store.`, `Open it and turn on the HTTP API server in settings.`, `Set the port to 7860 and keep the app open.`, `Click Retry.`
    - If `mflux_available`: the text `Use mflux instead` as a button, which posts `:generate` with `backend: "mflux"`. Otherwise the string "mflux" appears nowhere on the screen.
    - Generate controls are replaced by this panel; existing candidates and masters stay visible.
  - Rows are `<ul aria-label="Cast characters">` with `<li aria-label="Character: <name>">`.
    - Each row shows the name, aliases, and a textarea labelled `Character bible line`. It has a badge `Approved` or `Not approved`.
    - Empty state: `No candidates yet` and a button `Generate candidates`.
    - Generating state: text `Generating image <n> of <total> - <s> s elapsed` and a `Cancel` button. Elapsed seconds come from the job's `started_at`.
    - Stopped: `Stopped after <n> of <total> images`.
    - Failed: `Couldn't generate images.` plus the error and a `Retry` button.
  - Candidate tiles: `<li aria-label="Candidate seed <seed>">` containing an `<img alt="Candidate seed <seed>">`. Each tile has a radio-style select control `role="radio"` named `Select candidate seed <seed>`, and buttons `Enlarge seed <seed>` and `Compare seed <seed>`. Enlarge opens a `dialog` showing prompt, seed and model.
  - Row buttons: `Approve this one`, `Regenerate 4 more`, `Edit look text and regenerate`, `Refine selected (img2img)`, `Use from library`. There is also a file input labelled `Upload my own image`. `Approve this one` and `Refine selected (img2img)` are disabled until a candidate is selected. Refine shows a text box labelled `What small change?`.
  - Approved row: shows the master image with the `Approved` badge and the buttons `Change approval` (calls `:reopen`) and `Replace from library`. If `library_character_id` is set, the note `From library: <name>` is shown. If `variant_of_library_id` is set: `This changes a library character, so a copy was made.`
  - A top-level button `Use characters from library` opens a picker (dialog) of library characters.
- `web/src/library/LibraryPage.tsx`: `export function LibraryPage()` has heading `Library`, empty text `No characters in your library yet. Approve a cast to save characters here.`, and cards `<li aria-label="Library character: <name>">` that link to the detail and show name, aliases, tags, created date and `Variant of <parent name>` when `parent_character_id` is set.
- `web/src/library/LibraryDetail.tsx`: `export function LibraryDetail()` has fields labelled `Name`, `Aliases` (comma separated), `Tags` (comma separated), and a `Save` button that sends PATCH.
- `SettingsPage` adds a list item `aria-label="Image model licence: amber"` showing the `image_licence_warning` text from `/health`, only when the key is present.
