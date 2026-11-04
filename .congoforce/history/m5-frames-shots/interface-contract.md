# Interface contract — m5-frames-shots

### Settings and config (`reelforge.config`)
- `Settings.shot_mem_gb: float = 16.0`. It has the same validation as `image_mem_gb` (`gt=0`, `allow_inf_nan=False`) and the same precedence (CLI > `REELFORGE_SHOT_MEM_GB` > config.toml `[limits] shot_mem_gb` > default). A non-numeric or non-positive value raises `ConfigError` with `key == "shot_mem_gb"`.
- CLI: `reelforge doctor` and `reelforge serve` accept `--shot-mem-gb FLOAT`.
- `Settings.shot_quality: Literal["draft","final"] = "draft"`. Env `REELFORGE_SHOT_QUALITY`, toml `[runtime] shot_quality`.
- `Settings.shot_draft_size: str = "320x576"` and `Settings.shot_final_size: str = "448x768"`. Format `WxH` with both sides a multiple of 32, otherwise `ConfigError` with `key` equal to the field name. Env `REELFORGE_SHOT_DRAFT_SIZE` and `REELFORGE_SHOT_FINAL_SIZE`, toml `[runtime]`.
- `Settings.shot_timeout_s: float = 1800.0` (toml `[runtime]`) and `Settings.max_clip_mb: int = 100` (toml `[runtime]`, `ge=1`).
- `models.toml` `[models.video]` gains `steps = 8`. Model id, steps and size are never hard-coded elsewhere.

### LTX adapter (`reelforge.adapters.ltx`)
- `REQUIRED_FLAGS: dict[str, tuple[str, ...]]` with exactly:
  - `a2v`: `--prompt --output --audio --image --frame-rate --frames --width --height --model --seed --distilled --low-ram`
  - `generate`: `--prompt --output --image --frame-rate --frames --width --height --model --seed --distilled --low-ram --no-audio`
  - `extend`: `--prompt --output --video --extend-frames --distilled --low-ram --image`
- `parse_flags(help_text: str) -> set[str]` returns every `--long-option` token found in the text (regex `--[a-z0-9][a-z0-9-]*`).
- `LtxAdapter(project_path: Path | None, *, timeout_s: float = 1800.0, sample_interval_s: float = 2.0)`.
  - The executable is `<project_path>/.venv/bin/ltx-2-mlx`, run directly and never via `uv run`.
  - `check() -> HealthReport` (sync, name `"ltx"`). The existing failures stay (path not configured, project not found, no `.venv`). New ones:
    - Executable missing gives `ok=False`, `detail="ltx-2-mlx executable not found in <path>/.venv/bin"`.
    - Runs `[exe, "a2v", "--help"]`, `[exe, "generate", "--help"]` and `[exe, "extend", "--help"]` as argument lists and parses stdout+stderr.
    - Any required flag missing gives `ok=False`, `detail="ltx-2-mlx is missing required options: a2v: --frame-rate; extend: --image"`. The format is subcommand, colon, its missing flags in `REQUIRED_FLAGS` order joined by `, `; subcommands that miss nothing are omitted, the rest are joined by `; ` in the order a2v, generate, extend.
    - A `--help` that cannot run or exits non-zero gives `ok=False`, `detail="ltx-2-mlx could not run '<sub> --help'"`.
    - All present gives `ok=True`.
    - Results are cached per `(exe path, mtime_ns, size)`.
  - `async health() -> HealthReport` (wraps `check` in a thread). `async capabilities() -> {"video"}`.
  - `async run(task, out_dir, progress, cancel, *, ctx_job_id=None) -> list[ProducedFile]` runs one subprocess through `run_command` (timeout `timeout_s`, cancel kills the process tree, RSS sampled).
    - `task.params["mode"]` is `"a2v"` or `"generate"`.
    - `task.input_paths[0]` is the image (`--image`). For `a2v`, `input_paths[1]` is the audio (`--audio`).
    - `generate` always adds `--no-audio`.
    - Always passed: `--prompt`, `--output <out_dir>/out.mp4`, `--frame-rate <params.fps>`, `--frames <params.frames>`, `--width`, `--height`, `--model <task.model.id>`, `--seed`, `--distilled`, `--low-ram`.
    - `--steps N` is added only when `task.model.steps` is set and the subcommand's `--help` lists `--steps`.
    - Exit -9 or 137 raises `AdapterError("Killed, likely out of memory.")`. A timeout raises `AdapterError("Timed out")`. Cancel raises `AdapterError("cancelled")`. Any other non-zero exit raises `AdapterError("ltx-2-mlx failed: <last stderr line>")`.
