---
class: feature
size: large
title: Add Hindi voice-overs (M4 Voice) with OmniVoice, Kokoro fallback and a voice board
---
# Requirements — Add Hindi voice-overs (M4 Voice)

## Problem
After the cast is approved, a creator needs spoken Hindi lines for every scene: pick or clone a voice per character, generate takes, audition and approve them, and have each approved line set its scene's shot length. Today `adapters/mlx_audio.py` only checks that the environment exists, `models.toml` names Kokoro as the TTS model, and there is no voice stage, worker, or board.

## Requirements
- R1. When given a JSONL batch (`{id, text, model, voice, ref_audio, ref_text, speed, lang}` per line), `tts_worker.py` shall load each model once, write one 24 kHz mono WAV per line, and print one JSON progress line per finished line (`id`, `path`, `duration_s`). It imports only numpy and mlx-audio, never `reelforge`.
- R2. If one line fails, then the worker shall print that line's progress with an `error` and continue the batch.
- R3. When run with `--selftest`, the worker shall render a one-word WAV and exit 0. With `--backend mock` it shall produce short deterministic WAVs with no model.
- R4. When a voice batch runs, the mlx-audio adapter shall start one subprocess per batch (argument list, timeout, cancel, progress to the job), then with ffmpeg trim silence at both ends, normalise to -16 LUFS and resample to 48 kHz.
- R5. When speed is within 0.8 to 1.25, the adapter shall apply it (worker speed argument where the model has one, ffmpeg `atempo` otherwise). If speed is outside 0.8 to 1.25 or a pause (before or after) is outside 0 to 1 s, then the system shall reject the request.
- R6. `doctor` shall gain a blocking check that fails when the mlx-audio environment is missing or `tts_worker.py --selftest` fails, and passes otherwise.
- R7. `models.toml` shall name OmniVoice (`mlx-community/OmniVoice-bfloat16`, Apache-2.0, license URL) as `[models.tts]` and Kokoro (`mlx-community/Kokoro-82M-bf16`, Apache-2.0) as a separate fallback entry. Settings shall gain `voice_model` (default OmniVoice; Kokoro selectable); the batch the adapter writes shall use the selected model id; the Status panel shall name the voice model in use.
- R8. The system shall let each character have a voice: a preset (Kokoro `hf_alpha`, `hf_beta`, `hm_omega`, `hm_psi`; a small set of named Hindi voices for OmniVoice defined in the adapter), a cloned voice (5 to 10 s reference clip plus transcript), or a recorded-line upload per line (bypasses TTS). The voice stores model, voice id or reference clip, default speed and default language `hi`, and is saved with the character in the library and reused with it in new projects.
- R9. When a clip is uploaded for cloning, the system shall check type and size by content (as cast uploads do), reject non-audio and oversized files, and store accepted files under the data root with a generated name.
- R10. When the user starts generation, the system shall enqueue one `gen_voice_take` batch job for all lines in story order with progress per line. The voice board (one column per scene) shall support play, approve, new take (different seed), edit text and re-take, speed slider, pause before/after, keeping all takes with exactly one active, and "Play scene" / "Play all" previews that stitch active takes with their pauses.
- R11. When every line has an approved active take, the project stage shall become `VOICES_APPROVED`, unlocking "Continue to key frames". When an approved line's text is edited, only that line shall be reopened and the stage shall leave `VOICES_APPROVED`.
- R12. When a line is approved, the system shall write the active take's duration including pauses to its scene as shot length, with `frames = 8 * ceil((duration * 24 - 1) / 8) + 1`. A line over its scene's duration budget shall be flagged with the line-fitting suggestions (speed up, shorten text via the LLM, extend the scene).
- R13. When a line's text changes, the system shall mark only that line's voice take and that scene's shot length stale using `artifact_inputs`/`story_changes`; other scenes stay fresh, nothing regenerates automatically, stale items show an amber badge and a "Regenerate stale items" action regenerates them.
- R14. The voice job shall use the GPU lease and memory pre-flight (Ollama unloaded first) with a new setting `voice_mem_gb` (default 4.0, same precedence as `image_mem_gb`: CLI > env > config.toml > default). If available memory is below it, then the job shall fail with a message naming `voice_mem_gb`.
- R15. All of the above shall run on the `mock` backend with no outbound network connection.

