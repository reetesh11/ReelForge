# ReelForge Phase 3 / M6 — Assembly, captions, export and player

Binding inputs: `ReelForge — Requirements Document.md`, `ReelForge — Product Spec.md` (Stage 6, States and notifications), `ReelForge — Technical Spec.md` (milestone M6, Assembly, Frontend). The Technical Spec wins on design; the Requirements Document wins on acceptance. Parent: `phases/phase-3-assembly-player-hardening.md`. Requires M1 to M5 merged (M5 gives approved shots with their voice audio). Order agreed with the owner: **M6 assembly, then emotion in dialogue, then music**. Out of scope here: the music bed (last milestone), emotion hints, M7 hardening.

## Inputs already decided
- Approved shots are `take_NNN.mp4` per scene under `shots/<scene>/`; talking shots already carry the dialogue audio, action shots are silent. Draft shots are 320x576 and Final 448x768, so assembly must scale up to 1080x1920.
- The data root is `~/reelforge-data`. Reel versions are rows in `reel_versions`; the `assembly/` folder per project already exists.
- ffmpeg 9.0.2 (arm64, filters check passes) is the only render tool. Run it as an argument list, never through a shell.
- Captions need word timing. Use a forced aligner or Whisper through the existing mlx-audio environment; this must be spiked on the reference Mac before the caption task is planned (does the installed mlx-audio expose alignment?).
- The Hindi (Devanagari) font must be available to the subtitles filter; the brand-kit screens do not exist yet, so the font path comes from a setting with a sensible macOS default.

## Requirements
- R1. **EDL:** generate `edl.json` from the approved shot takes, the active voice takes and the captions. The EDL is the single source of truth: preview and final render from the same EDL. A typed ffmpeg filter-graph builder serialises the graph to a `-filter_complex_script` file stored next to the output. Slots for a music track exist in the EDL schema but stay empty until the music milestone.
- R2. **Assembly:** normalise each shot (trim, scale to 1080x1920 with correct 9:16 handling, 24 fps, yuv420p), join with concat or xfade (0 to 0.5 s, default 0), place each dialogue clip with `adelay`, mix with `amix`, and run two-pass `loudnorm` to about -14 LUFS and -1 dBTP. A shot with no audio contributes silence. Each step is a recorded step so a killed render resumes from the last completed one.
- R3. **Captions:** `.ass` generation with presets Bold pop, Clean subtitle and Hindi Devanagari; Instagram safe-zone margins; word timing from a forced aligner or Whisper through mlx-audio; burned in with the `subtitles` filter. Caption text is editable per line without re-recording. Optional 1.5 s end card from the brand kit is **off by default** until the brand-kit screens exist.
- R4. **Preview and export:** preview at 540x960 (veryfast, crf 28) rebuilt after every timeline edit with a 1 s debounce; explicit final export (libx264 High, crf 18, yuv420p, faststart, AAC 192 kb/s 48 kHz stereo) saved as a new reel version together with its EDL. Verify with `ffprobe`; write `cover.jpg` and `credits.json` (model, version and licence for every model used, with a warning before export when one is non-commercial or unfilled).
- R5. **Player and timeline:** in-app 9:16 player (frame step, loop, speed, scrub, mute, Instagram safe-zone overlay) reused for candidates, shots and the final reel; media served with HTTP range requests and scoped to the data root. Basic timeline: reorder shots, trim in/out, swap take, nudge a dialogue clip, edit captions. A new stage "Assembly" with `REEL_EXPORTED` unlocked by `SHOTS_APPROVED`.
- R6. **Jobs and memory:** assembly and export run as jobs in the existing queue (`assemble_preview`, `assemble_final`), are light jobs (no GPU lease, no model), and show per-step progress. Mock backend: the whole stage runs in tests and CI with mock shots, with no network.
- R7. **Reel versions:** each export creates a new version (v1, v2...) with its own EDL; older versions stay playable and unchanged; reopening a version loads its EDL for further editing.

## Acceptance criteria
- AC-1: The exported reel is 10 to 15 s for the reference story, 1080x1920, 24 fps, H.264 High yuv420p, AAC 48 kHz stereo, with duration within 50 ms of the EDL and burned captions (checked with `ffprobe`).
- AC-2: Integrated loudness is within tolerance of -14 LUFS and true peak at most -1 dBTP on golden media.
- AC-3: The filter-graph script is written next to the output and the same EDL produces both the 540x960 preview and the final; one timeline edit re-renders the preview only.
- AC-4: A dialogue clip lands at its EDL offset (within one frame) and shots without audio produce silence, not an error.
- AC-5: Captions follow the chosen preset, stay inside the safe-zone margins, and Devanagari text renders (a golden frame check).
- AC-6: Each export writes `credits.json` listing model, version and licence; a non-commercial or unfilled licence shows a warning before export.
- AC-7: If the process is killed mid-render at any step, on restart the project resumes from the last completed step and completed steps are not re-run (mock backend).
- AC-8: The player plays the exported file in the browser with range requests and seeks to any frame; a media request for a path outside the data root is rejected.
- AC-9: A second export creates v2 without changing v1; reopening v1 loads its EDL.
- AC-10: The whole story-to-export pipeline on the mock backend completes with the network disabled and zero outbound connections.
- AC-11: Existing frozen M1 to M5 tests pass unchanged.
- AC-12: Manual check on the reference Mac (recorded in `docs/manual-checks.md`): the Grumpy Uncle project (3 approved shots) is exported as a real reel, plays in the app, and the dialogue is clear and in sync.

## Out of scope
- Music bed, ducking and music licensing (last milestone).
- Emotion hints and re-recording lines (next milestone).
- M7 hardening items: Playwright flows, full security pass, packaging, notifications, "Clean unused takes".
- Full 4-track timeline, caption and hashtag suggestions, visual QA, cloud rendering, auto-posting.
