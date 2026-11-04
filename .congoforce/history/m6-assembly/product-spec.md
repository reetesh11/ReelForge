# Product spec — Assembly stage - EDL, captions, export and player

## User-facing behaviour

### Where it lives
- The existing stage stepper (`web/src/components/StageStepper.tsx`) already lists "Assembly" as the sixth stage after "Shots". It stays locked until the project reaches `SHOTS_APPROVED`, then becomes available. After a successful export the project reaches `REEL_EXPORTED` and the Assembly badge shows "Approved".
- The Assembly screen opens in the project page as `?screen=assembly`, following the pattern of `?screen=voices|frames|shots`. The Shots screen gets a "Continue to Assembly" action once all shots are approved; the Assembly screen has a "Back to Shots" action.
- Stepper badges use the existing set: Not started, Queued, "Rendering NN%", Needs review, Approved, Stale, Failed.

### Assembly screen layout
- Left: phone-shaped 9:16 player. Below it: timeline. Right or below: caption editor, style preset, export panel.
- Top of the screen shows a version selector ("Editing: working copy" or "Reel v1", "v2", ...).

### Player (one component, reused)
Used on the Assembly screen (preview and exported versions), and replaces the plain video elements for key-frame/shot candidates, shot cards and take comparison.
- Controls: Play/Pause, Previous frame, Next frame (also keyboard left/right arrow while the player has focus), Loop toggle, Speed (0.5x, 1x, 1.5x, 2x), scrub bar, Mute toggle, Safe-zone overlay toggle (off by default).
- Frame step moves by exactly 1/24 s.
- The safe-zone overlay draws the Instagram top and bottom UI areas over the video, so the user can check captions do not enter them. It is a visual layer only and is never rendered into exported files.
- While media loads: spinner and "Loading video...". If the file cannot be loaded: "Couldn't load this video." with a Retry button.

### Timeline (basic, 2 tracks plus captions)
- Video track: one block per approved shot in scene order. Edits: drag to reorder (or Move earlier / Move later buttons for keyboard use), trim in and trim out (seconds, 0.01 s resolution, cannot trim below 0.5 s of the shot or beyond its length), "Swap take" (choose another take of that shot), cut-or-crossfade setting between adjacent shots (0 to 0.5 s, default 0 = cut).
- Dialogue track: one block per active voice take placed at its offset. Edit: nudge earlier/later (step 1/24 s; arrows and typed value in seconds). Nudge cannot move a clip before 0 or past the end of the reel.
- Captions track: one caption per line. Edit text inline (see Captions). Timing comes from alignment and is not edited in M6.
- A music-track row is not shown. The EDL carries empty slots for it only.
- Every timeline edit marks the preview "Out of date" immediately and, after a 1 s pause with no further edits, starts a preview rebuild automatically. A new edit during the pause restarts the 1 s wait. An edit during a running preview rebuild queues one more rebuild after it.

### Preview
- Preview badge states: "Preview up to date", "Out of date - rebuilding in 1 s", "Rebuilding preview: <step name> (NN%)", "Preview failed - Retry".
- Preview is 540x960, same EDL as the final. A "Rebuild preview" button exists for manual retry.
- Timeline edits never start an export.

### Captions
- Style presets, selected from a dropdown labelled "Caption style": "Bold pop" (word-by-word highlight), "Clean subtitle", "Hindi Devanagari". Default: "Bold pop" for English text; "Hindi Devanagari" is chosen automatically when the line text is Devanagari, and the user can override it.
- Caption text per line is an editable text field, one per script line, labelled "Caption for <character> line <n>". Saving a change updates the EDL captions and the preview rebuild follows the 1 s debounce. No voice take is created, no TTS job runs, and the audio is unchanged.
- Captions are placed inside Instagram safe-zone margins (on a 1080x1920 frame: no caption pixel above y=250 or below y=1670 and none within 64 px of the left or right edge; exact values are fixed in the tech spec but must satisfy "inside the safe zone" for the overlay).
- Empty caption text: the line shows no caption in the render; the field shows placeholder "No caption for this line".
- Word timing is produced by a forced aligner or Whisper (via mlx-audio). While alignment runs the Captions track shows "Aligning captions..." If alignment fails for a line, that line falls back to line-level timing (whole line shown from its dialogue start to end) and shows the note "Word timing unavailable - showing the whole line".

### End card
- Off by default. Default EDL has the end card disabled. There is no end-card control in M6 UI (brand-kit screens do not exist).

