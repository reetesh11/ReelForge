# Acceptance test plan — Add voice emotion, character age and working speed to OmniVoice takes

## Coverage
| Criterion | File | Test names | Red because |
| --- | --- | --- | --- |
| AC-1 | `tests/acceptance/test_m6b_generate.py` | `test_speed_changes_take_length_in_the_right_direction` | `Settings` has no `emotion_mapping_path`; once it does, worker rows have no `target_speed` and speed is dropped, so take lengths do not change |
| AC-2 | `test_m6b_generate.py` | `test_sad_line_records_mapping_values_and_table_edit_affects_next_take_only`, `test_load_mapping_reads_a_custom_file`, `test_kokoro_does_not_apply_emotion` | `reelforge.voice.mapping`, `set-emotion` route and the `phrases` params do not exist |
| AC-3 | `test_m6b_generate.py`, `test_m6b_markup_age.py`, `test_m6b_stale_display.py` | `test_typed_tags_reach_the_model`, `test_display_and_speech_text`, `test_voice_card_text_is_clean_and_edit_box_keeps_markup`, `test_captions_in_the_edl_have_no_markup_or_tags` | `reelforge.story.markup` is missing; the card text and EDL captions still carry `<sad>` and `[sigh]` |
| AC-4 | `test_m6b_generate.py` | `test_two_phrases_two_model_calls_one_joined_take_with_gap`, `test_phrase_gap_setting_is_per_project_and_stales_only_multi_phrase_takes`, `test_picker_emotion_overrides_phrase_markup` | one row `s2` is sent instead of `s2#1`, `s2#2`; `/voices/settings` does not exist |
| AC-5 | `test_m6b_postprocess.py` | six tests (pitch up and down, tempo, gain, missing `rubberband`, `ffmpeg_has_filter`, argument lists) | `postprocess_wav` has no `semitones`, `tempo`, `gain_db`; `ffmpeg_has_filter` is missing |
| AC-6 | `test_m6b_markup_age.py`, `test_m6b_stale_display.py` | `test_emotions_and_check_emotion`, `test_parse_segments_*`, `test_story_accepts_emotion_and_rejects_unknown`, `test_story_rejects_bad_markup_in_line`, `test_set_emotion_unknown_value_and_unknown_line` | `story.markup` missing; story schema rejects `emotion` as an unknown field and accepts bad markup; `set-emotion` returns 404 |
| AC-6 (no emotion unchanged) | `test_m6b_unchanged.py` | `test_plain_line_has_exactly_todays_params_and_row` | green today, must stay green |
| AC-7 | `test_m6b_markup_age.py` | `test_check_age_values`, `test_age_band_boundaries`, `test_story_character_age_valid_and_invalid`, `test_set_age_api_and_cast_listing`, `test_set_age_rejects_invalid_and_saves_nothing`, `test_schema_models_have_emotion_and_age` | `story.age` missing; `Character.age` is an unknown field; `cast/{key}:set-age` returns 404 |
| AC-8 | `test_m6b_generate.py` | `test_preset_voice_gets_age_band_and_pitch_in_instruct`, `test_cloned_voice_always_gets_the_age_band` | worker rows have no `instruct`; no age exists |
| AC-9 | `test_m6b_stale_display.py` | `test_emotion_change_stales_only_that_line_and_starts_no_job`, `test_age_change_stales_only_that_characters_takes` | `set-emotion` and `set-age` routes do not exist |
| AC-10 | `web/tests/acceptance/m6b_voice.test.tsx` (vitest, not junit-tracked) | 14 tests | picker, panel, age and clip UI do not exist (12 red; 2 guards for preset voices pass) |
| AC-11 | `test_m6b_generate.py` | `test_full_voice_path_with_emotion_and_age_on_the_mock_backend` | emotion and age cannot be set yet |
| AC-12 | `test_m6b_unchanged.py` | `test_voices_response_omits_new_fields_when_empty`, `test_cast_items_omit_age_when_unset` | green today, must stay green; the frozen M1 to M6 suites are the rest of the proof |
| AC-13 | `test_m6b_generate.py`, `test_m6b_spike.py` | `test_mapping_direction_in_packaged_table`, `test_measure_*`, `test_the_tool_imports_no_reelforge_module` | `voice.mapping` and `tools/voice_sweep.py` are missing |
| AC-15 | `test_m6b_clips.py` | `test_sad_clip_is_the_reference_for_sad_lines_only`, `test_voice_without_clips_behaves_as_before` | clip routes and `set-emotion` do not exist |
| AC-16 | `test_m6b_clips.py` | upload, rejections, cloned-only, from-take, remove or replace staleness (5 tests) | `emotion-clips` routes return 404 |

## Approach
- Public surfaces only: HTTP through the `TestClient`, the modules named in the interface contract, and the worker `batch.jsonl` rows read through the existing `wrap_worker` helper. Take params and inputs are read from `Artifact` and `ArtifactInput` rows through `ctx.session_factory`.
- Mapping values are never taken from the packaged `emotions.toml`. Each test writes its own TOML (`m6b_helpers.MAPPING`) and points `Settings.emotion_mapping_path` at it, so a rewritten file also proves the "re-read on every generation" rule. The packaged table is only checked for direction (happy semitones above sad, fear duration scale below sad).
- Audio checks run on the mock WAVs and on a generated tone: zero-crossing frequency for pitch, RMS ratio for gain, the longest interior silent run for the phrase gap. I ran the pitch and gap helpers against a hand-built tone and a hand-built 150 ms gap, and the pitch helper against ffmpeg `rubberband` output, before relying on them.
- To check that the red tests fail for the right reason beyond the first `Settings` error, I temporarily ran the voice tests without `emotion_mapping_path` and saw them fail on missing routes, missing `target_speed`, `s2` instead of `s2#1`/`s2#2` and markup still in captions. The temporary edit is reverted.
- Picker overrides phrase markup, typed `[sigh]` reaches the model but not the screen, and the 150 ms gap is editable per project: these follow the owner answers in `answers.md`. Age is passed for cloned voices always, as the owner decided, so there is no spike gate in the tests.
- AC-9 shot staleness is checked through the line's `shot_length_stale` flag. The shots board is locked until the voices are approved, so a stale shot cannot be read through `/shots` right after an emotion or age change.

## Untestable criteria
- AC-10 (UI): covered by the vitest file above, which the junit-based tracking cannot run. The verifier should run `pnpm --dir web test --run`.
- AC-13 (measured table): the real-model sweep and the Status column and experiment log in `docs/voice-levers.md` need the reference Mac. The tests cover the `measure` function and the mapping direction only.
- AC-14: manual on the reference Mac, recorded in `docs/manual-checks.md`.
- Not covered for lack of a public surface in the contract: the story-structuring step proposing an age from the look text (R6, AC-7), the Kokoro age mapping (`Mapping.kokoro_age`) and the real model call with `duration_s`.

## Open questions
- How is the structuring step expected to propose an age? The contract names no function or LLM reply shape, so no test pins it.
- For Kokoro, does an age override a character's explicit preset voice or only act when none is set? No test pins it.
