# Acceptance test plan — image_mem_gb setting

## Coverage
| Criterion | File | Test names | Red because |
| --- | --- | --- | --- |
| AC-1 | `tests/acceptance/test_m3c_image_mem.py` | `test_default_is_6`, `test_config_toml_level`, `test_env_level`, `test_cli_level`, `test_precedence_cli_over_env_over_toml`, `test_cli_flag_reaches_settings[up/doctor]`, `test_cli_help_lists_flag[up/doctor]` | no `image_mem_gb` field, `[limits]` section or CLI flag yet |
| AC-2 | same | `test_env_rejects_bad`, `test_toml_rejects_bad`, `test_cli_mapping_rejects_bad`, `test_settings_direct_rejects_bad`, `test_small_positive_accepted`, `test_cli_bad_value_exits_2` | setting unknown: no error raised, or valid value rejected as extra field |
| AC-3 | same | `test_mem_need_default`, `test_mem_need_configured` | job still gets 10.0; Settings rejects `image_mem_gb` |
| AC-4 | same | `test_cast_preflight_failure_message`, `test_cast_succeeds_when_memory_enough` | message lacks hint; setting missing |
| AC-4 (unchanged) | `tests/acceptance/test_m3c_unchanged.py` | `test_non_cast_preflight_wording_unchanged` | green now: pins non-cast wording |
| AC-5 / R5 | `tests/acceptance/test_m3c_image_mem.py` | `test_no_generate_mem_gb_in_src`, `test_manual_checks_m3_documents_setting` | constant still exists; docs lack the note |

## Approach
Settings via `load_settings(cli, env, config_path)` and `Settings`; CLI via typer `CliRunner` with `run_doctor`/`run_up` monkeypatched; HTTP via existing `make_ctx`/`make_client` helpers with faked `available_gb` and `preflight_wait_s=0`.

## Untestable criteria
- AC-6: toolchain gate, run by the verifier.
- AC-7: manual on the reference Mac.

## Open questions
- none
