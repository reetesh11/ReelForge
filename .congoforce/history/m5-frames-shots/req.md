---
class: feature
size: large
title: Add key frames and shots (M5): gen_frame, gen_shot and the ltx adapter
---
# Requirements — Add key frames and shots (M5)

## Problem
After M4 the user has approved characters, voice takes and shot lengths, but cannot yet turn a scene into a picture or a moving clip. M5 adds Stage 4 (one 9:16 key frame per scene, an img2img edit of the approved character master) and Stage 5 (one rendered shot per scene via ltx-2-mlx: talking, action or continue), with approve, re-roll, staleness and queue controls, so the reel can reach Phase 3 assembly.

## Requirements
The binding list is R1 to R11 in `/Users/reetesh/workspace/ReelForge/phases/phase-2/m5-frames-shots.md`. In EARS form:
- R1. When the user generates a frame for a scene, the system shall run an img2img edit of the approved master (the speaker's, else the first named character's) with an editable LLM-written prompt that contains the character's look text verbatim, never text alone, at the framing from `Scene.framing` (closeup default for dialogue).
- R2. When a card is acted on, the system shall support generate, approve, regenerate (new seed), edit prompt, upload replacement (checked by content and size), and "continue from previous"; all takes are kept, one active. Generate-all shall run one job per frame in story order with per-frame progress.
- R3. When a scene has two characters, the system shall build from one master, put the other character's look text in the prompt, say in the UI that the second character is described not copied, and offer "upload replacement"; it shall not rely on a second `init_images` entry.
- R4. When a scene has `product_in_shot` on and `product.asset` is an existing image under the data root, the frame job shall receive it as an input artifact and the prompt shall ask for the real pack in hand or on the table. If the asset is missing, the scene shall show "Product image missing" and the frame shall still generate.
- R5. When `doctor` or startup runs, `LtxAdapter` shall parse `a2v --help`, `generate --help` and `extend --help` of `<ltx_path>/.venv/bin/ltx-2-mlx` and, if a required flag is missing, doctor (check key stays `ltx`) shall fail and no shot job shall start. Shots run as one subprocess each (argument list, timeout, cancel, RSS sampling via the existing runner); model id, steps and size come from `models.toml` and settings.
- R6. The system shall set shot type automatically (approved voice take: talking; `continue_from`: continue; else action), allow per-shot override, and run talking as a2v (key frame as `--image`, active take as `--audio`), action as silent image-to-video, continue from the previous shot's extracted last frame.
- R7. The system shall use the M4 written-back frame count (8k+1) and a per-shot quality of Draft (320x576) or Final (448x768), both from settings with those defaults.
- R8. The system shall write editable motion prompts (appearance-only for talking, motion for action and continue, each with the character bible line) and extract every finished shot's last frame as artifact `last_frame`.
- R9. The shot board shall offer per shot: render, play (looping inline), approve, re-roll (new seed, same prompt), edit motion prompt, quality, upload own clip (ffprobe: video stream, 9:16, length limit), compare takes. "Render all" shall queue unrendered shots, show order, per-shot estimates (history for same type and size, else a built-in default) and a total ("N shots · about N min · keep the Mac plugged in"), and allow reorder, pause and cancel.
- R10. While a shot or frame job runs, the system shall use `shot_mem_gb` (default 16.0, same precedence and validation as `image_mem_gb`, message names `shot_mem_gb`) or `image_mem_gb`, hold one GPU lease, unload Ollama first, and classify exit -9 and 137 as "killed, likely out of memory" with a Draft-size retry offered on the shot card.
- R11. When a scene's action changes, only that scene's frame and shot shall become stale; a new active voice take stales that scene's talking shot; a changed approved frame stales its shot. Stale items show an amber "Needs update" badge and a one-click "Regenerate stale items"; nothing regenerates automatically. `FRAMES_APPROVED` and `SHOTS_APPROVED` are reached per the ACs and unlock the next stage button.
- R12. The `mock` backend shall provide a deterministic PNG for Draw Things edits and a deterministic ffmpeg MP4 (correct size, frame count, given audio for talking) for LTX, via the same subprocess path as the real adapter where practical.