### Export
- Button "Export final". Disabled while the preview is rebuilding or a final export is running.
- Licence warning: before the export starts, if any model used by the project is non-commercial or has an unfilled licence, a dialog opens titled "Licence check before export" listing each model as "<model> <version> - <licence or 'Licence not filled in'>", with the message "Some models used in this reel are non-commercial or have no licence recorded. Exporting is allowed, but check you may publish this reel." and buttons "Export anyway" and "Cancel". With no such model there is no dialog.
- While exporting: per-step progress (see Jobs) in the export panel, e.g. "Exporting: Mixing audio (3 of 8)".
- On success: new version appears in the version selector ("Reel v1"), the final plays in the player, and the panel shows "Exported reel v1". Files in the version folder: the reel, `cover.jpg`, `credits.json`, the `edl.json` for that version, and the filter-graph script next to each render output.
- On failure: "Export failed at <step name>. <short reason>" with a Retry button. A retry resumes from the last completed step.
- `credits.json` lists, per model used: model name, version, licence.
- A second export creates "Reel v2". Version v1 files and EDL are not modified. Choosing v1 in the selector plays v1 and loads its EDL into the timeline for editing; edits after reopening produce, on export, a new version (never overwrite v1).

### Jobs and progress
- `assemble_preview` and `assemble_final` appear in the existing queue panel as light jobs (no GPU, no model load) with the label "Assembly preview" and "Assembly export".
- Per-step progress names, in order: "Preparing shots", "Joining video", "Placing dialogue", "Mixing audio", "Measuring loudness", "Normalising loudness", "Burning captions", "Encoding". Export adds "Verifying", "Writing cover and credits". Percent is derived from completed steps.
- After an app restart, a render that was killed mid-way resumes from the last completed step without redoing finished steps.

### Media serving
- All video, audio and image files used by the UI are served with HTTP range requests (206 Partial Content for ranged requests) so the browser can seek to any frame.
- Requests for a path outside the data root are rejected (404, body `{"detail":"Not found"}` style used by existing API errors); traversal such as `..` and symlinks leading outside are also rejected.

### Mock backend
- With the mock backend the whole story-to-export pipeline runs without network and produces a valid reel from mock shots and mock voice audio.

## Acceptance criteria

- AC-1: Exporting the reference story yields a file with `ffprobe` showing: duration between 10.000 and 15.000 s and within 0.050 s of the EDL total duration; video h264, profile High, pix_fmt yuv420p, 1080x1920, 24 fps (r_frame_rate 24/1); audio aac, 48000 Hz, 2 channels, bit rate about 192 kb/s; `moov` atom at the start (faststart). Captions are visible in a sampled frame during a dialogue line.
- AC-2: On golden media, an `ebur128` measurement of the exported audio gives integrated loudness within -14 LUFS plus or minus 1.0 LU and true peak at most -1.0 dBTP. Loudnorm is run as two passes (measure then apply with the measured values).
- AC-3: Each render output (preview and final) has its `-filter_complex_script` file in the same folder, named after the output (for example `preview.filtergraph.txt`, `final.filtergraph.txt`). Preview (540x960) and final (1080x1920) are produced from the same EDL; the graphs differ only in output size/encoding parameters. After one timeline edit and the 1 s debounce, exactly one `assemble_preview` job is enqueued and no `assemble_final` job is enqueued.
- AC-4: A dialogue clip with EDL offset t starts in the mixed audio at t within 1/24 s (about 41.7 ms), checked on the mix. A shot with no audio stream contributes silence of its length; render completes with no error and no warning shown to the user.
- AC-5: A rendered frame during a caption shows the chosen preset style (Bold pop: highlighted current word; Clean subtitle: plain line; Hindi Devanagari: Devanagari glyphs drawn, not tofu/blank boxes). All caption pixels lie inside the safe-zone margins. Golden frame comparison covers one Devanagari frame. The alignment is unit-tested with a mock aligner.
- AC-6: Each export writes `credits.json` in the version folder with one entry per model used: `model`, `version`, `licence`. If any entry is non-commercial or has an empty/unfilled licence, the "Licence check before export" dialog (above) appears before the export job is enqueued; "Cancel" enqueues nothing. The `credits` value is also stored on the reel version row.
- AC-7: With the mock backend, killing the process at each recorded render step and restarting resumes at the first step not marked complete; steps already completed are not executed again (verified by per-step run counters or output timestamps). The final output is identical in content to an uninterrupted render.
- AC-8: In the browser the exported file plays and seeks to any frame; the network log shows 206 responses with `Content-Range` for ranged requests. A request whose path resolves outside the data root (including `..` and absolute paths) is rejected with a 4xx and no file content.
- AC-9: After a second export, `v2` exists with its own files and EDL; every file of `v1` has unchanged content and modification time and `v1`'s EDL is byte-identical. Selecting v1 in the version selector loads v1's EDL into the timeline.
- AC-10: The story-to-export pipeline on the mock backend completes with network access disabled; a test records zero outbound connections.
- AC-11: All existing M1 to M5 tests that were frozen before this task pass unchanged.
- AC-12: Manual check on the reference Mac, written as a dated entry in `docs/manual-checks.md`: the Grumpy Uncle project with 3 approved shots exports as a real reel, plays in the app, dialogue is clear and in sync with the picture.
- AC-13: `assemble_preview` and `assemble_final` are registered job types. They take no GPU lease and load no model. While running they report progress per step (step name and percent) through the existing job progress/events channel, visible in the queue panel and the stepper badge ("Rendering NN%").
- AC-14: Editing a caption line changes that line's text in the EDL captions and, after the next render, in the generated `.ass` file. No voice take row or audio file is created or modified.
- AC-15: The EDL schema has music-track slots, and a freshly generated EDL has them empty (an empty list or null for each slot, as fixed by the tech spec). A freshly generated EDL has the end card disabled (`enabled: false`).

