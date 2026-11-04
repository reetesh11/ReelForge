# Interface contract — m6-assembly

### Python modules (import paths and signatures)

`reelforge.assembly.edl`
- `FPS = 24`, `WIDTH = 1080`, `HEIGHT = 1920`.
- Pydantic v2 models (`extra="forbid"`):
  - `EdlShot(scene_id: str, artifact: str, source_duration_s: float, in_s: float, out_s: float, transition_in_s: float = 0.0)` — `artifact` is the shot take's artifact id. `transition_in_s` is the crossfade with the previous shot (0 = cut; ignored on the first shot; 0 to 0.5).
  - `EdlDialogue(scene_id: str, artifact: str, offset_s: float, duration_s: float, gain_db: float = 0.0)` — `artifact` is the voice take's artifact id; `offset_s` is the start on the reel timeline.
  - `EdlCaption(scene_id: str, speaker: str | None, line_no: int, text: str, start_s: float, end_s: float, style: str | None = None)` — `style` of None means "auto".
  - `EdlMusic(tracks: list[dict[str, Any]] = [], duck: bool = False)` — music slots; always empty in M6.
  - `EdlEndCard(enabled: bool = False, duration_s: float = 1.5, template: str = "default")`.
  - `Edl(version: int = 1, fps: int = 24, width: int = 1080, height: int = 1920, project_id: str, video: list[EdlShot], dialogue: list[EdlDialogue], captions: list[EdlCaption], caption_style: str = "auto", music: EdlMusic, end_card: EdlEndCard)`.
    - JSON field names are exactly these (so `edl.json` has keys `video`, `dialogue`, `captions`, `caption_style`, `music.tracks`, `end_card.enabled`).
    - Properties: `total_frames: int`, `total_duration_s: float`, `shot_start_s(index: int) -> float`.
- `edl_hash(edl: Edl) -> str` — sha256 hex of canonical JSON (sorted keys).
- `load_edl(path: Path) -> Edl`, `save_edl(edl: Edl, path: Path) -> None` (atomic write).
- `CAPTION_PRESETS: dict[str, str]` = `{"bold_pop": "Bold pop", "clean_subtitle": "Clean subtitle", "hindi_devanagari": "Hindi Devanagari"}`; valid `caption_style` values are those keys plus `"auto"`.

`reelforge.assembly.build`
- `build_edl(ctx: AppContext, project_id: str) -> Edl` — one `EdlShot` per scene in story order using the shot slot's approved take (`in_s=0`, `out_s` = take duration, `transition_in_s=0`); one `EdlDialogue` per scene whose line has an approved voice take (`offset_s` = start of that scene's shot, `duration_s` = take duration, clipped so it ends within the reel); one `EdlCaption` per such line (`text` = story line text, `start_s`/`end_s` = dialogue start/end, `line_no` = 1-based order among captions, `speaker` = character display name); `music.tracks == []`; `end_card.enabled is False`; `caption_style == "auto"`. Raises `AssemblyError(409, "Approve all shots before exporting.")` when any scene has no approved shot take.
- `working_edl_path(ctx, project_id) -> Path` = `<data_root>/<project.data_dir>/assembly/edl.json`.

`reelforge.assembly.state` (shared small types)
- `class AssemblyError(Exception)` with `.status: int`, `.message: str`.
- `class StepError(AdapterError)` with `.step: str`, `.reason: str`; `str(exc) == reason`.

