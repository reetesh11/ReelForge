# Acceptance test plan — Add Story stage

## Coverage
| Criterion | File | Test names | Red because |
| --- | --- | --- | --- |
| AC-1 | `tests/acceptance/test_m2_story_api.py`, `test_m2_story_files.py` | `test_structure_on_mock_saves_valid_version_and_put_moves_current`, `test_structure_empty_storyline_422`, `test_parse_story_valid_and_story_to_yaml_roundtrips` | `reelforge.story` and story routes do not exist |
| AC-2 | api, files | `test_put_and_import_reject_bad_story_naming_fields`, `test_put_empty_malformed_and_oversize`, `test_unknown_field_and_invalid_value_all_reported_with_paths`, `test_nested_unknown_field_path`, `test_invalid_values_name_the_field[*]` | no schema or endpoints |
| AC-3 | files, api | `test_roundtrip_preserves_comments_and_order`, `test_put_roundtrip_stores_text_exactly` | no yamlio module / PUT |
| AC-4 | `test_m2_story_llm.py` | `test_invalid_output_gets_exactly_one_repair_then_fails`, `test_non_json_output_also_one_repair`, `test_repair_valid_saves_version_with_two_calls`, `test_valid_first_reply_makes_one_call` | no MockLlm / structure task |
| AC-5 | api | `test_edit_after_approve_drafts_and_marks_only_that_scene`, `test_other_scene_field_and_character_look_staleness`, `test_semantically_identical_put_creates_version_but_nothing_stale` | no story routes, `AppContext.create(llm=)` missing |
| AC-6 | api | `test_import_and_export_byte_identical_with_zero_llm_calls`, `test_export_404_without_story` | no import/export |
| AC-7 | llm | `test_gap_question_*`, `test_gap_on_required_field_*`, `test_suggested_flag_*`, `test_no_suggested_flag_*`, `test_accepting_suggestion_*`, `test_answers_are_included_in_prompt` | no structure task |
| AC-8 | `web/tests/acceptance/story.test.tsx` | three Form/YAML sync tests | ProjectPage still shows the placeholder; no tabs |
| AC-9 | llm | mock LLM, backend selection, chat request shape, keep_alive, model from models.toml, temperature range, error messages, health, adapter error job | no `adapters.llm`/`mock_llm`, adapter lacks `chat`/`transport`; the autouse fixture blocks outbound network |
| AC-10 | files, api | `test_unsafe_tag_*`, `test_json_schema_*`, `test_schema_endpoint_served` | no yamlio/schema |
| AC-11 | api | `test_approve_flow_and_errors`, `test_approve_blocked_while_structure_job_runs` | no approve route |
| AC-12 | llm | `test_structural_rules_trigger_repair_round[*]`, `test_server_sets_target_language_and_version` | no structure task |

## Approach
Python tests use the public HTTP API (TestClient with real worker, `AppContext.create(..., llm=MockLlm(...))`), the contract's modules, and `httpx.MockTransport` for the Ollama adapter. Shared helpers are in `tests/acceptance/story_helpers.py`. The existing acceptance conftest blocks outbound network for all of them. Imports are lazy so a missing module fails only the test needing it. Web tests use the existing `stubFetch`/`renderApp` helpers and the contract's accessible names; the YAML editor is a textarea under test.
Gap-question path format for characters is assumed `characters.<key>.look`.

## Untestable criteria
- AC-8 is automated in vitest (`web/tests/acceptance/story.test.tsx`) but listed under untestable in tests.json because the tracker only reads pytest results.
- Monaco-specific behaviour (schema completion/hover, inline underline), approve button tooltip/confirm, version panel, and gap-question UI buttons are not covered by AC-8 tests; the verifier should check them by reading code.

## Open questions
- none