## Edge cases and errors
- Shot with no audio stream: silence, no error (AC-4). Talking shots already carry dialogue audio; action shots are silent.
- Draft (320x576) and Final (448x768) shots are scaled up to 1080x1920; no crop or letterbox is needed because they are 9:16. Other aspect ratios are handled by scaling to cover and cropping centre.
- Crossfade requested longer than the shorter adjacent shot: the value is capped to 0.5 s and to half of the shorter shot's trimmed length, with note "Crossfade shortened to fit".
- Trim leaving less than 0.5 s of a shot: rejected with "A shot must be at least 0.5 s long."
- Timeline edits with zero approved shots: Assembly stays locked; if a shot is un-approved while Assembly is open, the stage badge becomes "Stale" and Export is disabled with "Approve all shots before exporting."
- A take swapped for one with different length: the EDL is rebuilt, dialogue offsets are kept, and a dialogue clip extending beyond the new total length is trimmed with the note "Dialogue was trimmed to fit."
- Missing media file for a take (deleted from disk): the render fails at "Preparing shots" with "A shot file is missing: <scene>". Retry is offered after the user swaps the take.
- ffmpeg missing or a filter (for example `subtitles`/libass) unavailable: job fails with "ffmpeg is not available or lacks the subtitles filter. Run Settings & status to check." Existing doctor output is reused.
- Devanagari font not found at the configured path: the Hindi preset render fails at "Burning captions" with "Devanagari font not found at <path>. Set it in Settings." The font path is a new setting with a macOS default.
- Alignment fails or text is empty: fall back to line-level timing (see Captions); the render does not fail.
- Preview or export job failure keeps the previous good preview/final untouched.
- A second export clicked while one is running: ignored (button disabled); no duplicate version is created.
- Concurrent edit during export: the export renders the EDL snapshot taken when it started; later edits mark the working copy "Out of date" for preview only.
- Killed render: partial output files are never listed as a version; a version appears only after verification passes.
- ffprobe verification fails (wrong size, fps, codec, duration drift over 50 ms): export fails at "Verifying" with the first failing check named, no version is created.
- Media request with a malformed or missing range header: whole file served (200); invalid range: 416.
- Unknown version in the selector (deleted from disk): "This version's files are missing."

## Out of scope
- Music bed, ducking, music licensing (music slots in the EDL stay empty).
- Emotion hints and re-recording lines.
- M7 hardening: Playwright flows, full security pass, packaging, notifications, "Clean unused takes".
- Full 4-track timeline, caption and hashtag suggestions, visual QA, cloud rendering, auto-posting.
- Brand-kit screens and the end-card UI (end card stays off).
- Export-panel extras from the master Product Spec (Reveal in Finder, Copy to folder, pick cover frame, suggested caption text). Cover is automatic in M6.
- Editing caption timing, position and per-caption style; volume controls; full-screen mode for the player.

## Open questions
- Stage naming: the code today has project stages `ASSEMBLED` and `EXPORTED` (`src/reelforge/api/stages.py`), while req.md R15 names the new stage value `REEL_EXPORTED`. Should `REEL_EXPORTED` replace `EXPORTED` (and what happens to `ASSEMBLED`), or be added alongside? Tech spec to resolve with the owner.
- Does the owner want the exact safe-zone margins proposed above (top 250 px, bottom 250 px, sides 64 px at 1080x1920), or Instagram's own published values?
- Should the full-screen button and volume sliders from the master Product Spec be deferred, as assumed in Out of scope?
- Is reopening an older version meant to create a working copy that exports as the next version (assumed here), or edit that version in place? (Assumed: next version, never in place, per AC-9.)
- Already delegated at gate 1 to tech spec: mlx-audio forced alignment vs Whisper, and the Devanagari font default path.
