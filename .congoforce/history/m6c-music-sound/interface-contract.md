# Interface contract — m6c-music-sound

### Story schema (`reelforge.story.schema`)
- `Story.audio: list[Cue] | None = None`. The type is strict, so unknown fields are rejected. `Story.music` is unchanged. When `audio is not None` the music block is ignored everywhere (mix, staleness, UI). A story with only `music` loads as before, and a story with both loads.
- `Cue` fields:
  - `id: str`
  - `kind: str`
  - `start: CueTime`
  - `end: CueTime | None = None`
  - `duration: float | None = None`
  - `prompt: str | None = None`
  - `source: str = "generate"`
  - `gain_db: float | None = None`
  - `fade_in_s: float | None = None`
  - `fade_out_s: float | None = None`
  - `duck: bool | None = None`
  - `state: Literal["suggested"] | None = None`. Only `suggested` is ever stored. `draft`, `ready` and `stale` are computed.
- `CueTime`: `{scene: str, at: "scene_start" | "scene_end" = "scene_start", offset: float = 0.0}`. In YAML, `start: { scene: s3, offset: 1.5 }` or `end: { scene: s3, at: scene_end }`.
- A `silence` cue ignores `prompt`, `source` and `duck` if given. `duck` is only meaningful for music.
- Cross-field validation raises `CrossFieldIssues`, so a failed story save returns 422 with `errors[].path = "audio[<i>]"` and these exact messages (`<id>` is the cue id, times in seconds with one decimal):
  - `Cue "gong1": unknown scene "s99".`
  - `Cue "gong1": start must not be negative.` The same wording applies to `end` and `duration`.
  - `Cue "gong1": end (2.0 s) is before start (3.0 s).` A zero-length cue gives `Cue "gong1": end (3.0 s) is not after start (3.0 s).`
  - `Cue "gong1": unknown kind "boom"; use music, sfx, ambience or silence.`
  - `Cue "gong1": id is used more than once.`
  - `Cue "gong1": give either end or duration.`
  - `Cue "gong1": prompt is empty.` Raised only at generation time, not at story validation.
- Times are resolved with the story timeline. Each scene's start is the sum of the earlier scenes' `duration`, using `target_seconds / len(scenes)` for a scene without a duration. `scene_end` is the scene start plus its duration.

### Python modules the tests import
- `reelforge.story.audio`
  - `story_timeline(story: Story) -> dict[str, tuple[float, float]]` — scene id to (start_s, end_s).
  - `resolve_cue(story: Story, cue: Cue, timeline: dict[str, tuple[float, float]] | None = None) -> tuple[float, float]` — absolute (start_s, end_s).
  - `KIND_DEFAULT_GAIN_DB = {"music": -12.0, "sfx": -6.0, "ambience": -18.0}`
- `reelforge.audio.state`
  - `AUDIO_JOB = "gen_audio_cue"`
  - `class AudioError(Exception)` with `.status: int` and `.message: str`.
  - `NEEDS_APPROVAL = "Approve this cue before generating it."`
  - `NOT_AUDIO = "That file is not an audio clip."`
  - `DEFAULT_MIX = {"duck_db": 9.0, "attack_s": 0.15, "release_s": 0.4, "silence_fade_s": 0.08}`
  - `get_mix_settings(ctx, project_id) -> dict[str, float]`
  - `put_mix_settings(ctx, project_id, **values) -> dict[str, float]`
- `reelforge.audio.fit`
  - `async fit_to_length(src: Path, dst: Path, seconds: float, *, crossfade_s: float = 1.0) -> None` — writes a 48 kHz stereo WAV of exactly `seconds` (within 1 ms). A source that is too short is looped with `acrossfade` of `crossfade_s`. A source that is too long is trimmed. It uses an ffmpeg argument list.
- `reelforge.audio.build`
  - `build_audio_section(ctx, project_id, edl) -> tuple[list[EdlAudio], EdlMix, int]` — the cues with absolute times, the mix settings, and the count of cues left out because they have no picked take.
  - `refresh_audio(ctx, project_id) -> Edl | None` — replaces the working EDL's `audio` and `mix`. It returns None and does nothing when no working EDL exists.