- `reelforge.doctor.check_ltx(settings) -> CheckResult` keeps key `ltx`, its position in `CHECKS` and severity `blocking`. It returns `status="fail"` with `detail` set to the message above when `check()` fails.

### Job types and worker (`reelforge.frames.state`, `reelforge.shots.state`, `reelforge.jobs.worker`)
- `reelforge.frames.state.FRAME_JOB = "gen_frame"`. Payload: `{"stage": "frames", "scene_id": str, "batch_id": str, "index": int, "total": int}`. The job is heavy with `mem_need_gb = settings.image_mem_gb`. Insufficient memory fails with the existing image message ("... lower image_mem_gb in config.toml.").
- `reelforge.shots.state.SHOT_JOB = "gen_shot"`. Payload: `{"stage": "shots", "scene_id": str, "shot_type": "talking"|"action"|"continue", "quality": "draft"|"final", "batch_id": str, "index": int, "total": int}`. The job is heavy with `mem_need_gb = settings.shot_mem_gb`. Insufficient memory fails with `Not enough free memory for a shot: need {need:.1f} GB (shot_mem_gb), have {free:.1f} GB`.
- Every heavy job runs under the single GPU lease, with Ollama unloaded first (existing `_run_heavy`).
- `reelforge.shots.state.SHOT_OOM_MESSAGE = "Killed, likely out of memory."`. A shot job whose adapter raises an `AdapterError` or `TransientError` whose message contains "killed, likely out of memory" (case-insensitive) fails once, not retried, with `job.error == SHOT_OOM_MESSAGE`.
- Job `result` (a new key only when set):
  - Frame: `{"scene_id", "take_id", "inputs": [artifact ids, master first, then pack if any], "elapsed_s"}`.
  - Shot: `{"scene_id", "take_id", "shot_type", "quality", "width", "height", "frames", "render_s", "inputs": [...], "last_frame_id"}`.
- `Worker` gains `paused_projects: set[str]`. Queued `SHOT_JOB` rows of a paused project are not dispatched; running ones finish.

### Task specs seen by adapters (what `ctx.adapter` / RecAdapter records)
- Frame: `kind="image"`, `prompt`, `input_paths == [master_file] (+ [pack_file])`. The master is the approved cast master of the scene's character (speaker, else first character mentioned, else first story character). `params`: `{"strength": 0.6, "width": 576, "height": 1024}`.
- Talking shot: `kind="video"`, `input_paths == [key_frame_file, active_voice_take_file]`, `params["mode"] == "a2v"`.
- Action shot: `kind="video"`, `input_paths == [key_frame_file]` (no audio input, no audio argument), `params["mode"] == "generate"`.
- Continue shot: `kind="video"`, `input_paths == [previous_shot_last_frame_file]`, `params["mode"] == "generate"`.
- All shots: `params["frames"] ==` the scene's written-back `frames` (8k+1, from `scenes.frames`; if never written, `frames_for(scene.duration or 3.0)`), `params["fps"] == 24`, `params["width"]` and `params["height"]` from the quality size, `task.model == registry.get("video")`.

