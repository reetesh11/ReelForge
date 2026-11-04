# Verify report — m4-voice

## Result
PASS — all testable criteria are met by code and tests; AC-13 remains a manual check. One major item (unverified real OmniVoice call shape) needs confirming on the Mac.

## Acceptance criteria
| # | Criterion | Status | Evidence |
| --- | --- | --- | --- |
| AC-1 | Shot length from active take | met | `voice/service.py` approve_line uses the active take; `write_take` makes the new take active; test_m4_takes |
| AC-2 | Only the edited line and its scene go stale | met | `edit_text` records story_changes for that scene only; `_take_out` / `build_lines` stale logic; test_m4_takes |
| AC-3 | frames = 8k+1 (73, 81) | met | `voice/frames.py:frames_for` (9-frame minimum per gate2); test_m4_frames |
| AC-4 | Worker: 3 WAVs, per-line error, one load | met | `tts_worker.py:run_batch` caches loader per model; test_m4_worker |
| AC-5 | ffmpeg trim, -16 LUFS, 48 kHz | met | `mlx_audio.py:postprocess_wav` two-pass measure then gain plus limiter; test_m4_adapter |
| AC-6 | doctor blocking selftest check | met | `doctor.py:check_mlx_audio` fails on missing env or failed selftest |
| AC-7 | OmniVoice/Kokoro models, voice_model, Status | met | `models.toml`, `config.py`, `VOICE_MODELS`; test_m4_settings |
| AC-8 | Voice in library, content-checked uploads | met | `voice/uploads.py` sniff plus ffprobe, size limit, generated names; `slots.sync_to_library` / `adopt_from_library` |
| AC-9 | Speed and pause ranges, durations include pauses | met | `check_speed`, `check_pause` (422); `approve_line` adds both pauses |
| AC-10 | voice_mem_gb preflight | met | Job enqueued heavy with `mem_need_gb=voice_mem_gb`; message in `jobs/worker.py`; config gt=0 validation |
| AC-11 | VOICES_APPROVED rules | met | `recompute_stage`; edit clears only that line's approval |
| AC-12 | Mock backend, no network | met | `--backend mock`, mock synth; acceptance conftest blocks network |
| AC-13 | Manual listening | not run (expected) | Section and 11-step table added to `docs/manual-checks.md`, results empty |
| AC-14 | Frozen M1 to M3c tests | met | checks.md: frozen set intact, 519 passed; `save_version` changes are opt-in kwargs |

## Spec compliance
Architecture matches the tech.md diagram: routes, voice service, generate handler registered in worker HANDLERS, adapter through runner to tts_worker, ffmpeg, doctor and config. No component was dropped or rewired. Extras beyond the spec are small (preset preview job, library read-only voice summary, accepted in answers.md).

## Code quality
- Major, `adapters/tts_worker.py:106`: real OmniVoice voice-description and cloning arguments cannot be tested here; confirm in the AC-13 run.
- Note, `voice/service.py` (enqueue_generation): a request made while another voice job is queued or running returns that job instead of the requested work.
- Note, `doctor.py:170`: synchronous real selftest, up to 120 s.
- Note, `tts_worker.py:150`: the real selftest without a model id only imports mlx_audio.
- Note, `voice/service.py`: 1065 lines in one module; local imports to avoid cycles.
- The adapter, worker and runner streaming code is clean: argument lists, timeout, cancel, error per line, and clean-up of temp dirs.

## Recommendation
Ready for a human reviewer. Run the AC-13 manual checks on the reference Mac and record the results, including OmniVoice cloning. I did not run the web unit tests or inspect the UI in depth.
