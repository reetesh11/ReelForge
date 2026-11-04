# Interface contract — m6b-voice-emotion-age

### Python modules (importable)
- `reelforge.story.markup`
  - `EMOTIONS: tuple[str, ...] == ("happy", "sad", "fear", "anger")`.
  - `check_emotion(value: str | None) -> str | None` — returns the value or `None`; raises `ValueError('Unknown emotion "joy". Use one of: happy, sad, fear, anger.')`.
  - `@dataclass(frozen=True) Segment(text: str, emotion: str | None)`.
  - `parse_segments(raw: str) -> list[Segment]` — splits `Tum kahan ho? <sad>Mujhe akela chhod diya.</sad>` into unmarked and marked segments in order (whitespace-only segments dropped). Raises `ValueError` with the unknown-emotion message for any other tag-like `<name>` (for example `<joy>`), and `ValueError("Emotion markup is not valid: close every <emotion> tag and do not nest them.")` for unclosed, nested or empty (`<sad></sad>`) markup. Typed `[...]` tags are kept in segment text.
  - `display_text(raw: str) -> str` — markup and every `[...]` tag removed, whitespace collapsed, stripped.
  - `speech_text(raw: str) -> str` — markup removed, `[...]` tags kept.
- `reelforge.story.age`
  - `AGE_ERROR == "Age must be a whole number from 1 to 120."`
  - `check_age(value: object) -> int | None` — `None` stays `None`; int 1..120 returned; bool, float, str, 0, 121, negative raise `ValueError(AGE_ERROR)`.
  - `age_band(age: int) -> str` — `child` (<=12), `teenager` (13-19), `young adult` (20-39), `middle-aged` (40-59), `elderly` (>=60).
- Story schema (`reelforge.story.schema`): `Scene.emotion: str | None = None` (validated by `check_emotion`), `Character.age: int | None = None` (validated by `check_age`). A story PUT with an invalid emotion, age or markup in `line` is rejected through the existing story validation error response (status 422) and nothing is saved; the error text contains the messages above.
- `reelforge.voice.mapping`
  - `load_mapping(path: Path) -> Mapping`; `Mapping.rule(emotion: str) -> EmotionRule | None`; `Mapping.phrase_gap_ms: int`; `Mapping.kokoro_age(band: str) -> KokoroAge | None`.
  - `EmotionRule(tags: list[str], tag_position: Literal["prefix","suffix"], pitch: str, duration_scale: float, generation: dict[str, float], post: PostSettings)`; `PostSettings(semitones: float = 0.0, gain_db: float = 0.0, pause_s: float = 0.0, tempo: float = 1.0)`.
  - Mapping file format (TOML), the single table, packaged at `src/reelforge/voice/emotions.toml`, seeded from section 9 of `docs/voice-levers.md`:
    ```toml
    [phrase]
    gap_ms = 150
    [emotion.sad]
    tags = ["[sigh]"]
    tag_position = "prefix"
    pitch = "low pitch"          # an OmniVoice instruct pitch value, or ""
    duration_scale = 1.25
    [emotion.sad.generation]     # optional, passed to model.generate
    guidance_scale = 2.0
    [emotion.sad.post]
    semitones = -2.0
    gain_db = -3.0
    pause_s = 0.0
    [kokoro_age.elderly]         # experimental
    prefer = ["hm_omega", "hf_alpha"]
    semitones = -1.0
    ```
    One `[emotion.<name>]` table per emotion in `EMOTIONS`. Tests must never assert specific values from the packaged file, only direction (happy `post.semitones` higher than sad; fear `duration_scale` lower than sad) and that a rewritten file changes the next take.
- `reelforge.config.Settings.emotion_mapping_path: Path` (default the packaged `emotions.toml`; config.toml key `emotion_mapping_path` under `[paths]`). The file is re-read on every generation and board build, so a test edits the file at that path and the next take uses it.
- `reelforge.adapters.mlx_audio`
  - `postprocess_wav(src: Path, dst: Path, *, atempo: float | None = None, semitones: float = 0.0, tempo: float = 1.0, gain_db: float = 0.0, timeout_s: float = 120.0, cancel: CancelToken | None = None) -> float` (async, returns duration; existing arguments keep their behaviour). Pitch/tempo run `rubberband=pitch=<2^(st/12)>:tempo=<t>`; gain is added to the `volume` filter after loudness normalisation. All through `run_command` argument lists. When `semitones != 0` or `tempo != 1.0` and the filter is absent, raises `AdapterError('ffmpeg is missing the "rubberband" filter, needed for pitch and tempo changes. Install ffmpeg-full.')`; nothing is skipped.
  - `ffmpeg_has_filter(name: str) -> bool` — runs `ffmpeg -hide_banner -filters`; no cache (tests may monkeypatch it to return `False`).
  - `VoiceLine` gains optional fields (defaults keep current constructors valid): `instruct: str | None = None`, `duration_scale: float = 1.0`, `semitones: float = 0.0`, `tempo: float = 1.0`, `gain_db: float = 0.0`, `generation: dict[str, float] = {}`. `VoiceResult` gains `duration_requested_s: float | None = None`.
  - `plan_speed` is unchanged (frozen). `run_batch` for `omnivoice` writes row `speed: 1.0` (as now) and no longer applies `atempo`.