### Prompt helpers (`reelforge.frames.prompts`)
- `FRAMING_PHRASES: dict[str, str]` with keys `wide`, `medium`, `closeup`.
- `PRODUCT_PHRASE: str`, a request for the real pack in hand or on the table.
- `compose_frame_prompt(*, scene_sentence: str, look: str, framing: str, style: str, other_looks: list[tuple[str, str]], product: bool) -> str`. The result contains `look` verbatim, `FRAMING_PHRASES[framing]`, each other character's look verbatim, and `PRODUCT_PHRASE` only if `product`.

### Artifacts (read through `GET /media/{artifact_id}` and the `artifacts` table)
| kind | owner_type / owner_id | subdir | inputs (ArtifactInput) |
| --- | --- | --- | --- |
| `frame` | `scene` / scene id | `frames/<scene_id>` | master id, then pack id |
| `shot` | `scene` / scene id | `shots/<scene_id>` | frame id and voice take id (talking), frame id (action), previous last_frame id (continue) |
| `last_frame` (PNG) | `scene` / scene id | `shots/<scene_id>/last` | the shot take id it was cut from |
| `product_pack` | `project` / `product` | `product` | none, deduplicated by sha256 |

Uploads write the same kinds with `params.source == "upload"`. Files are stored as `take_NNN.<ext>`, never under the client's file name.

### HTTP (prefix `/api/v1/projects/{project_id}`)
Errors are `{"detail": str}`. Unknown project or scene gives 404. Frames endpoints return 409 "Approve the voices first." when the stage is below VOICES_APPROVED. Shots endpoints return 409 "Approve the key frames first." when it is below FRAMES_APPROVED.

**Frames**
- `GET /frames` returns `FramesOut`:
  ```
  {stage, approved_count, total, stale_count, jobs: [JobOut], frames: [Frame]}
  ```
  `jobs` holds the active (queued or running) frame jobs in story order, each with its payload `index` and `total`.
- Frame card (`Frame`):
  ```
  {scene_id, position, characters: [{key, name}],
   master: {key, name, artifact_id} | null,
   framing: "wide"|"medium"|"closeup",
   state: "no_frame"|"queued"|"rendering"|"ready"|"approved"|"stale"|"failed"|"continue_previous",
   message?: str, prompt: str, prompt_source: "llm"|"user"|"",
   look_removed: bool,
   takes: [{id, take_no, seed, active, approved, stale, source: "render"|"upload", image_url, inputs: [ids]}],
   notes: {second_character?: {master_name, other_name},
           product?: "included"|"missing",
           waiting_for_previous_shot?: true,
           needs_master?: str,
           no_character?: true},
   continue_previous: bool, job: JobOut | null}
  ```
  - `message` is the text of a failed job.
  - `look_removed` is true when the prompt no longer contains the master's look text.
  - `image_url` is `/media/<id>`.
  - `needs_master` carries the character name when no master is approved. Generate then returns 409 "Approve a master for <name> in Cast first".
- `POST /frames:generate` with `{"mode": "missing"|"stale"|"scenes", "scenes"?: [ids]}`:
  - Returns 202 `{"jobs": [JobOut], "skipped": [{"scene_id", "reason"}]}`, one job per scene in story order.
  - Scenes that already have a queued or running frame job are not duplicated.
  - Returns 409 "Nothing to generate." when no job is created.
  - A scene with `continue_previous` or no master is skipped with a reason.
- `POST /frames:cancel` cancels all active frame jobs and returns `{"cancelled": int}`.
- `POST /frames/{scene_id}:generate` returns 202 `JobOut`. It is the "Generate" and "Regenerate" button, and every call makes a new take with a new seed. If a job for the scene is queued or running, that job is returned (duplicate click ignored).
- Actions returning 200 `FrameActionOut = {project_stage, approved_count, total, frame: Frame, job?: JobOut}`:
  - `POST /frames/{scene_id}:approve` makes the active take approved. 409 "This scene has no frame yet." or 409 "This frame is out of date. Make a new frame first." if stale.
  - `POST /frames/{scene_id}:select-take` with `{"take_id"}`. 404 "take not found".
  - `POST /frames/{scene_id}:set-framing` with `{"framing"}`. The frame becomes stale, the LLM-written prompt is rewritten at the next generate, and a user-written prompt is kept.
  - `POST /frames/{scene_id}:save-prompt` with `{"prompt": str, "regenerate": bool = false}`. It stores `prompt_source="user"`. When `regenerate` is true it also enqueues a job and returns `job`.
  - `POST /frames/{scene_id}:continue-previous` with `{"enabled": bool}`.
