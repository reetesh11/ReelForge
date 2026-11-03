# ReelForge Phase 2 — Voice, key frames and shots

Binding inputs: `ReelForge — Requirements Document.md`, `ReelForge — Product Spec.md` (Stages 3–5, States, Manual edit options), `ReelForge — Technical Spec.md` (milestones M4, M5, Adapters, Process and memory model, Shot length and frame math). Builds on Phase 1.

Scope is Tech Spec milestones **M4 Voice** and **M5 Frames and shots**. CI uses the `mock` backend; real model runs are manual on the reference Mac.

## Prerequisites (human)
- Phase 1 merged.
- Spike S2 (LTX a2v with image + 3 s Hindi line at 320×576) done, finding in the Technical Spec: `a2v --image … --audio … --distilled --low-ram` works, 48 s, 15.6 GB peak, lip sync good on a cartoon character. Human-like characters are unverified.
- Spike S3 (Hindi TTS bake-off) done, finding in the Technical Spec: default voice model OmniVoice, fallback Kokoro; Voxtral is non-commercial and Qwen3-TTS has no Hindi. Cloning is still untested. `models.toml` must be updated by M4 (OmniVoice default entry, Kokoro fallback entry).
- Spike S4 (Draw Things open + LTX render on 24 GB) done: no swaps with Draw Things open, so auto-quit stays off by default.

## Requirements
- R1 (M4). `tts_worker.py` batch worker for mlx-audio (JSONL in, WAV 24 kHz mono plus duration and JSON progress out); adapter with preset and cloned voices; ffmpeg post-process (trim silence, −16 LUFS, 48 kHz).
- R2 (M4). Voice setup per character (preset, cloned, recorded-line upload) saved to the library; voice board with generate-all, play, approve, new take, edit text and re-take, speed 0.8–1.25×, pause before/after 0–1 s; all takes kept, one active; play scene / play all preview.
- R3 (M4). Approved line duration written back to the scene as shot length with `frames = 8 × ceil((duration × 24 − 1) / 8) + 1`; lines over the scene budget are flagged with the line-fitting LLM suggestions.
- R4 (M5). Key-frame generation by image edit from approved masters + setting + action + style (never text alone), with LLM-written editable frame prompts; framing presets; per-card approve / regenerate / edit prompt / upload / continue-from-previous; AI product placement from brand-kit pack shots.
- R5 (M5). ltx-2-mlx adapter that parses `--help` at startup and refuses to run if a required flag is missing; talking (a2v), action (i2v, silent) and continue (extend) shots; last-frame extraction; LLM-written editable motion prompts; draft and final sizes; per-shot approve / re-roll (new seed) / edit prompt / upload clip / choose take.
- R6 (M5). Shot board with render-all queue, per-shot ETA from render history, pause / reorder / cancel, and the "N shots · about X min" estimate; a shot is one subprocess; memory monitoring (RSS sampling, pressure flag, exit −9/137 offers smaller retry).
- R7. Staleness computed on read from `artifact_inputs`: stale items show an amber badge and one-click "Regenerate stale items"; nothing regenerates automatically.

## Acceptance criteria
- AC-1: Given 5 dialogue lines rendered and one re-taken, the active take is the one used for that scene's shot length and is the one passed to the shot job.
- AC-2: Changing a line's text marks only that line's voice and that scene's frame-independent shot stale; other scenes are not stale.
- AC-3: Frame math gives `8k + 1` frames for any duration (property test), e.g. 2.9 s → 73 frames.
- AC-4: Given 5 rendered shots, re-rolling one produces a new take for that shot only and leaves the other four cache entries untouched.
- AC-5: Every key frame job receives the approved master image(s) as inputs and its prompt references the character look text verbatim.
- AC-6: With a pack shot selected, the product-in-shot scene's frame job receives the pack image as an input.
- AC-7: The ltx adapter fails `doctor` (not mid-render) when a required CLI flag is missing from `--help`.
- AC-8: A job killed with exit code 137 is classified "killed, likely out of memory" and offers a smaller retry.
- AC-9: Only one heavy job holds the GPU lease at a time; Ollama is unloaded before a heavy job starts.
- AC-10: Steps for AC-1..AC-4 complete with no outbound network connection.
- AC-11: Manual check on the reference Mac: one real talking shot and one action shot render at draft size, and the characters read as the same (human visual check, not automated).

## Out of scope
- Transition (start/end frame) shots, draft-then-final workflow, voice design, emotion hints, overnight queue (v1.1).
- Manual product overlay canvas, visual QA (v1.1).
- Assembly, captions, export (Phase 3).

## Open questions
- Resolved by S2: lip sync on the cartoon character is good, so talking shots stay `a2v` with the key frame as `--image`; no separate lip-sync pass. Still open: human-like characters are untested (fallback: the experimental `lipdub` command).
