# Acceptance test plan - Add Cast stage with Draw Things/mflux adapters and character library

## Coverage
| Criterion | File | Test names | Red because |
| --- | --- | --- | --- |
| AC-3 | `tests/acceptance/test_m3_cast_generate.py` | `test_four_candidates_with_consecutive_seeds_then_cache`, `test_regenerate_appends_four_more_seeds_and_refine_adds_one`, `test_generate_errors` | cast routes do not exist (404) |
| AC-6 | same | `test_cancel_after_image_two_keeps_two_and_stops` | no cast route |
| AC-11 | same | `test_bible_line_returned_and_edited_text_used_in_next_prompt` | no cast route |
| AC-9 | `tests/acceptance/test_m3_adapters.py` | `test_txt2img_one_request_pinned_model_no_batch`, `test_params_override_size_and_steps`, `test_img2img_sends_init_image_and_strength`, `test_error_messages`, `test_doctor_fails_when_pinned_model_is_rejected_with_422`, `test_doctor_passes_when_model_accepted` | `DrawThingsAdapter.run` missing; doctor does not probe the model |
| AC-12 | `test_m3_adapters.py`, `test_m3_cast_mflux.py` | `test_mflux_adapter_runs_argument_list`, `test_mflux_adapter_img2img_flags_and_failure`, `test_generation_runs_through_mflux_when_draw_things_is_down` | `reelforge.adapters.mflux` missing; Settings lacks `backend="real"`, `image_fallback`, `mflux_command` |
| AC-4 | `test_m3_cast_backend.py` | `test_unreachable_reported_and_generation_fails_with_exact_message`, `test_mflux_available_only_when_configured`, `test_mock_backend_is_always_reachable` | new Settings fields and cast GET missing |
| AC-5 | `test_m3_cast_approve.py` | `test_upload_png_and_jpeg_replace_candidates_with_generated_name`, `test_upload_rejects_wrong_content_and_oversize_without_side_effects` | upload route and `max_upload_mb` missing |
| AC-10 (and R9) | same | `test_stage_becomes_cast_approved_only_after_last_character`, `test_approve_unknown_candidate_404`, `test_approval_creates_master_library_record_and_mirror` | approve/reopen routes and library missing |
| AC-7 | same | `test_licence_warning_everywhere_and_approval_still_succeeds`, `test_licence_warning_text_rules`, `test_permissive_licence_has_no_warning_in_cast` | `/health` lacks `image_licence_warning`; `reelforge.cast.licence` missing; cast GET missing |
| AC-1 | `tests/acceptance/test_m3_library.py` | `test_second_project_gets_identical_master_look_seed_voice`, `test_use_library_requires_master_image` | library and use-library routes missing |
| AC-2 | same | `test_editing_look_creates_variant_and_library_original_is_unchanged`, `test_patch_only_name_aliases_tags` | library routes missing |
| AC-14 | `tests/acceptance/test_m3_unchanged.py` | 3 tests (expect_red false) | green now: pins `/health` shape, Draw Things `check()` and the 11 doctor names |
| AC-4/AC-7 UI (vitest, not in tests.json) | `web/tests/acceptance/cast.test.tsx` | 6 tests | `CastScreen` and the licence row do not exist |

## Approach
Backend tests build the app with `make_settings`, `make_ctx` and `make_client`, and use a `RecAdapter` (mock adapter that records seeds, prompts and inputs) from `tests/acceptance/m3_helpers.py`. Draw Things is a loopback stub HTTP server; mflux is a fake executable that logs its argv and writes a PNG. Cancel (AC-6) calls `ctx.queue.cancel(job_id)` from the adapter after image 2. The existing autouse network guard covers AC-8 for every test. Candidate checks use the cast API, artifact sidecars and the library API only. The `character.json` mirror is found by searching the data root for `library/characters/<cid>/character.json`.
Every red test fails on a missing route (404), a missing module or attribute, or an unknown Settings field.

## Untestable criteria
- AC-13: manual visual check with the real adapter on the reference Mac.
- AC-8: enforced implicitly by the outbound-network guard in `tests/acceptance/conftest.py`. No separate test.
- The vitest file `web/tests/acceptance/cast.test.tsx` is not tracked in `tests.json` because `test_files` runs pytest only. The verifier should run `pnpm --dir web test --run`.

## Open questions
- Reaching mflux when Draw Things is down: the contract does not say whether fallback is automatic without `backend:"mflux"`. The tests pass `backend: "mflux"` explicitly.

## Addendum: AC-15 and AC-16
| Criterion | File | Test | Red because |
| --- | --- | --- | --- |
| AC-15 | `tests/acceptance/test_m3_cast_approve.py` | `test_approval_creates_master_library_record_and_mirror` (record + character.json equality), `test_reapproving_same_character_creates_no_duplicate_library_record` (no duplicate) | approve route and library missing |
| AC-16 | `tests/acceptance/test_m3_cast_generate.py` | `test_progress_is_image_n_of_4_in_job_events` | cast generate route missing (404) |
