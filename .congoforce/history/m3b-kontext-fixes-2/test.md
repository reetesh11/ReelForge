# Acceptance test plan — Kontext default, per-model steps, Draw Things probe fix

## Coverage
| Criterion | File | Test names | Red because |
| --- | --- | --- | --- |
| AC-1 | `tests/acceptance/test_m3b_kontext.py` | `test_probe_is_128_by_128_one_step`, `test_check_passes_for_known_model_against_size_strict_stub` | probe still sends 64 x 64, so a size-strict stub returns 422 |
| AC-1 (unchanged) | `tests/acceptance/test_m3b_unchanged.py` | `test_check_fails_with_message_when_model_rejected`, `test_check_timeout_counts_as_ok` | green now: 422 message and timeout handling already exist |
| AC-2 | `tests/acceptance/test_m3b_kontext.py` | `test_steps_precedence_task_then_entry_then_four[False/True]`, `test_model_entry_steps_validation_and_loading` | `ModelEntry.steps` missing; adapter ignores the entry (sends 4, not 20) |
| AC-3 | `tests/acceptance/test_m3b_kontext.py` | `test_packaged_image_entry`, `test_cast_generate_and_refine_send_kontext_model_and_20_steps` | packaged entry is still Schnell with no steps |
| AC-4 | `tests/acceptance/test_m3b_kontext.py` | `test_packaged_registry_warns_in_health_and_cast_and_sidecars_record_licence` | packaged licence is Apache-2.0, so no warning |
| AC-5 | `tests/acceptance/test_m3b_unchanged.py`, revised `test_m3_unchanged.py::test_health_has_no_licence_key_for_permissive_default_model`, revised `test_m3_cast_approve.py::test_permissive_licence_has_no_warning_in_cast` | `test_explicit_permissive_model_has_no_warning` and the two revised tests | green now and after: they set a permissive model via a temporary `models.toml` |

## Approach
Tests use public surfaces only: `DrawThingsAdapter.check()/run()`, `ModelEntry`, `load_models`, the packaged `models.toml`, and the HTTP API through the existing helpers. A local size-strict stub (422 for width or height below 128 or an unknown model) reproduces the real server. The cast job test runs the real backend against the recording stub, for generate and refine, and checks `model` and `steps` of every request. Approval confirmation ("Approve anyway") is UI-only; the backend test checks that approval succeeds. R7 revisions: the two named tests now use `models_with_license(..., "Apache-2.0")`; `web/e2e/cast.spec.ts` clicks "Approve anyway" after "Approve this one".

## Untestable criteria
- AC-6: toolchain gate run by the pipeline (Playwright flow uses the revised e2e spec).
- AC-7: docs wording; the verifier reads `docs/manual-checks.md` M3 rows 2, 4 and 11.
- AC-8: manual on the reference Mac with real Draw Things and Kontext.

## Open questions
- none