`reelforge.assembly.render`
- `PREVIEW_STEPS: list[str]` = `["Preparing shots", "Joining video", "Placing dialogue", "Mixing audio", "Measuring loudness", "Normalising loudness", "Burning captions", "Encoding"]`; `FINAL_STEPS` = `PREVIEW_STEPS + ["Verifying", "Writing cover and credits"]`.
- `@dataclass class RenderHooks: before_step: Callable[[str], None] | None = None; after_step: Callable[[str], None] | None = None` — called around each step (after_step is called after the step is persisted as done). Tests raise a `BaseException` subclass from them to simulate a kill.
- `@dataclass class RenderResult: output: Path; filtergraph: Path; captions_burned: bool; step_runs: dict[str, int]`.
- `async def render_edl(ctx: AppContext, edl: Edl, out_dir: Path, *, profile: Literal["preview", "final"], progress: ProgressCb, cancel: CancelToken, hooks: RenderHooks | None = None) -> RenderResult` — runs the first eight steps (the `PREVIEW_STEPS` names, for both profiles). Outputs `out_dir/preview.mp4` (540x960, libx264 veryfast crf 28, AAC) or `out_dir/final.mp4` (1080x1920, libx264 High crf 18 yuv420p faststart, AAC 192k 48 kHz stereo), and next to it `preview.filtergraph.txt` / `final.filtergraph.txt`. `progress(pct, "<Step name> (<i> of <n>)")` is called at each step start; pct = completed steps / n * 100.
- `out_dir/state.json` after every step: `{"edl_hash": str, "profile": str, "steps": {"<Step name>": {"done": bool, "runs": int}}}`. A step with `done: true` and its output file present is never run again; `runs` counts executions. Partial files are written as `*.part` and renamed only when the step succeeds. A `state.json` whose `edl_hash` differs from the EDL's is discarded and the folder is restarted.
- Errors raise `StepError` with these exact reasons: missing media file `"A shot file is missing: <scene_id>"` at "Preparing shots"; ffmpeg or the `subtitles` filter missing `"ffmpeg is not available or lacks the subtitles filter. Run Settings & status to check."`; font missing `"Devanagari font not found at <path>. Set it in Settings."` at "Burning captions".
- Mock-backend rule: when `ctx.settings.backend == "mock"` and the ffmpeg build lacks the `subtitles` filter, "Burning captions" skips the burn, `captions_burned` is False, and no error is raised. On the real backend it fails as above.

`reelforge.assembly.ffmpeg`
- `def has_filter(name: str) -> bool` — True when `ffmpeg -filters` lists the filter (cached). Tests use it to skip burn-in checks on builds without libass.

`reelforge.assembly.filtergraph`
- `class Filter(name: str, args: list[str] | dict[str, str | int | float] | None = None)`, `class Chain(inputs: list[str], filters: list[Filter], outputs: list[str])`, `class FilterGraph(chains: list[Chain])` with `to_script() -> str` (chains joined by `;\n`, labels as `[label]`, option values escaped for ffmpeg).
- `build_encode_graph(...)`, `build_join_graph(...)`, `build_dialogue_graph(...)`, `build_mix_graph(...)`, `build_loudnorm_graph(...)`: internal helpers used by `render_edl`; their signatures are not part of the contract.

`reelforge.assembly.captions`
- `SAFE_ZONE = SafeZone(top=250, bottom=250, left=64, right=64)` (frozen dataclass; ints, pixels on 1080x1920).
- `resolve_style(caption_style: str, caption: EdlCaption) -> str` — caption's own style, else the EDL style, else when `"auto"`: `"hindi_devanagari"` if the text contains characters in U+0900-U+097F, otherwise `"bold_pop"`.
- `build_ass(edl: Edl, words: dict[str, list[WordTiming]], *, devanagari_font_family: str) -> str` — full `.ass` text. `PlayResX=1080`, `PlayResY=1920`; three styles named `Bold pop`, `Clean subtitle`, `Hindi Devanagari`; every style has `MarginL=64`, `MarginR=64`, `MarginV=250`, Alignment 2 (bottom centre). One `Dialogue:` event per caption with non-empty text, using the resolved style, from `start_s` to `end_s`; the `Bold pop` style uses `\k` karaoke tags per word when `words[scene_id]` is non-empty, otherwise the plain line. Empty caption text produces no event.
- `@dataclass(frozen=True) class WordTiming: text: str; start_s: float; end_s: float` (seconds relative to the start of the audio clip).

`reelforge.assembly.align`
- `class Aligner(Protocol): async def align(self, audio: Path, text: str, language: str) -> list[WordTiming]` — raises `AlignmentError` on failure.
- `class ProportionalAligner` (mock backend): splits the clip duration across whitespace-separated words by character count; deterministic; never fails.
- `class MlxWhisperAligner(settings)`: runs `adapters/align_worker.py` in the mlx-audio environment; model id from `models.toml` key `align`.
- `AppContext.aligner: Aligner` — `AppContext.create(..., aligner: Aligner | None = None)`; default is `ProportionalAligner` when `settings.backend == "mock"`, else `MlxWhisperAligner`. Tests inject a stub.
- A line whose alignment raises, or whose result is empty, gets line-level timing in the `.ass` (no `\k` tags).

