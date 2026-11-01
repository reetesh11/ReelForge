# ReelForge Phase 3 — Assembly, player and hardening

Binding inputs: `ReelForge — Requirements Document.md`, `ReelForge — Product Spec.md` (Stage 6, Library/Brand kit/Settings, States and notifications), `ReelForge — Technical Spec.md` (milestones M6, M7, Assembly, Frontend, Observability/testing/security). Builds on Phases 1 and 2.

Scope is Tech Spec milestones **M6 Assembly and player** and **M7 Hardening**.

## Prerequisites (human)
- Phases 1 and 2 merged.
- Music source for the bed track decided (library folder or royalty-free pack); Devanagari font in the brand kit.

## Requirements
- R1 (M6). EDL (`edl.json`) generated from approved shots, active voice takes, music and captions; typed ffmpeg filter-graph builder serialised to a `-filter_complex_script` file stored next to the output.
- R2 (M6). Assembly steps: normalise shots (trim, scale to 1080×1920, 24 fps, yuv420p, strip audio), concat / xfade (0–0.5 s), dialogue track with `adelay` + `amix`, music bed with fades and sidechain ducking, two-pass `loudnorm` to about −14 LUFS / −1 dBTP.
- R3 (M6). Captions: `.ass` generation with presets (Bold pop, Clean subtitle, Hindi Devanagari), safe-zone margins, word timing via forced aligner / Whisper through mlx-audio, burned with the `subtitles` filter; optional brand-kit end card (1.5 s).
- R4 (M6). Preview (540×960, veryfast, crf 28) rebuilt on every timeline edit with a 1 s debounce; explicit final export (libx264 High, crf 18, yuv420p, faststart, AAC 192 kb/s 48 kHz stereo) saved as a new reel version with its EDL; `ffprobe` verification; `cover.jpg`; `credits.json` with model, version and license for every model used.
- R5 (M6). In-app 9:16 player (frame step, loop, speed, scrub, mute, Instagram safe-zone overlay) reused for candidates, shots and the final reel; HTTP range-request media serving scoped to the data root; basic timeline (reorder, trim, swap take, nudge dialogue, caption edits).
- R6 (M7). Staleness UI across all stages; resume after crash end to end; offline acceptance test; "Clean unused takes"; macOS notification when a long job ends; Jobs view with "Copy command"; non-commercial or unverified licence warning.
- R7 (M7). Playwright flows on the mock backend (approve cast, retake line, re-roll shot, export); security checks (127.0.0.1 binding, CORS, no `shell=True`, path-traversal rejection, upload content checks); packaging so `uv tool install` gives a working `reelforge`.

## Acceptance criteria
- AC-1: The exported reel is 10–15 s, 1080×1920, 24 fps, H.264 High yuv420p, AAC 48 kHz stereo, duration within 50 ms of the EDL, with burned captions (checked with `ffprobe`).
- AC-2: Integrated loudness is within tolerance of −14 LUFS and true peak ≤ −1 dBTP on golden media.
- AC-3: Music is ducked under dialogue: music level during a dialogue span is lower than outside it by the configured amount.
- AC-4: Each export writes `credits.json` listing model, version and license, and a model with a non-commercial or unfilled license triggers a warning before export.
- AC-5: The same EDL renders as preview and as final; changing one timeline edit re-renders the preview only.
- AC-6: The player plays the exported file in the browser with range requests and seeks to any frame; media requests for paths outside the data root are rejected.
- AC-7: If the process is killed mid-render at any stage, on restart the project resumes from the last completed step and completed steps are not re-run (full-pipeline test on the mock backend).
- AC-8: The whole pipeline from story to export on the mock backend completes with network disabled and zero outbound connections.
- AC-9: Each reel version keeps its EDL and can be reopened and changed; a new export creates v2 without altering v1.
- AC-10: Playwright flows pass: approve cast, retake line, re-roll shot, export.
- AC-11: Manual check on the reference Mac: one full real reel is produced from a story and plays in the app (human check, time-to-first-reel recorded against the 2-hour goal).

## Out of scope
- Full 4-track timeline editing, takes comparison view, suggested caption and hashtags, overnight queue, visual QA (v1.1).
- Cloud rendering, auto-posting to Instagram, videos over 60 s.

## Open questions
- Music source and licence (still an open question in the Requirements Document).