## Acceptance criteria
- AC-1: A frame job for a scene receives the approved master image(s) as inputs, and its prompt contains the character's look text verbatim.
- AC-2: With a pack image selected and `product_in_shot` on, the frame job receives the pack image as an input; with the asset missing the frame still generates and the scene reports "Product image missing".
- AC-3: A talking shot job receives the key frame and the active approved voice take as inputs and a frame count of 8k+1 equal to the scene's written-back value; an action shot job receives no audio input.
- AC-4: Given 5 rendered shots, re-rolling one produces a new take for that shot only and leaves the other four cache entries untouched.
- AC-5: The ltx adapter fails `doctor` (not mid-render) when a required flag is missing from the parsed `--help`, and passes when all are present (tested with a fake `ltx-2-mlx` script printing a configurable `--help`).
- AC-6: A shot job killed with exit code 137 (or -9) is classified "killed, likely out of memory" and the card offers a Draft-size retry.
- AC-7: A shot job started with less available memory than `shot_mem_gb` fails with a message naming `shot_mem_gb`; with enough memory it runs; only one heavy job holds the GPU lease and Ollama is unloaded first; `shot_mem_gb` has the same precedence and validation as `image_mem_gb`.
- AC-8: The last frame of a finished shot is extracted as an artifact, and a continue shot uses it as its start image.
- AC-9: The shot board's estimate uses recorded render times for the same shot type and size when they exist, and the built-in default otherwise; the queue can be reordered, paused and cancelled, and a cancelled running shot stops its subprocess.
- AC-10: Changing one scene's action marks only that scene's frame and shot stale; a new active voice take marks only that scene's talking shot stale; other scenes are not stale; nothing regenerates automatically.
- AC-11: `FRAMES_APPROVED` is reached only when every scene has an approved frame (or is "continue from previous"); `SHOTS_APPROVED` only when every shot has an approved active take; editing an approved frame reopens only that frame and its shot.
- AC-12: An uploaded replacement frame or clip is checked by content and size (not the extension) and stored under a generated name; a non-image and a non-video are rejected.
- AC-13: Steps for AC-1 to AC-4 complete on the mock backend with no outbound network connection.
- AC-14: Existing frozen M1 to M4 tests pass unchanged (no new keys on existing responses such as `GET /jobs` unless a job has a `result`; the `ltx` doctor check keeps its key).
- AC-15: Manual check on the reference Mac, recorded in `docs/manual-checks.md`: one real key frame from a real master; one real talking shot and one real action shot at Draft size; characters read as the same across shots; the real adapter run once before shipping.

## Out of scope
- Transition (start and end frame) shots, guided draft-then-final workflow, trim in/out, overnight queue (v1.1).
- Manual product overlay canvas, visual QA, brand-kit screens (v1.1).
- Assembly, captions, export (Phase 3).
- Human-like characters (lip sync verified on cartoon only).

## Assumptions
- M1 to M4 are merged on `origin/main` (migration 0004_voice and the voice job handler exist in the tree).
- `Scene.framing`, `product_in_shot` and `continue_from` already exist in `story/schema.py`; `LtxAdapter` in `adapters/ltx.py` is currently a check-only stub to be extended.
- The `ltx-2-mlx` binary is run directly from `.venv/bin`, never via `uv run`; any real-backend worker script must not share a folder with a module shadowing a package it imports.
- Continuation uses `extend` or image-to-video from the extracted last frame, whichever `--help` shows; flags for `generate`/`extend` are read at runtime, not assumed.
- Built-in default render-time estimate values are an implementation choice.

## Suggested split
Too large for one implement/verify loop. Each part is shippable alone and in order:
1. **M5a Key frames:** R1 to R4 (frame prompts, `gen_frame` job, frame cards, product placement, upload, continue-from-previous, `FRAMES_APPROVED`) on the mock Draw Things edit. Covers AC-1, AC-2, AC-12 (image), AC-13 (frames), part of AC-10/11.
2. **M5b LTX adapter and shot job:** R5 to R8, R10 (flag parsing in `doctor`, `shot_mem_gb`, talking/action/continue render, last frame, OOM classification, mock LTX). Covers AC-3, AC-5 to AC-8, AC-13.
3. **M5c Shot board and queue:** R9, R11 and `SHOTS_APPROVED` (cards, re-roll, takes, compare, clip upload, Render all queue with estimates, reorder/pause/cancel, staleness badges, stale regeneration). Covers AC-4, AC-9 to AC-12, AC-14.
4. **M5d Real-tool check:** AC-15 manual run and `docs/manual-checks.md` entry (can fold into M5b/M5c PRs).

## Open questions
- Should this task be split as suggested above, or run as one large task?
- What are the required flags for each of `a2v`, `generate` and `extend` that make doctor fail when absent (a2v list is known; `generate` and `extend` are unconfirmed until `--help` is read)?
- What is the shot length limit for uploaded clips (R9 says "length limit" without a value)?
