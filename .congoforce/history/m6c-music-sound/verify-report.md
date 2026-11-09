# Verify report: m6c-music-sound

**Result: PASS** (with deferred items the owner accepted at verify; see Open items).

## Pass 1: spec compliance
Executable checks passed (checks.md: 1066 tests, frozen set intact). Judged by reading code and tests:

| AC | Verdict | Evidence |
| --- | --- | --- |
| AC-1 | met | `story/audio.py`, `story/schema.py`; test_m6c_schema.py. Old `music` still loads. |
| AC-2 | met | `audio/generate.py`, `audio/fit.py`; versioned takes, earlier kept. |
| AC-3 | met | `audio/uploads.py` (size 413, content 415); `fit_to_length` loops with crossfade or trims. |
| AC-4 | met | `build_mix_graph` in `assembly/filtergraph.py`; ffmpeg argv with no shell; test_m6c_mix.py measures windows. |
| AC-5 | met | `duck_expression`: attack and release ramps, depth from `duck_db`, music cues with `duck` only. |
| AC-6 | met | `silence_expression` gates the cue bus only; dialogue untouched. |
| AC-7 | met | `story/staleness.py`; no job started. |
| AC-8 | met | `web/src/sound/*`, vitest acceptance. |
| AC-9 | met | `audio/seed.py`; suggested cues generate nothing until approved. |
| AC-10 | met | `assembly/publish.py` credits and licence check; `cast/licence.py`. |
| AC-11 | met | Mock-only backend path; no network. |
| AC-12 | met | Frozen set intact. |
| AC-13, AC-14 | open (manual) | Deferred by owner. `docs/audio-levers.md` is a pending stub. |

## Pass 2: quality
No blocking defects found. Cue chain construction is clear, files are written via `.part` then replaced, and licence gating rejects non-commercial `audio_*` entries at load.

Architecture comparison: all diagram components exist except `adapters/audio_gen.py` and `adapters/audio_worker.py` (real adapters, task 17). That is deferred by the owner.

## Open items for the PR body
- AC-13 (spike on reference Mac), AC-14 (Gujiya listening check) and task 17 (real adapters) are open. `models.toml` has placeholder entries only.
- EDL deviation: working and exported `edl.json` always carry `audio` and `mix`. Accepted by the owner.