- `reelforge.assembly.edl`
  - `class EdlAudio(_Strict)`: `cue_id: str`, `kind: Literal["music","sfx","ambience","silence"]`, `artifact: str | None` (None for silence), `start_s: float`, `end_s: float`, `gain_db: float`, `fade_in_s: float`, `fade_out_s: float`, `duck: bool`. Cue times are absolute reel seconds taken from the EDL shot starts. `scene_end` is the shot start plus the shot length.
  - `class EdlMix(_Strict)`: `duck_db: float = 9.0`, `attack_s: float = 0.15`, `release_s: float = 0.4`, `silence_fade_s: float = 0.08`.
  - `Edl.audio: list[EdlAudio] = []` and `Edl.mix: EdlMix`.
  - `edl_hash` and `save_edl` omit `audio` and `mix` when `audio` is empty, so existing hashes and files are unchanged.
- `reelforge.assembly.filtergraph`
  - `build_mix_graph(edl: Edl) -> FilterGraph`. With `edl.audio` empty it returns exactly today's graph.
  - Otherwise input 0 is the dialogue WAV and inputs 1..N are the cue files, in order of `edl.audio` entries that have an artifact. The output label is `mix`. Each cue is trimmed to its length, scaled by its gain, faded, and delayed to its start.
  - A music cue with `duck` gets the ducking volume expression: drop of `mix.duck_db` dB, with attack and release from `mix`, driven by `edl.dialogue` offsets and durations.
  - All silence cues together gate the music, sfx and ambience bus to zero. Gain goes to 0 over `silence_fade_s` from the cue start, holds to the cue end, and returns over `silence_fade_s` after the end. The bus is mixed with the untouched dialogue.
  - The result is cut at the reel end. The script is written with the existing `-filter_complex_script` path. No shell.
- `reelforge.models_registry`
  - `ModelEntry.max_seconds: float | None = None` (positive).
  - `load_models` raises `ModelLicenceError(ValueError)` when an entry whose key starts with `audio_` has a licence outside `COMMERCIAL_LICENCES = ("MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "ISC", "CC0-1.0", "Unlicense")`, compared case-insensitively. It also raises when the licence is empty.
  - `check_audio_licences(entries: list[ModelEntry]) -> None` is the same check as a function. Building `ModelRegistry([...])` directly does not run it, so tests can inject a non-commercial entry.
- `reelforge.assembly.publish`
  - `collect_credits(ctx, project_id, edl)` keeps its current entries and appends one entry per cue that has an artifact. A generated cue gives `{"cue_id", "kind", "model", "version", "licence"}`. An upload gives `{"cue_id", "kind", "file_name", "licence": "<owner note or empty>"}` with no `model` or `version` keys.
  - `licence_warnings(credits)` also returns audio entries whose model licence is non-commercial or empty, and uploads with an empty note. An upload warning keeps its `cue_id`, `kind`, `file_name` and `licence` keys.
- `reelforge.audio.seed`
  - `suggest_cues(text: str, story: Story) -> list[Cue]` — keyword-based cues, all with `state="suggested"`. Examples that match: "TRACK 2 kicks in", "gong slam", "drum roll", "ceramic crash", "crinkle", "crunch", "complete silence", "ambience".
  - `merge_suggestions(existing: list[Cue], new: list[Cue]) -> list[Cue]` — never removes or edits an existing cue. It skips a suggestion whose id, or whose (kind, scene, prompt), already exists.

### Mock adapter
- `MockAdapter.run` for `TaskSpec(kind="audio")` honours `task.params["duration_s"]` (float) when the `mock` hook has no `duration_s`. It writes a deterministic tone with frequency by `task.params.get("audio_kind")`: music 220 Hz, sfx 880 Hz, ambience 330 Hz. Existing voice behaviour (the `mock` hooks, default 1.0 s) is unchanged.

### HTTP (all under `/api/v1/projects/{project_id}`)
Cue JSON (request and response) uses the schema above. Responses add computed fields.