- `POST /frames/{scene_id}:upload` is multipart field `file`. It returns 201 `FrameActionOut` and the upload becomes a new active take. Errors:
  - 415 "That file is not an image." (PNG/JPEG decided by content, extension ignored; empty files too).
  - 413 "That image is larger than {max_upload_mb} MB."
- Continue-previous and `FRAMES_APPROVED`:
  - A scene with `continue_previous` shows state `continue_previous`, and its key frame is the previous scene's active shot take's `last_frame`.
  - If that does not exist yet, `notes.waiting_for_previous_shot` is set.
  - Such a scene counts as approved for `FRAMES_APPROVED`.

**Shots**
- `GET /shots` returns `ShotsOut`:
  ```
  {stage, engine: {ok: bool, message: str},
   approved_count, total, stale_count, shots: [Shot], queue: Queue}
  ```
  On the mock backend `engine.ok` is true. On the real backend it is `LtxAdapter.check()`; when it fails, `message` is "Video engine check failed - see Settings & status".
- Shot card (`Shot`):
  ```
  {scene_id, position, shot_type: "talking"|"action"|"continue",
   shot_type_auto: str, quality: "draft"|"final", width, height,
   frames: int, shot_length_s: float, motion_prompt: str,
   state: "no_shot"|"queued"|"rendering"|"ready"|"approved"|"stale"|"failed",
   message?: str, oom?: true, can_retry_draft?: true,
   blockers: ["frame_not_approved"|"voice_not_approved"|"waiting_previous"],
   frame_url: str | null,
   takes: [{id, take_no, seed, active, approved, stale, source, quality, video_url, last_frame_id | null, inputs: [ids]}],
   job: JobOut | null}
  ```
  - Blocker texts for the UI are "Approve the key frame first", "Approve the voice take first" and "Waiting for the previous shot".
  - The auto type is talking when the scene has an approved voice take, else continue when `continue_from` is set, else action. A stored override wins.
  - `oom` is true when the newest job failed with `SHOT_OOM_MESSAGE`. `can_retry_draft` is set with `oom` when the shot is not already at Draft size.
- Queue:
  ```
  {paused: bool,
   rows: [{job_id, scene_id, position, shot_type, quality, width, height, status: "queued"|"running", estimate_s: int, estimate_text: "about N min", can_move: bool}],
   total_shots, total_s, total_text, running: {scene_id, index, total, elapsed_s} | null}
  ```
  - `total_text` is exactly `"{n} shots - about {m} min - keep the Mac plugged in"` ("1 shot" when n is 1). `m = max(1, ceil(sum(estimate_s)/60))`.
  - Each row's `estimate_text` is `about {max(1, ceil(estimate_s/60))} min`.
  - The estimate is the mean `render_s` of succeeded `gen_shot` jobs whose result has the same `shot_type`, `width` and `height`; otherwise the built-in `DEFAULT_ESTIMATE_S[(shot_type, quality)]` in `reelforge.shots.state`.
  - A running row has `can_move == false`.
- `POST /shots:render-all` with `{"mode": "missing"|"stale"}` returns 202 `{"jobs": [JobOut], "skipped": [...]}`. Jobs are enqueued in story order with a shared `batch_id`.
  - "missing" covers every shot without an active take.
  - Blocked shots are skipped with reason `frame_not_approved`, `voice_not_approved` or `waiting_previous`.
  - 409 "Nothing to generate." when nothing was enqueued.
  - 409 "Video engine check failed - see Settings & status" when the real engine check fails (no job is created).
