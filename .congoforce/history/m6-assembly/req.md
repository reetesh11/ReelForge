---
class: feature
size: large
title: Assembly stage - EDL, captions, export and player
---
# Requirements - Assembly stage - EDL, captions, export and player

## Problem
After shots are approved (M5), a creator has no way to turn them into a finished vertical reel. They need the approved shots and voice audio joined into one 1080x1920 video with loudness-normalised audio and burned-in captions (including Hindi), a preview that follows their timeline edits, an explicit export saved as a versioned reel, and an in-app player to review it. The EDL must be the single source of truth for preview and final render.

## Requirements
- R1. When assembly is requested, the system shall generate `edl.json` from the approved shot takes, active voice takes and captions, with empty music-track slots in the schema.
- R2. When an EDL is rendered, the system shall serialise a typed ffmpeg filter graph to a `-filter_complex_script` file next to the output and run ffmpeg as an argument list (never via a shell).
- R3. When rendering, the system shall normalise each shot (trim, scale to 1080x1920 with 9:16 handling, 24 fps, yuv420p), join with concat or xfade (0 to 0.5 s, default 0), place each dialogue clip with `adelay`, mix with `amix`, and run two-pass `loudnorm` to about -14 LUFS and -1 dBTP.
- R4. If a shot has no audio, then the system shall treat it as silence and not raise an error.
- R5. While a render runs, the system shall record each step so a killed render resumes at the last completed step without re-running completed steps.
- R6. When captions are generated, the system shall produce `.ass` with presets Bold pop, Clean subtitle and Hindi Devanagari, inside Instagram safe-zone margins, using word timing from a forced aligner or Whisper via mlx-audio, and burn them in with the `subtitles` filter.
- R7. When a user edits a caption line, the system shall update the EDL captions without re-recording audio.
- R8. The system shall keep the 1.5 s brand-kit end card off by default.
- R9. When a timeline edit occurs, the system shall rebuild only the 540x960 preview (veryfast, crf 28) after a 1 s debounce.
- R10. When the user exports, the system shall render the final (libx264 High, crf 18, yuv420p, faststart, AAC 192 kb/s 48 kHz stereo), verify it with `ffprobe`, write `cover.jpg` and `credits.json`, and save a new reel version with its EDL.
- R11. If any model used is non-commercial or has an unfilled licence, then the system shall show a warning before export.
- R12. When a second export happens, the system shall create the next version (v2, ...) and leave earlier versions playable and unchanged; reopening a version shall load its EDL.
- R13. The system shall serve media with HTTP range requests, scoped to the data root, and reject paths outside it.
- R14. The UI shall provide a 9:16 player (frame step, loop, speed, scrub, mute, safe-zone overlay) reused for candidates, shots and the final reel, and a basic timeline (reorder shots, trim in/out, swap take, nudge dialogue clip, edit captions).
- R15. The system shall add stage "Assembly" with `REEL_EXPORTED`, unlocked by `SHOTS_APPROVED`.
- R16. The system shall run `assemble_preview` and `assemble_final` as light jobs in the existing queue (no GPU lease, no model) with per-step progress, and the full stage shall run on the mock backend with no network.

## Acceptance criteria
- AC-1: The exported reel for the reference story is 10 to 15 s, 1080x1920, 24 fps, H.264 High yuv420p, AAC 48 kHz stereo, duration within 50 ms of the EDL, with burned captions (`ffprobe`).
- AC-2: On golden media, integrated loudness is within tolerance of -14 LUFS and true peak is at most -1 dBTP.
- AC-3: The filter-graph script exists next to each output; the same EDL yields the 540x960 preview and the final; one timeline edit re-renders the preview only (no final job enqueued).
- AC-4: A dialogue clip lands at its EDL offset within one frame (1/24 s); a silent shot yields silence in the mix and no error.
- AC-5: Captions follow the chosen preset, stay inside safe-zone margins, and Devanagari text renders (golden frame check).
- AC-6: Each export writes `credits.json` with model, version and licence per model used; a non-commercial or unfilled licence produces a pre-export warning.
- AC-7: Killing the process at each render step on the mock backend, then restarting, resumes from the last completed step and does not re-run completed steps.
- AC-8: The player plays the exported file in the browser with range requests (206 responses) and seeks to any frame; a media request outside the data root is rejected.
- AC-9: A second export creates v2 without changing v1's files or EDL; reopening v1 loads its EDL.
- AC-10: The story-to-export pipeline on the mock backend completes with network disabled and zero outbound connections.
- AC-11: Existing frozen M1 to M5 tests pass unchanged.
- AC-12: Manual check on the reference Mac, recorded in `docs/manual-checks.md`: the Grumpy Uncle project (3 approved shots) exports as a real reel, plays in the app, dialogue clear and in sync.
- AC-13: `assemble_preview` and `assemble_final` are registered job types that take no GPU lease and report per-step progress.
- AC-14: Editing a caption line changes the EDL and the rendered `.ass` text without creating any voice take.
- AC-15: The EDL schema contains empty music-track slots, and the end card is disabled in a default EDL.

## Out of scope
- Music bed, ducking, music licensing.
- Emotion hints and re-recording lines.
- M7 hardening: Playwright flows, full security pass, packaging, notifications, "Clean unused takes".
- Full 4-track timeline, caption/hashtag suggestions, visual QA, cloud rendering, auto-posting.
- Brand-kit screens.

## Assumptions
- Draft (320x576) and Final (448x768) shots are scaled up to 1080x1920; the aspect ratio is already 9:16.
- The Devanagari font path comes from a new setting with a macOS default.
- Existing `reel_versions` table (edl_artifact_id, final_artifact_id, credits) is reused; a migration is added only if needed.
- Caption alignment is unit-tested with a mock aligner; the real aligner is checked manually.

## Suggested split
1. M6a - EDL and render engine: EDL schema, typed filter-graph builder, normalise/concat/audio mix/loudnorm, resumable steps, `assemble_preview` job, mock backend (R1-R5, R9 backend, R16; AC-1 partly, 2, 3, 4, 7, 10, 13, 15).
2. M6b - Captions: alignment spike, `.ass` presets, safe zones, Devanagari, editable lines (R6-R8; AC-5, 14). Requires the spike result first.
3. M6c - Export and versions: final export, ffprobe verification, cover, credits, licence warning, reel versions, Assembly stage (R10-R12, R15; AC-1, 6, 9).
4. M6d - Player and timeline UI: range-request media serving scoped to the data root, player component, basic timeline (R13, R14; AC-8).
5. AC-11 and AC-12 apply to every part; AC-12 closes M6d.

## Open questions
- Does the installed mlx-audio expose forced alignment, or must Whisper be used? (Needs a spike on the reference Mac before M6b is planned.)
- Which Devanagari font should be the macOS default path?
- Should M6 be delivered as the four suggested parts, or does the owner want a different split?