## Acceptance criteria
- AC-1: With 5 dialogue lines rendered and one re-taken, the scene's shot length is computed from the active take, not the earlier one.
- AC-2: Changing one line's text marks only that line's voice take and its scene's shot length stale; the other four scenes are not stale.
- AC-3: For any duration, frames equal `8k + 1` (property test); 2.9 s gives 73 and 3.32 s gives 81.
- AC-4: `tts_worker.py` on a 3-line batch with a stub model writes 3 WAVs and prints 3 progress JSON lines; with one failing line, that line carries `error` and the other two succeed; the model is loaded once (one process).
- AC-5: Post-processing of generated tones and silence through ffmpeg yields 48 kHz WAVs at about -16 LUFS with leading and trailing silence trimmed, without any model.
- AC-6: `doctor` reports a blocking failure when the mlx-audio environment is missing or `--selftest` fails, and passes when it works.
- AC-7: Packaged `models.toml` has OmniVoice as `[models.tts]` and Kokoro as fallback; setting `voice_model` to Kokoro changes the model id in the batch the adapter writes; no licence warning shows for either; the Status panel shows the model in use.
- AC-8: Saving an approved character to the library stores its voice; a second project using it gets the same voice settings and reference clip. A clone upload of a non-audio file and of an oversized file is rejected by content; an accepted file is stored under a generated name.
- AC-9: Speed outside 0.8 to 1.25 and pauses outside 0 to 1 s are rejected; inside the ranges, the duration written to the scene includes both pauses.
- AC-10: A job with less available memory than `voice_mem_gb` fails with a message naming `voice_mem_gb`; with enough it runs. Only one heavy job holds the GPU lease and Ollama is unloaded first. `voice_mem_gb` follows the `image_mem_gb` precedence and rejects non-positive values.
- AC-11: `VOICES_APPROVED` is reached only when every line has an approved active take; editing an approved line's text reopens only that line.
- AC-12: AC-1 to AC-4 pass with no outbound network connection (mock TTS).
- AC-13: Manual (human listening, reference Mac, recorded in `docs/manual-checks.md`): 5 real Hindi lines render correctly with OmniVoice and with Kokoro; one cloned voice from a real 5 to 10 s clip is judged recognisable or recorded as a known limitation.
- AC-14: Existing frozen M1 to M3c tests still pass (no new keys on existing responses such as `GET /jobs` unless a job has a `result`).

## Out of scope
- Voice design from text, emotion hints, English voices, other selectable TTS models (v1.1).
- Key frames, shots, lip-sync rendering (M5); assembly, captions, word-level timings (Phase 3).
- Testing voice cloning with a real model (manual only; stub in tests).

## Assumptions
- Hindi only (`lang = hi`) in the voice UI and defaults.
- The fallback is a second `models.toml` entry (for example `[models.tts_fallback]`); the name is an implementation choice.
- `voice_mem_gb` goes under the existing `[limits]` TOML mapping next to `image_mem_gb`.
- Recorded-line uploads are checked by content like cast uploads and still get silence trim and normalisation unless design says otherwise.
- The "Play scene / Play all" preview is done in the browser or by a short ffmpeg concat (design decides).
- A new DB migration may be needed for voices and takes; design decides.

## Suggested split
1. Voice engine: `tts_worker.py` (real plus `--backend mock`, `--selftest`), mlx-audio adapter batch run, ffmpeg post-processing, speed handling, `doctor` check (R1 to R6, R15; AC-4, AC-5, AC-6, AC-12).
2. Models and settings: `models.toml` OmniVoice/Kokoro, `voice_model`, `voice_mem_gb`, Status panel (R7, R14 settings part; AC-7, AC-10 settings part).
3. Character voices and library: presets, clone upload, recorded-line upload, library persistence (R8, R9; AC-8).
4. Voice takes, staleness and frame math: `gen_voice_take` job, takes and active take, approval, stage `VOICES_APPROVED`, shot length write-back, stale handling, memory pre-flight (R10 backend, R11 to R14; AC-1 to AC-3, AC-9 to AC-11).
5. Voice board UI: per-scene columns, controls, previews, amber badges and regenerate action (R10 UI).

## Open questions
- Should this single task be split as suggested (5 pieces), or run as one large task?
- What named Hindi starting voices should OmniVoice offer (names and parameters), or may the implementer choose a small set?
- Is the line-fitting "duration budget" the scene's existing duration field in the story YAML? Please confirm the field.