`reelforge.assembly.edit`
- `apply_edit(ctx, project_id, op: dict[str, Any]) -> tuple[Edl, list[str]]` — applies one edit to the working EDL, saves it, returns the new EDL and notes (may be empty). Raises `AssemblyError`. Operations (`op["op"]`):
  - `reorder` `{scene_ids: [..]}` — must be a permutation of the current scenes; each dialogue clip keeps its offset relative to its shot start and moves with it.
  - `trim` `{scene_id, in_s, out_s}` — `0 <= in_s < out_s <= source_duration_s`; `out_s - in_s < 0.5` raises 422 `"A shot must be at least 0.5 s long."`. Values are rounded to 0.01 s. Dialogue beyond the new total is trimmed (note `"Dialogue was trimmed to fit."`).
  - `swap_take` `{scene_id, take_id}` — `take_id` must be a shot take of that scene (404 `"take not found"`); `in_s`=0, `out_s`=new take duration, `source_duration_s` updated; dialogue absolute offsets are kept; overflow trimmed with the note above.
  - `set_transition` `{scene_id, seconds}` — 0 to 0.5; capped to half of the shorter adjacent trimmed length with note `"Crossfade shortened to fit"`.
  - `nudge_dialogue` `{scene_id, offset_s}` — absolute offset; 422 `"Dialogue cannot start before 0 or after the end of the reel."` if outside `[0, total_duration_s]`.
  - `set_caption_text` `{scene_id, text}` — changes only `captions[].text` in the EDL; creates no voice take and no job except the debounced preview.
  - `set_caption_style` `{style}` — one of `auto`, `bold_pop`, `clean_subtitle`, `hindi_devanagari` (422 otherwise).

`reelforge.assembly.scheduler`
- `class PreviewScheduler(ctx)`; `ctx.previews: PreviewScheduler`. `touch(project_id)` (called after every edit) restarts a timer of `settings.preview_debounce_s` seconds; when it fires it snapshots the working EDL to `assembly/edls/<hash>.json`, cancels any still-queued `assemble_preview` job of the project, and enqueues one new `assemble_preview` job with payload `{"stage": "assembly", "kind": "preview", "edl_hash": <hash>}` (a running job is left running). `enqueue_now(project_id) -> Job` skips the timer.

`reelforge.assembly.publish`
- `collect_credits(ctx, project_id, edl) -> list[dict]` — one `{"model": <models.toml id>, "version": <revision>, "licence": <licence text>}` per distinct model among the artifacts used (shot takes, their input chains, voice takes), plus the `align` model when the real aligner timed a caption.
- `licence_warnings(credits) -> list[dict]` — the entries whose licence is empty or contains a non-commercial marker (reuse the markers in `cast/licence.py`).
- `publish_version(ctx, project_id, ...) -> ReelVersion` — see Data section; internal.

`reelforge.config.Settings` new fields: `preview_debounce_s: float = 1.0` (ge 0), `devanagari_font: Path = Path("/System/Library/Fonts/Kohinoor.ttc")`, `devanagari_font_family: str = "Kohinoor Devanagari"`. Env: `REELFORGE_PREVIEW_DEBOUNCE_S`, `REELFORGE_DEVANAGARI_FONT`, `REELFORGE_DEVANAGARI_FONT_FAMILY`. config.toml keys under `[runtime]`: `preview_debounce_s`, `devanagari_font`, `devanagari_font_family`.

`reelforge.api.stages`: `STAGE_ORDER` = `[DRAFT, STORY_APPROVED, CAST_APPROVED, VOICES_APPROVED, FRAMES_APPROVED, SHOTS_APPROVED, REEL_EXPORTED, EXPORTED]`; `stages_approved("REEL_EXPORTED") == 6`; `derive_stages` marks "Assembly" `approved` at `REEL_EXPORTED`, and shows `rendering` with `progress` while an `assemble_*` job (payload `stage == "assembly"`) is running, `queued`/`failed` likewise.

Job types (registered in `jobs.worker.HANDLERS`): `"assemble_preview"` and `"assemble_final"` (constants `PREVIEW_JOB`, `FINAL_JOB` in `reelforge.assembly.jobs`). Both enqueued with `heavy=False`, `mem_need_gb=0`, so no GPU lease is taken. Progress message is `"<Step name> (<i> of <n>)"`, n = 8 (preview) or 10 (final). Result (stored in `job.result` when finished): preview `{"edl_hash", "artifact_id", "filtergraph_artifact_id", "captions_burned", "step_runs"}`; final `{"edl_hash", "version", "reel_artifact_id", "step_runs"}`. On failure the handler first sets `result = {"failed_step": "<Step name>"}`, then raises, and `job.error` is the reason text.