- `POST /shots/{scene_id}:render` returns 202 `JobOut`. It makes a new take with a new seed, and an active job for the scene is returned instead (duplicate ignored). Same engine and blocker 409s: "Approve the key frame first.", "Approve the voice take first.", "Waiting for the previous shot."
- `POST /shots/{scene_id}:reroll` is the same, but 409 "This scene has no shot yet." when there is no take. It keeps the prompt and uses a new seed. Only that scene's takes change.
- `POST /shots/{scene_id}:retry-draft` sets the shot's quality to `draft`, enqueues a render and returns 202 `JobOut`.
- Actions returning 200 `ShotActionOut = {project_stage, approved_count, total, shot: Shot, job?: JobOut}`:
  - `POST /shots/{scene_id}:approve`. 409 "This scene has no shot yet." or 409 "This shot is out of date. Render it again first."
  - `POST /shots/{scene_id}:select-take` with `{"take_id"}`.
  - `POST /shots/{scene_id}:set-type` with `{"shot_type"}`.
  - `POST /shots/{scene_id}:set-quality` with `{"quality"}`. Changing type or quality on an existing take makes the shot stale.
  - `POST /shots/{scene_id}:save-prompt` with `{"prompt": str, "rerender": bool = false}`.
  - `POST /shots/{scene_id}:dequeue` removes the scene's queued job.
- `POST /shots/{scene_id}:upload-clip` is multipart field `file`. It returns 201 `ShotActionOut` with a new active take, and its last frame is extracted. Errors:
  - 415 "That file is not a video." (ffprobe must find a video stream).
  - 422 "The clip must be vertical 9:16." (width/height within 1% of 9/16).
  - 422 "The clip must be 20 seconds or shorter."
  - 413 "That clip is larger than {max_clip_mb} MB."
- Queue control, each returning 200 `Queue`:
  - `POST /shots/queue:move` with `{"job_id", "direction": "up"|"down"}`. 409 "That shot has already started." for a running job.
  - `POST /shots/queue:pause`, `POST /shots/queue:resume`.
  - `POST /shots/queue:cancel` cancels all queued rows and the running shot. The running subprocess is killed, the job ends `cancelled`, and no take is added.
- Existing `POST /api/v1/jobs/{id}/cancel` also works on any frame or shot job.

**Staleness and gates (observable through the boards)**
- Frame state `stale` when any of the following holds:
  - a `StoryChange` for the scene with kind `*` or `frame` is newer than the take;
  - the take's recorded `framing`, `look` or `master_id` differs from the current ones;
  - the take is an upload (only the first rule applies to uploads).
- Shot state `stale` when any of the following holds:
  - a `StoryChange` for the scene with kind `*` or `shot` is newer than the take;
  - the recorded `frame_id` differs from the scene's current key frame;
  - for talking, the recorded `audio_id` differs from the scene's current active voice take;
  - the recorded `frames`, `shot_type` or `quality` differs from the current ones.
- Changing one scene's `action` therefore stales only that scene's frame and shot. A new active voice take stales only that scene's talking shot. Nothing enqueues a job on its own.
- `approve` is refused while stale.
- `projects.stage` moves to `FRAMES_APPROVED` iff the stage was at least `VOICES_APPROVED` and every scene's frame is approved or `continue_previous`.
- It moves to `SHOTS_APPROVED` iff the frames condition holds and every shot has an approved active take.
- It drops back one stage when that stops being true. `ASSEMBLED` and `EXPORTED` are never touched.

**Doctor / settings status**: `GET /api/v1/doctor` (existing) check `ltx` as above.

### MockLlm (`reelforge.adapters.mock_llm.MockLlm.chat`)
- A schema with property `scene_sentence` returns `{"scene_sentence": "<Action text from the user message>"}`.
- A schema with property `motion_prompt` returns `{"motion_prompt": "<canned text>"}`.
- No other behaviour changes.

### UI (web, vitest queries by role and text)
Both screens follow `VoiceBoard`. The cards are `role="group"` with `aria-label="Scene <id>"`. Only one board is shown at a time. `ProjectPage` reads `?screen=voices|frames|shots` (default `voices`). The Voices footer button "Continue to key frames" (enabled at `VOICES_APPROVED`) opens `?screen=frames`.

