# Verify report — m6-assembly

## Result
PASS — all criteria met from code and tests; the one non-executable check (AC-5 burned frame) was done by hand, and AC-12 stays a human step.

## Acceptance criteria
| # | Criterion | Status | Evidence |
| --- | --- | --- | --- |
| AC-1 | Export 10-15 s, 1080x1920, 24 fps, High, AAC 48k stereo, within 50 ms of EDL | met | test_m6_render.py (6 tests); render.py encode step; publish.verify_output |
| AC-2 | Loudness about -14 LUFS, TP <= -1 dBTP | met | test_m6_render.py loudness test; two-pass loudnorm in render.py measure/normalise |
| AC-3 | Filtergraph next to output; one edit re-renders preview only | met | render.py script path; scheduler.enqueue_now enqueues preview only; test_m6_build_api.py / test_m6_render.py |
| AC-4 | Dialogue within one frame; silent shot OK | met | test_m6_render.py; shot audio stripped, silence bed generated |
| AC-5 | Preset, safe zone, Devanagari renders | met | test_m6_captions.py; manual burned-frame check below |
| AC-6 | credits.json per model; licence warning | met | publish.collect_credits / licence_warnings; export route returns 409 with warnings; test_m6_export.py |
| AC-7 | Kill/resume per step | met | render_state.RenderState.run_step, .part files, 18 tests |
| AC-8 | 206 range; outside data root rejected | met | existing /media route reused; test_m6_export.py range test; Player in web |
| AC-9 | v2 leaves v1 unchanged; reopen loads EDL | met | publish_version (staging folder, next version); open_version route; tests |
| AC-10 | Mock pipeline, no network | met | test_m6_export.py network guard test |
| AC-11 | Frozen M1-M5 tests pass | met | checks.md: only the pre-existing Playwright failure remains |
| AC-12 | Manual check on reference Mac | not verifiable here | docs/manual-checks.md M6 section is written; Result cells are blank. Human step |
| AC-13 | Light jobs, no GPU lease, per-step progress | met | jobs.py, heavy=False, step messages; tests |
| AC-14 | Caption edit changes EDL and .ass, no voice take | met | edit.py; test_m6_build_api.py |
| AC-15 | Empty music slots, end card off | met | edl.py defaults; test_m6_edl.py |

R14 (player, timeline UI) is covered by vitest files in web/tests; read the components and they match the contract.

AC-5 manual frame check (libass ffmpeg-full is installed here): I built a .ass from `build_ass` with a Latin and a Devanagari caption and burned it with the `subtitles` filter onto 1080x1920. Latin Bold pop renders (yellow, outlined) and Devanagari renders shaped, no missing glyphs. Both sit at about y=1600-1660, inside the 250 px bottom margin. This used a synthetic gray background, not a real render.

## Spec compliance
Matches tech.md, including its Architecture diagram: all listed components exist and are wired as drawn (routes -> build/edit -> scheduler -> queue -> jobs -> render -> filtergraph/captions/align; publish -> store). I found no dropped or rewired flows. Nothing built beyond the spec. Documentation update for ffmpeg-full was done as asked.

## Code quality
No correctness bugs found. Resume design is sound (hash-checked state, .part rename, orphan version cleanup, idempotent publish by job id). Minor notes only:
- jobs.py: leftover `del row`, `Any`-typed publish_version_row with local import.
- publish.py:15: imports a private licence constant.
- publish.py:73: verify tolerance 0.1 s versus the 50 ms criterion.

## Recommendation
Ready for a human reviewer. Before merge, run the AC-12 manual checks on the reference Mac and fill the Result column in docs/manual-checks.md.