### HTTP

Prefix `/api/v1/projects/{project_id}`. Error bodies are `{"detail": "<message>"}`. All 404 `"project not found"` for an unknown project; all 409 `"Approve the shots first."` when the project stage is below `SHOTS_APPROVED`.

- `GET /assembly` → 200 `AssemblyOut`:
  ```
  {
   "stage": str,                       // project stage
   "blocked_reason": str | null,       // "Approve all shots before exporting." when any scene lacks an approved shot take
   "edl": Edl | null,                  // working copy; null until built
   "edl_hash": str | null,
   "shots": [{"scene_id": str, "takes": [{"id": str, "take_no": int, "active": bool, "video_url": str}]}],
   "caption_status": {"<scene_id>": "words" | "line" | "pending"},
   "preview": {"state": "none"|"up_to_date"|"out_of_date"|"pending"|"rebuilding"|"failed",
               "step": str|null, "progress": int|null, "url": str|null, "job_id": str|null,
               "error": str|null, "rebuild_in_s": float|null},
   "export":  {"state": "idle"|"running"|"failed", "step": str|null, "step_index": int|null,
               "step_total": int|null, "progress": int|null, "job_id": str|null,
               "failed_step": str|null, "error": str|null},
   "versions": [{"version": int, "label": "Reel v1", "reel_url": str, "cover_url": str,
                 "created_at": str, "missing": bool}],
   "licence_warnings": [{"model": str, "version": str, "licence": str}],
   "caption_presets": [{"id": str, "label": str}]
  }
  ```
  `preview.state`: `out_of_date` = the latest finished preview is for a different EDL hash and no rebuild is scheduled; `pending` = a debounce timer is running (`rebuild_in_s` set) or a preview job is queued; `rebuilding` = running; `failed` = the last preview job failed and no newer one exists; `up_to_date` = a preview exists for the current hash; `url` is the last good preview (`/media/<artifact_id>`) even when out of date.
- `POST /assembly:build` body `{"force": bool = false}` → 200 `AssemblyOut`. Creates the working EDL (`assembly/edl.json`) when absent, or rebuilds it from the approved takes when `force` is true. Schedules a preview via `ctx.previews.touch`.
- `GET /assembly/edl` → 200 the working `Edl` JSON; 404 `"edl not built"`.
- `POST /assembly:edit` body = one operation object as in `apply_edit` (field `op`) → 200 `{"assembly": AssemblyOut, "notes": [str]}`; 404 `"edl not built"`; 409/422/404 per operation. Calls `ctx.previews.touch`. Never enqueues `assemble_final`.
- `POST /assembly:preview` → 202 `JobOut` (the new or the already queued `assemble_preview` job). No debounce.
- `POST /assembly:export` body `{"accept_licence_warning": bool = false}` → 202 `JobOut` of type `assemble_final`. 409 `{"detail": "Approve all shots before exporting."}` when blocked. 409 `{"detail": "Licence check before export", "licence_warnings": [...]}` when warnings exist and `accept_licence_warning` is false (nothing enqueued). If an `assemble_final` job is queued or running for the project, returns 202 with that job and creates no second one. The export renders the EDL snapshot (`assembly/edls/<hash>.json`) taken at request time.
- `POST /assembly:open-version` body `{"version": int}` → 200 `AssemblyOut`; copies that version's `edl.json` over the working copy; 404 `"This version's files are missing."` if the folder or file is gone; 404 `"version not found"` if no such row.
- Media: unchanged `GET /media/{artifact_id}`: `Accept-Ranges: bytes`; ranged request → 206 with `Content-Range`; unsatisfiable → 416; malformed range → 200 whole file; path resolving outside the data root (also via `..` or symlink) → 403 with no file content. Every preview, final, cover, credits, edl and filtergraph file is an artifact (kinds `preview`, `final`, `cover`, `credits`, `edl`, `filtergraph`).

