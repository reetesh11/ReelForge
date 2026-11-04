# Acceptance test plan — Add Hindi voice-overs (M4 Voice)

## Coverage
| Criterion | File | Test names | Red because |
| --- | --- | --- | --- |
| AC-3 (and AC-9 rules) | `tests/acceptance/test_m4_frames.py` | frames values/property/ValueError, check_speed/pause, plan_speed | `reelforge.voice.frames` and the new adapter functions do not exist |
| AC-4, AC-12 | `tests/acceptance/test_m4_worker.py` | run_batch (stub model, failure, distinct models), CLI mock batch, determinism, selftest, bad batch, import check | `tts_worker.py` does not exist |
| AC-5, AC-6 | `tests/acceptance/test_m4_adapter.py` | postprocess, run_batch (one subprocess, speed plan, crash, cancel), presets, doctor pass/fail/missing, selftest report | no `postprocess_wav`, `run_batch`, `selftest`, `WORKER_PATH`; doctor does not run a selftest |
| AC-7, AC-10 (settings) | `tests/acceptance/test_m4_settings.py` | models.toml, voice_model levels, CLI flags, voice_mem_gb levels and rejects, /voice-model, batch model id, manual-checks | tts entry is Kokoro, no new settings or route |
| AC-8 | `tests/acceptance/test_m4_voices.py` | locked before cast, presets, clone rules, upload accept/415/413, sniff/probe, library persistence and reuse | no voice routes or library voice |
| AC-1, AC-2, AC-9, AC-10, AC-11 | `tests/acceptance/test_m4_takes.py` | generate job, retake/active take frames, timing validation and pauses, stage, edit-text, stale, line fitting, upload recording, previews, memory | no voice job, routes or tables |
| AC-14 | `tests/acceptance/test_m4_unchanged.py` | M1 check details, doctor names, jobs keys, library without voice, other models | green now (`expect_red: false`) |

## Approach
Public surfaces only, through the interface contract: pure functions, the worker script (subprocess and `run_batch` with a stub model), the adapter, `check_mlx_audio`, and HTTP via `TestClient` on the mock backend (the voice job runs the real worker with `--backend mock` and real ffmpeg). `m4_helpers.py` builds a 5-line Hindi-text story, gets a project to `CAST_APPROVED`, and wraps `mlx_audio.WORKER_PATH` with a script that records the batch JSONL and then runs the real worker (used to check the model id, one subprocess, speed planning, crash, cancel). The acceptance conftest blocks outbound network for AC-12.

Assumptions: a new take becomes the active one; the worker `numpy` dependency must be added to the project environment (numpy is not installed today); the voice memory failure message is the exact contract string; story duration is written as `duration: <n>` in the YAML (extend-scene check).

All new tests fail today with missing modules, missing routes (404 or 405) or missing settings, not setup errors.

## Untestable criteria
- AC-13: manual listening on the reference Mac, recorded in `docs/manual-checks.md`.
- UI (VoiceBoard, Cast/Library Voice section, Settings voice select): not in the pytest set; verifier checks by reading code and web unit tests.

## Open questions
- none