`GET /audio` → `AudioOut`:
```
{
  "engine": {"ok": bool, "message": str},
  "legacy_music_hint": true,
  "settings": {"duck_db", "attack_s", "release_s", "silence_fade_s"},
  "skipped_count": int,
  "cues": [CueOut]
}
```
- `legacy_music_hint` is omitted when false. It is true when the story has `music` and no `audio`, and the UI shows the hint text then.
- `skipped_count` is omitted when 0. It counts cues with no picked take.
- `CueOut` carries all cue fields plus:
  - `order: int` (1-based).
  - `state: "suggested" | "draft" | "ready" | "stale"`.
  - `start_s`, `end_s`, `duration_s`: resolved seconds.
  - `source`.
  - `licence`: string. Generated cues show the model licence, for example `"Apache-2.0"`. Uploads show `"Your file: <note>"` or `"No licence note"`. It is `""` for silence or when there is no take.
  - `file_name`: string, omitted when empty.
  - `picked_take_id`: string or null.
  - `takes: [{id, take_no, seed, model, prompt, duration_s, url, picked, stale}]`.
  - `job`: the latest `JobOut` for the cue when it is queued, running or failed, else null.
  - `flags: ["ends_after_reel"]`, omitted when empty.

Cue writes (each returns the updated `AudioOut`, status 200, unless noted):
- `POST /audio/cues`
  - Body is a cue. It returns 201 with `AudioOut`.
  - Status 422 with `{"detail": "story.yaml is invalid", "errors": [{path, message}]}` for the validation messages above.
- `PUT /audio/cues/{cue_id}` — full replacement body. Status 404 `cue not found`.
- `DELETE /audio/cues/{cue_id}`
- `POST /audio/cues/{cue_id}:move` — body `{"direction": "up" | "down"}`.
- `POST /audio/cues/{cue_id}:approve` — clears `state: suggested`. It is idempotent.
- `POST /audio/cues/{cue_id}:dismiss` — deletes a suggested cue.
- `POST /audio/cues/{cue_id}:select-take` — body `{"take_id": str}`. It sets the picked take. Status 404 for a take that is not the cue's.
- `PUT /audio/settings` — body is any subset of `{duck_db, attack_s, release_s, silence_fade_s}` (all numbers greater than or equal to 0, `duck_db` at most 40). It returns the settings object. `GET /audio/settings` returns the same.

Generation and files:
- `POST /audio/cues/{cue_id}:generate` → 202 `JobOut` (type `gen_audio_cue`, payload `{"cue_id", "stage": "sound"}`). This is also Re-take.
  - A suggested cue gives 409 `Approve this cue before generating it.`
  - An empty prompt gives 422 `Cue "<id>": prompt is empty.`
  - A silence cue gives 422 `Cue "<id>": a silence cue has no audio.`
  - A file cue gives 422 `Cue "<id>": this cue uses your own file.`
  - A queued or running job for the same cue is returned instead of a new one (still 202, same job id).
  - The job result is `{"cue_id", "take_id", "take_no", "duration_s"}`. Each take is an `Artifact` with `owner_type="audio_cue"`, `owner_id=<cue id>`, `kind="audio_take"`, `prompt`, `seed`, `model_key` and `duration_s` within 50 ms of the cue length on the mock backend, and `params.model_id`. A second take has `take_no == 2`, and take 1 stays listed. The new take becomes the picked one.
- `POST /audio/cues/{cue_id}:upload` — multipart `file` plus optional form field `licence_note`.
  - The content check is `sniff_audio` plus `probe_seconds` from `voice/uploads.py`. The size limit is `settings.max_upload_mb`.
  - A non-audio or empty file gives 415 `That file is not an audio clip.` and creates no take.
  - A file over the limit gives 413 `That clip is larger than <N> MB.`
  - A cue that is not `source: file`, or has no resolvable length, gives 422.
  - On success it returns 201 `AudioOut`. The take is fitted to exactly the cue length, with `model_key="upload"` and `params {"source": "upload", "file_name", "licence_note"}`, and it is picked.

Mix and stale:
- `POST /audio:preview-mix` → 202 `JobOut` (the existing `assemble_preview` job). First it calls `refresh_audio`, so the working EDL carries the current cues and picked takes. If no working EDL exists it builds one. It makes no `vNNN`. It needs stage `SHOTS_APPROVED` or later, else 409 `Approve the shots first.`
- `GET /assembly` (existing) adds `audio_stale: true`, omitted when false. It is true when the working EDL's `audio` or `mix` differs from `build_audio_section`. It also adds `audio_skipped: int`, omitted when 0.
- `GET /stale` (existing) lists the stale cue takes as `{artifact_id, owner_type: "audio_cue", owner_id: <cue id>, kind: "audio_take"}`.
- An edit to a cue's prompt, kind, timing or source, or to the length of a scene it references, writes kinds `["audio_take"]` for that cue only. An edit to gain, fades or duck writes `["audio_mix"]` only. Saving with no cue change writes nothing.
- No cue edit starts a job, and existing `vNNN` folders are untouched.
- `POST /assembly:edit` and `POST /assembly:build` with `force` call `refresh_audio` or `build_edl`, so cue times follow the shots.
- `POST /assembly:export` on a licence problem still returns 409 `{"detail": "Licence check before export", "licence_warnings": [...]}`. The list now includes the audio entries described above.