- `web/src/frames/FrameBoard.tsx`: `FrameBoard({projectId}: {projectId: string})`.
  - Section `aria-label="Key frames"`, `h2` "Key frames", list `aria-label="Frames"`.
  - Buttons: "Generate all frames", "Regenerate stale items" (only if `stale_count > 0`), "Cancel" (while jobs are active), "Back to voices", and footer "Continue to shots" (disabled unless stage is `FRAMES_APPROVED` or later).
  - Texts: count `"{approved} of {total} frames approved"`, progress `"Generating frame {index} of {total} - {n} s elapsed"`.
  - Card, per scene:
    - Badge labels: "No frame yet", "Queued", "Rendering", "Ready", "Approved", "Needs update", "Continue from previous".
    - Controls: a framing `<select aria-label="Framing">` with options Wide, Medium, Closeup; `<textarea aria-label="Frame prompt">`; buttons "Save prompt", "Save and regenerate", "Generate" (no take), "Regenerate" (has take), "Approve" (disabled while stale), "Continue from previous" (toggle); file input labelled "Upload replacement"; a takes `<select aria-label="Takes">` ("Take 2 - Active"); an `<img>` of the active take.
    - Notes:
      - "Built from <master>'s master. <Other> is described in the prompt, not copied. Use Upload replacement if the second character looks wrong."
      - "Product pack included"
      - "Product image missing" (amber)
      - "Waiting for the previous shot to be rendered"
      - "Approve a master for <name> in Cast first" (Generate disabled)
      - "No character in this scene"
      - "The character description was removed from the prompt."
      - Failure: "Couldn't generate this frame." plus the reason and a "Retry" button.
- `web/src/shots/ShotBoard.tsx`: `ShotBoard({projectId})`.
  - Section `aria-label="Shots"`, `h2` "Shots", list `aria-label="Shot cards"`.
  - Buttons: "Render all", "Regenerate stale items", "Back to key frames", and footer "Continue to assembly" (disabled unless stage is `SHOTS_APPROVED` or later).
  - Texts: count `"{approved} of {total} shots approved"`. When `engine.ok` is false, Render and Render all are disabled and "Video engine check failed - see Settings & status" is shown.
  - Queue panel (`aria-label="Render queue"`, shown when `queue.rows` is non-empty):
    - It shows the `total_text`, rows `"{position}. {scene_id} - {Type} - {Quality} - {estimate_text}"`, and a status line "Rendering shot {index} of {total} - {n} s elapsed".
    - Buttons per row: "Move up", "Move down", "Remove". Panel buttons: "Pause" (becomes "Resume") and "Cancel".
  - Card, per scene:
    - Header texts: "Talking"/"Action"/"Continue", "Draft"/"Final", "{frames} frames ({shot_length_s} s)" with two decimals (for example "81 frames (3.38 s)").
    - Badge labels: "No shot yet", "Queued", "Rendering", "Ready", "Approved", "Needs update".
    - Controls: `<select aria-label="Shot type">`, `<select aria-label="Quality">`, `<textarea aria-label="Motion prompt">`; buttons "Save prompt", "Save and re-render", "Render", "Play", "Approve", "Re-roll", "Compare takes"; file input labelled "Upload own clip"; takes select.
    - A looping inline `<video aria-label="Shot video">` appears once a take exists. Before that the key frame `<img>` is shown.
    - Compare takes opens a dialog with two takes side by side, each with a looping video and a "Make active" button.
    - Notices:
      - "Approve the key frame first", "Approve the voice take first" (with a "Switch to Action" button), "Waiting for the previous shot".
      - OOM: "Killed, likely out of memory." plus the button "Retry at Draft size" (only if `can_retry_draft`). At Draft size it shows the hint "Close other apps and try again." without the button.
      - Other failure: "Couldn't render this shot." plus the reason and a "Retry" button.