- Worker batch rows (`batch.jsonl`, visible through the existing `wrap_worker` log): existing keys unchanged plus `instruct: str | None`, `duration_scale: float`, `target_speed: float` (the effective speed for OmniVoice, `1.0` for Kokoro), `gen: dict`. One row per phrase: id is the scene id for a single-phrase line and `<scene id>#<n>` (n from 1) for a multi-phrase line. Row `text` has markup removed and the mapping tag inserted; user-typed `[...]` tags are kept. Progress lines gain optional `duration_requested_s`. The mock worker honours `duration_scale / target_speed` (tone length), so `duration_s` follows speed and emotion; at factor 1.0 it is byte-identical to today. A target outside 0.3 to 60 s fails that row with `Duration target <x> s is outside what the model accepts (0.3 to 60 s).`

### HTTP (all under `/api/v1/projects/{project_id}`)
- `POST /voices/lines/{scene_id}:set-emotion` body `{"emotion": "happy"|"sad"|"fear"|"anger"|null}` → 200 `VoiceLineActionOut` (`line` as below). Unknown value → 422 `{"detail": "Unknown emotion \"joy\". Use one of: happy, sad, fear, anger."}`, nothing saved. Marks that line's voice take and shot stale only; no job starts.
- `POST /voices/lines/{scene_id}:edit-text` (existing) now also accepts markup. Invalid markup or unknown tag → 422 with the messages above, nothing saved. Text with no speakable text left after removing markup and `[...]` tags → 422 `The line can't be empty.`
- `GET /voices` line object (existing keys unchanged), new keys omitted when empty:
  - `text`: display text (no markup, no `[...]`). `edit_text`: the raw story line, present only when it differs from `text`. `emotion`: picker value.
  - `effective`: present unless delivery is default (no emotion, speed 1.0, no age): `{"emotion_applied": bool, "speed": float, "age_band"?: str, "gap_ms"?: int (multi-phrase only), "phrases": [{"text": str, "emotion": str|null, "tags": [str], "tag_position": str, "pitch": str, "duration_scale": float, "duration_factor": float, "generation": {}, "post": {"semitones": float, "gain_db": float, "pause_s": float}, "reference": "neutral"|"emotion", "reference_label": "Neutral reference"|"Sad reference clip"}]}`. `emotion_applied` is `false` for Kokoro voices (emotion levers are not applied).
  - `takes[i].settings`: the take's recorded applied values (same shape as `effective` plus `duration_requested_s`), omitted for takes with no recorded values. `settings_changed: true` on the line when its active take's recorded values differ from `effective`.
  - `takes[i].stale` is also `true` when the take's recorded mapping values for its emotions differ from the current mapping, when its recorded `gap_ms` differs (multi-phrase takes), or when it used an emotion clip that was since removed or replaced. Takes with no emotion are never stale from a mapping change.
