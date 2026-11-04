# Product spec — Add Hindi voice-overs (M4 Voice) with OmniVoice, Kokoro fallback and a voice board

## User-facing behaviour

### Existing surface this builds on
- Stage stepper (`web/src/components/StageStepper.tsx`, `src/reelforge/api/stages.py`) already lists Story, Cast, Voices, Key frames, Shots, Assembly. Voices is locked until `CAST_APPROVED`. `VOICES_APPROVED` already exists in the stage order. After M4 the Voices step becomes usable.
- Project page (`web/src/routes/ProjectPage.tsx`) hosts the story and cast screens; the voice board is a new step on it.
- Settings page (`web/src/routes/SettingsPage.tsx`, "Settings & status") is the Status panel. `image_mem_gb` is the model for the new `voice_mem_gb` setting (CLI > env > `config.toml` `[limits]` > default).
- `reelforge doctor` prints blocking and warning checks. `adapters/mlx_audio.py` currently only checks that the environment exists.
- `models.toml` has `[models.tts]` = Kokoro today. Story `Scene` has `line` (text) and an optional `duration` (float > 0), which is the scene's duration budget. Each scene has exactly one line.
- Cast upload checks (type and size by content, generated names under the data root) and the library record with `voice_reference` already exist; voices extend them.
- Job API: long work returns 202 with a job body; `GET /jobs` gains no new keys unless a job has a `result`.

### Voice setup per character
Shown on each character row of the Cast screen and on the Library character detail ("Voice" section). Language is fixed to Hindi (`hi`); no language picker is shown.

