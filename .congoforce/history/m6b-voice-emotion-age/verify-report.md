# Verify report: m6b-voice-emotion-age

## Result
PASS for the code, with three items the PR reviewer or owner must close: the real-model sweep (AC-13), the listening check (AC-14), and the vitest run for the UI (AC-10).

## Pass 1: spec compliance
| Criterion | Verdict | Evidence |
| --- | --- | --- |
| AC-1 speed | met | The worker turns `estimated length x duration_scale / target_speed` into `duration_s` (`tts_worker.py`). The mock honours it. The target is recorded and omitted at 1.0. |
| AC-2 mapping and params | met | `voice/emotions.toml` is the single table, read on every take. `PhrasePlan.recorded()` stores the applied values. `effective.values_stale` marks old takes stale after an edit. |
| AC-3 no markup on screen or in captions | met | `display_text` strips markup and `[...]` tags. Cards and EDL use it. Raw text is kept in `edit_text`. |
| AC-4 phrases | met | One batch row per phrase. `join.py` writes sample-exact silence. The phrase edge pad is 0. |
| AC-5 ffmpeg | met | `rubberband=pitch:tempo` and `volume` run as argument lists. A missing filter raises the "Install ffmpeg-full" message and fails the take. |
| AC-6 unknown emotion | met | `check_emotion`, the story schema validator and the 422 on set-emotion. A line with no emotion records no new params. |
| AC-7 age | met | `check_age`, `age_band`, the schema field and the set-age API. |
| AC-8 age in instruct | met, with a deviation | The band goes into `instruct` for preset voices and always for cloned voices, per owner answers 3 and gate2. The spec and req wording about a spike-gated setting is superseded. |
| AC-9 staleness | met | An emotion edit writes a story change row for that scene only. An age edit goes through `voice_changed`. No job starts. |
| AC-10 UI | met by reading code, vitest unconfirmed | The emotion picker, the "How this will sound" panel, age and band, and the clip rows exist. The vitest file is not in the pytest checks. |
| AC-11 mock path | met | The full path test runs on the mock backend with the network blocked. |
| AC-12 frozen tests | met | checks.md reports the frozen set intact. The one failure is the existing Playwright test. |
| AC-13 spike | partly | The tool and the direction test exist. The sweep has not been run and no table is in the docs. |
| AC-14 manual | open | The table is written and its results are blank. |
| AC-15 and AC-16 clips | met | The clip is `ref_audio` and `ref_text` for matching lines only and is recorded as a take input. Upload, from-take, content, size and transcript checks. `clip_changed` stales only takes whose recorded phrases used that clip. |

Built beyond the spec: a per-project phrase gap endpoint (owner answer 5) and the Kokoro experimental age mapping (R7). Neither is a problem.

## Pass 2: quality
No correctness bugs found. Details are in verify-review.json. In short:
- `adapters/mlx_audio.py`: the OmniVoice atempo path is now unused by generate.
- Cloned-voice age is always sent. This is an owner decision.
- `pyyaml` was added as a dev dependency for a test.
- The architecture diagram matches the code.

## For the reviewer
- Run `cd web && npx vitest run` to cover AC-10.
- On the reference Mac, run `tools/voice_sweep.py` and paste the table into `docs/voice-levers.md`. Adjust `emotions.toml` if needed, then complete the M6b section of `docs/manual-checks.md`.
- checks.md lists one failing test, `test_ac11_web.py::test_playwright_flows_pass`, as a pre-existing failure.
