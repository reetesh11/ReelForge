# Acceptance test plan — M6c music, background score and sound effects

## Coverage
| Criterion | File | Red because |
| --- | --- | --- |
| AC-1 | `tests/acceptance/test_m6c_schema.py` | `audio` is "unknown field" in story.yaml; no cue models, `story_timeline` or `resolve_cue` |
| AC-2 | `test_m6c_generate.py`, `test_m6c_flow.py` | cue routes and `reelforge.audio` missing; mock audio ignores duration (1.0 s, not requested) |
| AC-3 | `test_m6c_generate.py` | upload route and `fit_to_length` missing (`reelforge.audio` not found) |
| AC-4 | `test_m6c_mix.py`, `test_m6c_flow.py` | `EdlAudio`/`EdlMix` not in `reelforge.assembly.edl`; no cue mixing in `build_mix_graph`; no preview-mix route |
| AC-5 | `test_m6c_mix.py` | ducking not implemented (`EdlAudio`/`EdlMix` missing) |
| AC-6 | `test_m6c_mix.py` | silence spans do not affect music, sfx or ambience yet |
| AC-7 | `test_m6c_generate.py`, `test_m6c_flow.py` | no per-cue stale tracking or audio_take/audio_mix change kinds |
| AC-8 | `test_m6c_cues_api.py`, `web/tests/acceptance/m6c_sound.test.tsx` (vitest, 22 tests, not tracked by the pytest-only command) | `/audio` API and Sound screen do not exist |
| AC-9 | `test_m6c_generate.py`, `test_m6c_seed.py` | `suggest_cues` and approve/dismiss missing; structuring adds no cues |
| AC-10 | `test_m6c_licence.py`, `test_m6c_generate.py` | `COMMERCIAL_LICENCES`, `ModelLicenceError`, `max_seconds`, credits list missing |
| AC-11 | `test_m6c_flow.py` | whole path depends on the missing pieces above |
| AC-12 | `test_m6c_unchanged.py` | green today on purpose (`expect_red: false`): old stories, EDL hash, dialogue-only graph, 1.0 s mock audio, commercial models |
| AC-13 | `test_m6c_spike.py` | `tools/audio_spike.py` does not exist |
| AC-15 | `test_m6c_generate.py` | audio field rejected on save |
| AC-16 | `test_m6c_flow.py` | cues are not mixed, so loudness cannot be measured |

## Approach
Tests use only public surfaces from the interface contract: HTTP routes through the test client, `build_mix_graph` plus real ffmpeg on known tones (measured with level and loudness analysis), the models registry, `tools/audio_spike.py`, and the module constants. Shared helpers are in `tests/acceptance/m6c_helpers.py`. The mock backend is used throughout. Each red test fails with an "unknown field" 422, a missing import or a wrong value, never a typo or broken fixture. `congoforce try-tests` reports PASS.

## Untestable criteria
- AC-14: manual. The owner re-exports the Gujiya reel with the ten reference cues on the reference Mac, listens, and records the verdict in `docs/manual-checks.md`.
- Parts of AC-13: the reference-Mac table and `docs/audio-levers.md` are manual.

## Open questions
- none