A voice has: model, voice id or reference clip, default speed (default 1.0), default language `hi`. Three modes:
- **Preset.** A dropdown of presets for the selected voice model.
  - Kokoro: `hf_alpha`, `hf_beta`, `hm_omega`, `hm_psi`.
  - OmniVoice: a small set of named Hindi voices defined in the adapter (answers.md: implementer chooses; for example one female and one male via the model's voice description option).
  - Each preset has a "Preview" button that plays a short sample.
- **Cloned.** "Upload reference clip" (file picker, audio) plus a required "What is said in the clip" transcript box. Guidance text: "Use a clean 5 to 10 second clip." Saving requires both clip and transcript.
- **Recorded lines.** A mode where no TTS runs for this character: on each of its lines the board offers "Upload recording" instead of generating (see board).

The voice is saved with the character when the cast is approved and goes to the library with it. "Use from library" brings the same voice (model, voice id or reference clip and transcript, speed, language) into a new project. If the library voice's model differs from the project's current `voice_model`, the row shows "Voice made with <model>." and the voice still works as stored; for a preset that does not exist in the selected model the user must pick another preset before generating (line shows "Pick a voice for <character>").
A character without a voice blocks generation for its lines with "Pick a voice for <character>" on those lines; other lines still generate.

Rejections on clip upload (cast-upload style, by content, never by extension or client content type):
- Not audio: 415, "That file isn't an audio clip."
- Over the size limit: 413, "That clip is larger than N MB." where N is the configured limit shown in whole MB. Default limit: 10 MB, configurable like the image upload limit.
- Rejected uploads change nothing. Accepted files are stored under the data root with a generated name; the client filename never appears in the stored path.
- Clip length is not rejected on the 5 to 10 s guidance alone; a clip outside 5 to 10 s is accepted with a visible note "Clips of 5 to 10 seconds clone best." (see Open questions).

### Voice board (Project page, Voices step)
Locked with the existing locked state until the cast is approved. One column per scene, in story order. Each column holds that scene's single line card:
- Speaker avatar (approved master), speaker name, line text, language "Hindi", duration (active take plus pauses, e.g. "3.4 s"), waveform, play button, take count ("2 takes"), state badge (below).
- **Play** plays the active take.
- **Approve** approves the active take.
- **New take** generates another take with a different seed. Prior takes are kept.
- **Edit text and re-take** opens the line text for editing; confirming saves the text to the story line and generates a take.
- **Takes dropdown** lists all takes ("Take 1", "Take 2", ... with duration); exactly one is marked "Active". Choosing another take makes it active (and un-approves the line if it was approved).
- **Speed slider** 0.8 to 1.25 in 0.05 steps, default is the character's default speed, shows "1.00x".
- **Pause before** and **Pause after** numeric inputs/sliders 0 to 1 s in 0.1 s steps, default 0.
- Recorded-lines characters: a single "Upload recording" button replaces New take. An uploaded recording becomes the line's take (trimmed and normalised like generated takes), is checked by content like clip uploads, and can be approved like any take.
- Top bar: **Generate all lines**, **Regenerate stale items** (visible only when something is stale), **Play all**, and "N of M lines approved". Each column header has **Play scene**.
- Footer: **Continue to key frames**, disabled until the stage is `VOICES_APPROVED`.

Line states: No take yet, Queued, Rendering, Ready (take active, not approved), Approved, Stale (amber badge "Needs update"), Failed ("Couldn't generate this line." with reason and Retry; other lines unaffected), Over budget (see below).

Generate all lines: starts one batch job (`gen_voice_take`) with every line that has no active take, in story order. Progress per line: "Rendering line 2 of 5 - 14 s elapsed"; each finished line appears as it completes. Cancel stops the batch; finished takes stay. Lines of a cancelled batch show "Not generated". Lines that already have takes are not re-rendered by "Generate all lines" (use New take).

Play scene plays that scene's active take with its pause before and after. Play all plays every scene's active take in story order with the pauses. Both are previews and do not change state. Lines with no active take are skipped, and the control shows "N lines have no take yet" as a note. Playback stops on a second click.

### Approval and stage
- Approve on a line marks that take approved. When every line has an approved active take, the project stage becomes `VOICES_APPROVED`, the stepper marks Voices approved, and "Continue to key frames" unlocks. A line shows "N of M lines approved".
- Editing the text of an approved line reopens only that line (state returns to needs a take or stale) and the project stage leaves `VOICES_APPROVED` (back to `CAST_APPROVED`). Other approved lines stay approved.

### Shot length write-back
On approval, the active take's duration including pause before and after is written to the scene as its shot length: `frames = 8 * ceil((duration * 24 - 1) / 8) + 1` at 24 fps (frames are always `8k + 1`). Examples: 2.9 s gives 73 frames; 3.32 s gives 81 frames. The line card shows "Shot length: 73 frames (3.04 s)" after approval. Changing the active take, speed or pauses of an approved line re-opens it; the new approval rewrites the shot length.

### Over budget
If the active take's duration including pauses exceeds the scene's `duration`, the line card shows an amber flag: "This line is 4.2 s but the scene allows 3.0 s." with three suggestions as buttons: **Speed up** (sets speed to the smallest 0.05 step, within 1.25, that fits; if none fits it says "Even at 1.25x this is too long." and sets 1.25), **Shorten text** (asks the LLM for a shorter line, shows it as a proposal the user accepts or dismisses; if the LLM is unavailable it says "The language model isn't available. Edit the text yourself.") and **Extend scene** (sets the scene `duration` to the line's length rounded up to 0.5 s). The flag never blocks approval. Scenes without a `duration` are never flagged.

### Staleness
- Changing a line's text marks that line's voice take and that scene's shot length stale. No other scene is stale. Nothing regenerates automatically.
- Stale items carry an amber "Needs update" badge. The old take stays playable.
- **Regenerate stale items** enqueues one `gen_voice_take` batch job for just the stale lines in story order. Stale shot lengths are refreshed when their line is re-approved.
- Changing a character's voice marks that character's lines stale in the same way.

### Settings and Status panel
- New setting `voice_model`: `omnivoice` (default) or `kokoro`. A selector on Settings & status ("Voice model: OmniVoice / Kokoro (fallback)") and in `config.toml`.
- The Status panel names the model in use, e.g. "Voice model: OmniVoice (mlx-community/OmniVoice-bfloat16)", and the mlx-audio row shows environment health.
- New setting `voice_mem_gb` (float, default 4.0, `[limits]`): CLI > env > `config.toml` > default. Non-positive values are rejected with a message naming `voice_mem_gb` (same style as `image_mem_gb`).
- No licence warning shows for either voice model (both Apache-2.0).
- `models.toml`: `[models.tts]` = `mlx-community/OmniVoice-bfloat16`, `revision = "unpinned"`, Apache-2.0, with a licence URL; a separate fallback entry (name chosen in design) = `mlx-community/Kokoro-82M-bf16`, Apache-2.0, with a licence URL.

### Doctor
New blocking check named "mlx-audio voice engine":
- Pass: environment exists and `tts_worker.py --selftest` renders a WAV and exits 0. Detail: "mlx-audio ready (selftest passed)".
- Fail (blocking): environment missing, "mlx-audio project not found at <path>" with a "Fix:" line (create the arm64 uv environment; pin `cpython-3.12-macos-aarch64-none`); or selftest non-zero/timeout, "tts_worker selftest failed: <first line of error>".
It appears in the Settings & status panel as a row with the same text.

### Memory and GPU
The voice job takes the GPU lease, unloads Ollama first, and checks available memory against `voice_mem_gb`. If available memory is lower the job fails before starting, with: "Not enough free memory for voice: need <voice_mem_gb> GB, have <N> GB. Lower voice_mem_gb or close other apps." The board shows this as the failed state with the reason. Only one heavy job holds the lease at a time; a voice job waits (state "Queued") while another heavy job runs.

### Worker and engine behaviour (user-visible effects)
- One batch is one worker process, one model load. Per-line errors fail only that line.
- Each finished take is normalised: silence trimmed at both ends, -16 LUFS, 48 kHz WAV.
- Speed within 0.8 to 1.25 is applied. Speed or pauses outside the ranges are rejected with 422 and a message naming the field: "speed must be between 0.8 and 1.25" and "pause_before must be between 0 and 1 seconds" (same for `pause_after`).
- On the `mock` backend everything works offline with short deterministic WAVs.

### API (user-visible shape, details are tech-spec's)
New routes under `/api/v1`, `:action` style, existing shapes unchanged except fields added only when non-empty:
- `GET /projects/{id}/voices`: characters' voices and the lines with takes (id, seed, duration, active, approved, stale), speed, pauses, state, over-budget info, and the stage.
- Set/clear a character voice; upload a reference clip (multipart); upload a recorded line (multipart).
- `POST /projects/{id}/voices:generate` (202, job), with `lines` optional (stale regeneration or one line).
- Line actions: new take, select active take, approve, edit text, set speed and pauses.
- Preview stitch of active takes for a scene or all scenes (audio).
Errors use the existing body shape: unknown line 404; actions before cast approved 409; invalid speed/pause 422; bad upload 415/413.

## Acceptance criteria
- AC-1: A project with 5 dialogue lines (one per scene) is rendered; line 3 is re-taken so it has two takes and the second is active. After approving line 3, the scene's shot length equals the frame math applied to the second take's duration including pauses, not the first take's. Re-selecting the first take as active and re-approving writes the first take's value.
- AC-2: With 5 approved lines, editing the text of line 2 marks exactly that line's voice take and scene 2's shot length stale. Scenes 1, 3, 4, 5 have no stale item and keep their approvals. No generation job is created by the edit.
- AC-3: `frames(duration) = 8 * ceil((duration * 24 - 1) / 8) + 1` for every duration > 0; the result is always `8k + 1` for an integer k >= 1 (property test over durations). Exactly: 2.9 s gives 73 and 3.32 s gives 81. Minimum-frame behaviour for tiny durations is an open question.
- AC-4: `tts_worker.py` on a 3-line JSONL batch with a stub model writes 3 24 kHz mono WAVs and prints exactly 3 progress JSON lines (`id`, `path`, `duration_s`) in one process, loading the model once. With one failing line, that line's progress line has an `error` (no valid WAV required) and the other two succeed and exit status of the batch is 0. `--selftest` writes a one-word WAV and exits 0; `--backend mock` writes short deterministic WAVs (identical bytes for identical input) with no model and no network. The worker imports only numpy and mlx-audio, never `reelforge`.
- AC-5: Tones and silence run through the adapter's ffmpeg post-processing produce 48 kHz WAVs whose integrated loudness is -16 LUFS within 1 LU, with leading and trailing silence removed (no more than 0.1 s remains at either end) and the tone body kept, without any model. Speed uses the worker argument where the model has one and ffmpeg `atempo` otherwise; the output duration scales by 1/speed within 5 %.
- AC-6: `reelforge doctor` reports a blocking failure "mlx-audio voice engine" when the mlx-audio environment is missing or `--selftest` fails (non-zero exit or timeout), and passes when the environment exists and selftest exits 0. Exit code of `doctor` is non-zero on the blocking failure.
- AC-7: Packaged `models.toml` has OmniVoice (`mlx-community/OmniVoice-bfloat16`, Apache-2.0, licence URL) as `[models.tts]` and Kokoro (`mlx-community/Kokoro-82M-bf16`, Apache-2.0) as a separate fallback entry. With `voice_model` unset, the batch the adapter writes names the OmniVoice id; with `voice_model = "kokoro"` it names the Kokoro id. No licence warning shows in Settings or on the Voices screen for either. The Status panel shows "Voice model: <name> (<id>)" for the one in use. An unknown `voice_model` value is rejected with a message listing `omnivoice` and `kokoro`.
- AC-8: Approving the cast with a character that has a voice stores that voice (model, voice id or reference clip and transcript, speed, language `hi`) in the library record. A second project that uses that character through the library gets equal voice settings and the same reference clip (same content hash). A clone upload of a non-audio file (for example a text file named `x.wav`) is rejected with 415 and "That file isn't an audio clip."; an oversized file is rejected with 413 and "That clip is larger than 10 MB."; both leave the voice unchanged. An accepted file is stored under the data root with a generated name that does not contain the client filename.
- AC-9: Speed below 0.8 or above 1.25 is rejected (422, "speed must be between 0.8 and 1.25"); 0.8 and 1.25 are accepted. A pause before or after below 0 or above 1 is rejected (422, "pause_before must be between 0 and 1 seconds", same for `pause_after`); 0 and 1 are accepted. For valid values, the duration written to the scene equals the take's duration plus pause before plus pause after, then frame math.
- AC-10: A voice job started with available memory below `voice_mem_gb` fails before the adapter runs, with a message that contains `voice_mem_gb`; with enough memory it runs. Only one heavy job holds the GPU lease at a time and Ollama is unloaded first (same behaviour as image jobs). `voice_mem_gb` precedence is CLI > env > `config.toml` `[limits]` > default 4.0, and zero, negative and non-numeric values are rejected with a message naming `voice_mem_gb`.
- AC-11: `VOICES_APPROVED` is reached only when every line has an approved active take (4 of 5 approved leaves the stage at `CAST_APPROVED`; approving the fifth moves it). Editing an approved line's text reopens only that line, leaves the other approved lines approved, and moves the stage out of `VOICES_APPROVED`.
- AC-12: AC-1 to AC-4 run on the `mock` backend with outbound network connections blocked, and succeed.
- AC-13: Manual (human listening on the reference Mac), result recorded in `docs/manual-checks.md`: 5 real Hindi lines render with correct pronunciation with OmniVoice and with Kokoro; one cloned voice from a real 5 to 10 s Hindi clip is judged recognisable, or is recorded as not working and listed as a known limitation. Not automated.
- AC-14: All frozen M1 to M3c tests pass unchanged. `GET /jobs` and other existing responses gain no new keys, except a job that has a `result` may carry it.

## Edge cases and errors
- Empty board: before generation each line shows "No take yet"; "Generate all lines" is primary.
- Character with no voice: its lines show "Pick a voice for <character>"; generate skips them and reports which were skipped.
- A line with empty text: not generated; shown as "No dialogue" and does not count toward "N of M lines approved". If no scene has text, whether the stage advances automatically is an open question.
- Failure of one line in a batch: that line shows Failed with the worker's error; others keep their takes; Retry regenerates only it.
- Worker timeout or crash: the job fails with "Voice engine stopped: <reason>"; takes finished before the crash are kept.
- Cancel mid-batch: finished takes stay; the job is cancelled; lines not rendered return to their previous state.
- Double click on New take: one take per click is queued; they run one at a time.
- Concurrent edit while rendering: the text edit is saved; the in-flight take for the old text is stored but marked stale.
- Story approved text edited upstream (via story editor) after voices exist: handled as staleness above; the story editor's own flow is unchanged.
- Speed or pause changed on an approved line: line reopens; change applies to the next take or re-processing (UI says "Apply" to re-process the active take with the new speed; speed changes re-render the post-processing, not necessarily a new TTS call; design decides).
- Reference clip missing on disk when generating: line fails with "Reference clip for <character> is missing. Upload it again."
- Mixed models: library voice for a model other than the current `voice_model` shown as above; never silently switched.
- Offline: all voice work on the mock backend makes no network calls; a real backend uses no network after models are downloaded.

## Out of scope
- Voice design from text, emotion hints, English voices, other selectable TTS models (v1.1).
- Key frames, shots, lip-sync rendering (M5); assembly, captions, word-level timings (Phase 3).
- Testing real voice cloning in automated tests (manual only; stub in tests).
- Recording in the browser (only upload of an existing clip or recording).
- Multiple lines per scene.

## Open questions
- Reference clip length: should a clip outside 5 to 10 s be rejected (hard limit) or accepted with the note proposed here?
- Frame math lower bound: for durations at or below 1/24 s the formula gives `8*0+1 = 1` frame (or less for tiny values); should the minimum be clamped (for example to 9 frames) or is 1 acceptable?
- If a project has no dialogue lines at all, should the stage auto-advance to `VOICES_APPROVED` or require an explicit action?
- Speed or pause change on an approved line: confirm it reopens the line and rewrites shot length on re-approval (as proposed here), rather than applying silently.
- Clone upload size limit default of 10 MB (matching image uploads): confirm, or choose a smaller value for short clips.