- `GET /voices` `characters[]` items gain `age` (int) and `age_band` (str), omitted when no age. The `voice` object gains `emotion_clips: {"happy": {"url": "/media/<id>", "transcript": str, "clip_seconds": float}, ...}` for cloned voices, omitted when empty.
- `GET /voices/settings` → `{"phrase_gap_ms": int, "default_phrase_gap_ms": int}`; `PUT /voices/settings` body `{"phrase_gap_ms": int}` (0 to 1000, else 422 `phrase_gap_ms must be between 0 and 1000.`) → same shape. Stored per project; used by the next multi-phrase take; multi-phrase takes made with another gap become stale.
- `POST /cast/{key}:set-age` body `{"age": <int|null>}` → 200 `{"project_stage", "approved_count", "total", "character": <cast item with "age", "age_band">}`. Invalid → 422 `{"detail": "Age must be a whole number from 1 to 120."}`. Changing the age marks all and only that character's voice takes stale (and their shots) and starts no job; setting the same age changes nothing. The cast `GET /cast` items gain `age` and `age_band`, omitted when none.
- Emotion clips (cloned voices only; other modes → 409 `Emotion clips are only for cloned voices.`; unknown emotion → 422 unknown-emotion message):
  - `POST /voices/characters/{key}/emotion-clips/{emotion}:upload` multipart `file`, form `transcript` (required, non-blank else 422 `A transcript is required.`) → 201 `VoiceOut`. Content and size checked by `screen_clip` (non-audio → 415 `That file isn't an audio clip.`; over limit → 413 `That clip is larger than <n> MB.`).
  - `POST /voices/characters/{key}/emotion-clips/{emotion}:from-take` body `{"scene_id": str, "take_id": str, "transcript": str | null}` (null uses the take's display text) → 201 `VoiceOut`; take must belong to a line spoken by `key` (else 404 `take not found`).
  - `POST /voices/characters/{key}/emotion-clips/{emotion}:remove` → 200 `VoiceOut`. Replacing or removing a clip marks stale only takes whose recorded params used that clip, and their scenes' shots.
- Take generation with a clip: for a line phrase whose emotion has a clip on a cloned voice, the worker row's `ref_audio` is the clip file and `ref_text` its transcript, and the take's `input_artifact_ids` contains the clip artifact id; other phrases keep the neutral reference. A missing clip file fails the line with `The <emotion> reference clip for <name> is missing. Upload it again or remove it.` (no silent neutral fallback).

### Take data (`Artifact` rows, kind `voice_take`, readable through `ctx.session_factory` and `ctx.store`)
`params` keeps today's keys `text` (raw story line), `speed`, `voice`, `source`. New keys, added only when applicable (a no-emotion, no-age, speed 1.0 take has exactly today's params):
- `duration_requested_s` (float; when `duration_s` was passed to the model, summed over phrases).
- `age_band` (str; when the character has an age).
- `gap_ms` (int; multi-phrase only).
- `phrases`: list when any phrase has an emotion or the line has more than one phrase; each `{"text", "emotion", "tags", "tag_position", "pitch", "instruct", "duration_scale", "generation", "post": {"semitones","gain_db","pause_s"}, "duration_requested_s", "reference": "neutral"|"emotion", "reference_artifact_id"}`.
- `voice` gains `reference_kind` and `emotion` when an emotion clip was used.
- Instruct for OmniVoice: comma-joined `[pitch value from the mapping, age band]` (one value per category), appended to the preset description for preset voices; for cloned voices the same string alone (age always included when set). Kokoro: no `instruct`; age picks the preset via `Mapping.kokoro_age` plus its `semitones` post shift (marked experimental in the UI).

### CLI
- `python tools/voice_sweep.py --ref PATH --ref-text TEXT --out PATH [--model ID]` — real model, reference Mac only; runs inside the mlx-audio environment (`<mlx_audio_path>/.venv/bin/python tools/voice_sweep.py ...`); writes a Markdown table with columns `lever | value | duration (s) | median pitch (Hz) | pitch spread | loudness (LUFS) | brightness (Hz)` to `--out` and prints it. The module exposes `measure(path: Path) -> dict[str, float]` with keys `duration_s`, `median_pitch_hz`, `pitch_spread`, `loudness_lufs`, `brightness_hz` (importable by file path in tests; imports no `reelforge`).

### UI (web, vitest)
- Line card (`web/src/voice/LineCard.tsx`): a `select` labelled `Emotion` with options `None`, `Happy`, `Sad`, `Fear`, `Anger` (value `""`, `happy`, `sad`, `fear`, `anger`); change calls `set-emotion`. A `<details>` whose `<summary>` is `How this will sound`, closed by default; content: `Default delivery. No emotion settings applied.` when `effective` is absent; otherwise per phrase the emotion, tags and position, pitch, duration scale, generation settings, post (semitones, gain dB, pause), age band and the reference label; `Settings changed since this take` when `settings_changed`; `Emotion is not applied for this voice.` when `emotion_applied` is false. The paragraph shows `line.text`; the edit box starts with `line.edit_text ?? line.text`. Play, Approve and Re-take unchanged.
- When the speaker's voice is cloned and the line has an active take, buttons `Use this take as the Happy reference` (and Sad, Fear, Anger); clicking shows a text field labelled `Reference transcript` (prefilled with the display text) and a `Save reference` button.
- `VoiceSetup` (`web/src/voice/VoiceSetup.tsx`) new optional props `age?: number | null`, `ageBand?: string`, `modelKey?: string`, `emotionClips?: Record<string, {url: string; transcript: string; clip_seconds: number}>`, `onUploadEmotionClip?: (emotion: string, file: File, transcript: string) => void`, `onRemoveEmotionClip?: (emotion: string) => void`. Shows `Age 67 (elderly)` or `No age set`; an `Experimental` badge beside it when `modelKey === "kokoro"`. For cloned mode a section headed `Emotion reference clips` with a row per Happy, Sad, Fear, Anger: empty text `No clip. The neutral reference and emotion settings are used.`, or an audio element, the transcript and a button `Remove <Emotion> clip`; per row a file input labelled `Upload clip for <Emotion>`, a text input labelled `Transcript for <Emotion>` and a button `Upload clip`. Not shown for preset or recorded modes.
- Cast row (`web/src/cast/CastRow.tsx`): number input labelled `Age (years)` and button `Save age`; shows `Age 67 (elderly)` or `No age set` and the 422 message on error.
- All new props and fields are optional so the frozen web tests render unchanged.