### Files written (paths relative to `<data_root>/<project.data_dir>/assembly/`)
- `edl.json` working EDL; `edls/<hash>.json` snapshots.
- `work/preview-<job_id>/` and `work/final-<job_id>/`: `state.json`, intermediates, `captions.ass`, `<out>.mp4`, `<out>.filtergraph.txt`.
- `v001/`, `v002/`, ... per exported version: `final.mp4`, `final.filtergraph.txt`, `cover.jpg`, `credits.json`, `edl.json`, `captions.ass`. `credits.json` is a JSON list of `{"model", "version", "licence"}`. The `reel_versions` row has `version` (1, 2, ...), `edl_artifact_id`, `final_artifact_id`, `credits` (same list).
- On success of `assemble_final`: `projects.stage` becomes `REEL_EXPORTED` (only from `SHOTS_APPROVED` or already `REEL_EXPORTED`) and a `stage.changed` event is published.

### UI (vitest, accessible names)
- `Player` (`web/src/player/Player.tsx`): `<Player src: string, label: string, loop?: boolean, muted?: boolean, autoPlay?: boolean, width?: number, fps?: number = 24, showSafeZone?: boolean, controls?: boolean = true />`. The `<video>` has `aria-label={label}`. Controls (buttons, accessible names exact): `Play` / `Pause`, `Previous frame`, `Next frame`, `Loop` (toggle, `aria-pressed`), `Speed` (select with options `0.5x`, `1x`, `1.5x`, `2x`), `Scrub` (range input), `Mute` / `Unmute`, `Safe-zone overlay` (toggle, `aria-pressed`, off by default; when on, an element with `data-testid="safe-zone-overlay"` is present). Frame step sets `currentTime` by exactly `1/24` and pauses; ArrowLeft/ArrowRight on the focused `role="group"` named `<label> player` do the same. While loading: text `Loading video...`; on error: text `Couldn't load this video.` and a `Retry` button that reloads the source.
- `ShotCard` and `CompareTakes` render `Player` with labels `Shot video`, `Active video`/`Compare video` (labels unchanged from today so frozen tests still find them).
- `AssemblyScreen` (`web/src/assembly/AssemblyScreen.tsx`): `<AssemblyScreen projectId: string, onBack: () => void />`, shown at `?screen=assembly`. Button `Back to Shots`. `ShotBoard` gets an optional `onContinue` prop and shows a button `Continue to Assembly` once every shot is approved.
  - Version selector: `<select aria-label="Version">` with options `Editing: working copy`, `Reel v1`, `Reel v2`, ...; selecting a version calls `:open-version`; a version with `missing` shows `This version's files are missing.`
  - Preview badge text: `Preview up to date`, `Out of date - rebuilding in 1 s`, `Rebuilding preview: <step name> (NN%)`, `Preview failed - Retry`; button `Rebuild preview`.
  - Timeline: per shot, buttons `Move <scene_id> earlier` / `Move <scene_id> later`, number inputs `Trim in for <scene_id>` and `Trim out for <scene_id>` (step 0.01), select `Take for <scene_id>`, number input `Crossfade into <scene_id>` (0 to 0.5); per dialogue clip, buttons `Nudge <scene_id> dialogue earlier` / `Nudge <scene_id> dialogue later` (step 1/24 s) and number input `Dialogue offset for <scene_id>`. Edit errors show in a `role="alert"`; notes (`Crossfade shortened to fit`, `Dialogue was trimmed to fit.`) show as plain text.
  - Captions: select `Caption style` (options `Bold pop`, `Clean subtitle`, `Hindi Devanagari`, and `Auto`); per line a text input `Caption for <speaker> line <n>` with placeholder `No caption for this line`, saved on blur; `Aligning captions...` while `caption_status` has `pending` and a preview is rebuilding; `Word timing unavailable - showing the whole line` for `line`.
  - Export: button `Export final` (disabled while `preview.state` is `rebuilding`, an export is running, or `blocked_reason` is set; the reason is shown as text). Progress text `Exporting: <step> (<i> of <n>)`. If `licence_warnings` is not empty, clicking opens `role="dialog"` named `Licence check before export` listing `<model> <version> - <licence or 'Licence not filled in'>`, message `Some models used in this reel are non-commercial or have no licence recorded. Exporting is allowed, but check you may publish this reel.`, buttons `Export anyway` (posts `accept_licence_warning: true`) and `Cancel` (posts nothing). Success text `Exported reel v<n>`; failure `Export failed at <step>. <reason>` with a `Retry` button.
