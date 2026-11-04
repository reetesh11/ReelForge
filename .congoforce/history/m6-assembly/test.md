# Acceptance test plan - Assembly stage (M6)

## Coverage
| Criterion | File | Test names | Red because |
| --- | --- | --- | --- |
| AC-15, R1, R8, R15 | `tests/acceptance/test_m6_edl.py` | default EDL, extra fields rejected, timeline maths, hash, save/load, presets, new settings, stage order | `reelforge.assembly` does not exist; `Settings` lacks the new fields; `STAGE_ORDER` lacks `REEL_EXPORTED` |
| AC-5, AC-14 (renderer), R6 | `tests/acceptance/test_m6_captions.py` | safe zone, `resolve_style`, ass header/styles/margins, events, edl style, karaoke only with words, word timing, proportional aligner, `ctx.aligner` | `reelforge.assembly.captions`/`align` missing |
| R1, R7, R9, R15, AC-3, AC-14, AC-15 | `tests/acceptance/test_m6_build_api.py` | `build_edl`, 409 gating, 404 project, state before build, build/force, trim, trim note, reorder, swap_take, crossfade cap, nudge, caption text edit (no voice take, .ass changes), caption style, debounce, new preview after edit | no `/assembly` routes (404) and no `reelforge.assembly` |
| AC-1, 2, 3, 4, 7, R2-R6 | `tests/acceptance/test_m6_render.py` | preview 540x960, final spec, loudness, progress+state, kill before/after each of 8 steps (16 cases), re-render no-op, changed EDL restart, dialogue offset, silent shot, captions.ass, aligner failure, missing shot file, filtergraph serialisation | `render_edl`, `filtergraph`, `ffmpeg` modules missing |
| AC-6, 8, 9, 10, 13, R10-R13, R16 | `tests/acceptance/test_m6_export.py` | handlers registered, preview job, scheduler, credits, licence 409 + accept, licence text variants, full export v001, range requests, v2 + reopen v1, open-version errors, export dedupe, EDL snapshot, failed export | job types, routes and publish module missing |
| Unchanged (AC-11) | `tests/acceptance/test_m6_unchanged.py` | `test_assembly_stage_unchanged_before_export` | green now and must stay green |
| R14 UI | `web/tests/acceptance/m6_assembly.test.tsx` (vitest, not junit-tracked) | Player, AssemblyScreen, ShotBoard hand-off | `@/assembly/AssemblyScreen`, `@/player/Player` missing |

## Approach
- Backend tests use the existing M5 helpers (`ready`, `shots_approved`) to reach SHOTS_APPROVED on the mock backend inside `with w.client:` (the worker runs). New helpers are in `tests/acceptance/m6_helpers.py`.
- Only contract surfaces are used: `reelforge.assembly.*` modules, `/assembly*` HTTP routes, `ctx.previews`, `ctx.aligner`, job types, `/media`.
- Media is measured with ffprobe/ffmpeg (ebur128, silencedetect, volumedetect). Loudness tolerance is 1.5 LU around -14 and true peak at most -0.9 dBTP; dialogue onset tolerance is 1/24 s + 20 ms.
- Kill tests raise a `BaseException` subclass from `RenderHooks` and assert on `state.json` and `step_runs` after a restart.
- Burn-in is not pixel-checked: this machine's ffmpeg lacks `subtitles`; tests assert `captions_burned is has_filter("subtitles")` and the `.ass` content. Per the contract, `captions.ass` is expected in the render output folder even when the burn is skipped.
- Licence tests rely on the packaged `models.toml` (image model is "Non-Commercial") and a tmp copy with the image licence set to `MIT` or empty.
- Every expected-red test fails today with `ModuleNotFoundError: reelforge.assembly...`, HTTP 404 on `/assembly` routes, a missing `Settings` field, or the old `STAGE_ORDER`.

## Untestable criteria
- AC-5 golden frame: no libass here; verifier checks a burned frame on a libass build.
- AC-8 browser playback/seek: vitest covers the Player component; pytest covers 206/416 on the exported file.
- AC-12: manual check in `docs/manual-checks.md`.
- AC-11: run the existing suite. The frozen `web/tests/unit/shotBoard.test.tsx` expects a disabled "Continue to assembly" button with zero approved shots; the contract says "Continue to Assembly" appears once every shot is approved. The new test matches `/continue to assembly/i` when all are approved and does not remove the old one.

## Open questions
- none blocking; see the report.
