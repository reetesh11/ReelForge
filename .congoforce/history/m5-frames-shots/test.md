# Acceptance test plan - Key frames and shots (M5)

## Coverage
| Criterion | File | Test names | Red because |
| --- | --- | --- | --- |
| AC-1, AC-17, AC-18 | `tests/acceptance/test_m5_frames.py` | `test_frame_job_gets_master_and_prompt_with_look_verbatim`, `test_master_choice_...`, `test_two_characters_...`, `test_regenerate_...`, `test_generate_all_one_job_per_frame_in_story_order`, `test_board_shows_active_jobs_..._cancel_stops_them`, `test_save_prompt_...`, `test_set_framing_...` | `/frames` endpoints and `reelforge.frames` do not exist (404, ModuleNotFoundError) |
| AC-2 | same | `test_pack_image_is_second_input_...`, `test_missing_pack_image_...`, `test_pack_outside_data_root_...` | no frame job, no pack handling |
| AC-10, AC-11 (frames) | same | `test_frames_approved_only_when_...`, `test_editing_an_approved_frame_...`, `test_action_change_stales_only_that_scenes_frame_...`, `test_approve_errors_...`, `test_frames_need_voices_approved` | gates and staleness not implemented |
| AC-12 (image) | same | `test_upload_replacement_...` (2), `test_uploaded_frame_stales_only_by_story_change` | upload endpoint missing |
| AC-13 | all M5 files | autouse network guard in `conftest.py`; every flow runs on the mock backend | n/a |
| AC-7 (image side) | same | `test_frame_memory_shortfall_names_image_mem_gb_...` | frame job missing |
| prompt helpers, MockLlm | same | `test_compose_frame_prompt_...`, `test_mock_llm_writes_scene_sentence_and_motion_prompt` | `reelforge.frames.prompts` missing; MockLlm ignores the schemas |
| AC-3, AC-8, R12 | `tests/acceptance/test_m5_shots.py` | `test_talking_shot_inputs_...`, `test_action_shot_has_no_audio_input_...`, `test_last_frame_is_extracted_...`, `test_continue_previous_frame_...`, `test_board_types_sizes_...` | `/shots` endpoints and `gen_shot` missing |
| AC-4 | same | `test_reroll_adds_a_take_to_that_shot_only`, `test_reroll_without_a_shot_is_409` | no re-roll |
| AC-6 | same (+ adapter file) | `test_killed_shot_is_oom_once_...[adapter_error,exit137,exit_minus9]`, `test_oom_at_draft_...`, `test_other_failure_is_not_oom` | no shot job / classification |
| AC-7 | same | `test_shot_memory_shortfall_...`, `test_shot_mem_gb_setting_is_used_...`, `test_only_one_heavy_job_at_a_time` | `shot_mem_gb` setting missing |
| AC-9 | same | `test_render_all_...`, `test_queue_estimates_total_reorder_...`, `test_estimate_uses_recorded_render_times_...`, `test_pause_lets_...`, `test_cancel_stops_the_running_shot_...`, `test_generic_job_cancel_...` | no queue |
| AC-10, AC-11 (shots) | same | `test_action_change_stales_only_...`, `test_new_voice_take_stales_only_...`, `test_changed_approved_frame_stales_its_shot`, `test_shots_approved_only_when_...`, `test_editing_an_approved_frame_reopens_only_...`, `test_shots_need_key_frames_approved`, `test_overrides_and_quality_...` | staleness/gates missing |
| AC-12 (clips) | same | `test_upload_clip_is_checked_by_content_...`, `test_upload_clip_oversize_...` | endpoint missing |
| AC-5, R5, R6 | `tests/acceptance/test_m5_ltx_adapter.py` | `test_required_flags_exact`, `test_parse_flags_...`, `test_check_*` (6), `test_doctor_check_ltx_...`, `test_run_a2v_argv`, `test_run_generate_...`, `test_steps_only_when_...`, `test_exit_137_and_minus_9_are_oom`, `test_other_nonzero_exit_...`, `test_timeout_...`, `test_cancel_...` | stub adapter has no flag parsing, `run`, or new constructor args |
| AC-7 settings, R7 | `tests/acceptance/test_m5_settings.py` | `test_shot_mem_*`, `test_shot_mem_flag_...`, `test_shot_quality_and_sizes_...`, `test_shot_size_must_be_...`, `test_packaged_video_model_has_steps_...` | `Settings` has no such fields; models.toml has no steps |
| AC-14 | `tests/acceptance/test_m5_unchanged.py` | 4 tests (expect_red false) | green now: ltx stub messages, doctor key/position, defaults, M1 job keys |

## Approach
- Backend pytest on the mock backend, public surfaces only: HTTP via `TestClient`, `Settings`, `LtxAdapter`, `check_ltx`, `compose_frame_prompt`, `MockLlm`, plus the existing DB models read-only (artifacts, scenes, jobs) and `story.service.save_version(keep_stage=True)` to change a scene action exactly like the voice board does.
- `m5_helpers.py`: `World` (mock app with `M5Adapter` that records every TaskSpec and can slow, fail or exit-kill video jobs through the mock adapter's own hooks, a memory box and an Ollama-unload counter), story with talking scenes s1/s2/s5, a two-character action scene s3 and a continue scene s4, and a fake `ltx-2-mlx` script whose `--help` per subcommand and run behaviour are configurable.
- Every M5 test fails today because the endpoint, module, setting or adapter method is missing (404, ModuleNotFoundError, pydantic extra-field error, AttributeError), not because of the setup. The M4 setup (cast, voices) is exercised and works.
- Mock MP4 checks use ffprobe (size, `nb_frames`, audio stream only for talking).

## Untestable criteria
- AC-15: manual run on the reference Mac (docs/manual-checks.md).
- Web board copy and controls: no tracked vitest; the verifier checks them against the contract.
- Real-backend engine gating (Render disabled while `ltx` check fails): needs real wiring; flag check itself is tested.

## Open questions
- Contract says `reelforge serve --shot-mem-gb`; the CLI has no `serve`, only `up`. The test uses `up` and `doctor`.
- After a regenerated voice take or a regenerated frame the stage drops below FRAMES_APPROVED and `/shots` is 409 until the user re-approves; `test_new_voice_take_...` re-approves frames (idempotent approve) to bring the gate back. If approving an already approved frame is not allowed, that test needs revising.
- Action change on a project past voices: the contract lets `PUT story` reset the stage to DRAFT; the tests change the action with `save_version(keep_stage=True)` so the boards stay reachable.

## Per-criterion index (tests.json entries)
AC-1, AC-2, AC-11, AC-12, AC-13, AC-16, AC-17, AC-18: `test_m5_frames.py`. AC-3, AC-4, AC-6, AC-7, AC-8, AC-9, AC-10: `test_m5_shots.py`. AC-5, R5, R6: `test_m5_ltx_adapter.py`. R7: `test_m5_settings.py`. AC-14: `test_m5_unchanged.py` (green now). AC-16 is covered at API level by `test_approve_errors_*` (approving a stale item is rejected); the disabled button is UI. AC-15 is untestable (manual).