### Structuring
- After `story.structure` validates a story, `structure_story` carries over the current version's `audio` cues, merges `suggest_cues(storyline + dialogue, story)`, and saves. Suggested cues have `state: suggested` and no job is started. Re-running keeps approved and edited cues. If a carried-over cue now fails validation (for example its scene is gone), the job fails with that cue message and nothing is saved.

### Config
- `Settings.audio_mem_gb: float = 8.0` (key `audio_mem_gb`, same style as `shot_mem_gb`). The job is `heavy` only when `backend != "mock"`.

### CLI and tools
- `python tools/audio_spike.py --out DIR [--backend real|mock] [--models KEY,...] [--table PATH]`. It writes the audio files and a Markdown table with columns `model | cue | duration requested (s) | duration got (s) | accuracy (s) | generation time (s) | peak memory (MB) | loudness (LUFS) | note`. It also prints the table path to stdout and exits 0. `--backend mock` writes tones and needs no model. It reads candidate models from `[candidates.*]` in `models.toml`. Its cues are the three music descriptions, the five screenplay effects and the wedding ambience, at 3 durations each. No new `reelforge` CLI command is added; `reelforge up` and `reelforge doctor` are unchanged.

### UI (`web/`)
- `web/src/sound/SoundScreen.tsx`: `SoundScreen({ projectId, onBack, onContinue }: { projectId: string; onBack: () => void; onContinue: () => void })`.
  - Hooks and types are in `web/src/api/audio.ts` (`useAudio`, `useAudioMutations`). They call the routes above.
- `ProjectPage` shows the screen at `?screen=sound`, after Shots and before Assembly, for stages from `SHOTS_APPROVED`. ShotBoard's continue goes to Sound. Assembly's back goes to Sound.
- `AssemblyScreen` gets an optional prop `backLabel?: string` (default `"Back to Shots"`). `ProjectPage` passes `"Back to Sound"`.
- Visible text and roles the tests query:
  - Heading `Sound` (role heading).
  - Empty state `No sound cues yet. Add a cue or let the structuring step suggest some from your storyline.`
  - Legacy hint `This story uses the old music note. Add cues to design the sound.`
  - Buttons `Add cue`, `Preview full mix`, `Back`, `Next`.
  - Each cue is a `listitem` with accessible name `Cue <id>`. It shows order number, kind, id, `Generate` or `File`, start and duration as `<n> s`, a state badge (`Suggested`, `Draft`, `Ready`, `Needs update`), and the licence text.
  - Row buttons with these `aria-label` values:
    - `Edit cue <id>`
    - `Delete cue <id>`
    - `Move cue <id> up`
    - `Move cue <id> down`
    - `Play <id>`
    - `Re-take <id>` (the label is `Generate <id>` when the cue has no take)
    - `Takes for <id>`
    - `Upload file for <id>` (file cues, a file input)
  - Delete opens a dialog named `Delete cue <id>?` with buttons `Delete` and `Cancel`.
  - The takes list shows `take 1`, `take 2`, a `Play` button and a `Use this take` button per take.
  - Suggested cues show `Approve` and `Dismiss` buttons. `Generate <id>` is disabled until the cue is approved.
  - Add and edit form fields (labels): `Cue id`, `Kind`, `Scene`, `Offset (s)`, `Duration (s)`, `Prompt`, `Source`, `Gain (dB)`, `Fade in (s)`, `Fade out (s)`, `Duck under dialogue`. The submit button is `Save cue`.
  - Project field `Duck amount (dB)`, saved on blur.
  - Notes `Ends after the reel.`, `<n> cues have no audio and are left out of the mix.` and `No licence note`.
  - Generate actions are disabled, with the `engine.message` hint, when `engine.ok` is false.
- `LicenceDialog` (dialog named `Licence check before export`) renders an upload warning as `<file_name> - Licence note not filled in`, and an audio model warning as `<cue_id> <model> <version> - <licence>`. The `Export anyway` and `Cancel` buttons are unchanged.
