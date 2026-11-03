# Verify report — m3c-image-memory-setting

## Result
PASS — all criteria met by code reading; helper checks green (383 tests, lint, typecheck, build).

## Acceptance criteria
| # | Criterion | Status | Evidence |
| --- | --- | --- | --- |
| AC-1 | Default 6.0, toml/env/CLI(up, doctor), precedence | met | config.py `image_mem_gb` field, `_TOML_MAP["limits"]`; cli.py `ImageMemGb` on up and doctor; acceptance tests |
| AC-2 | 0, -1, abc rejected naming image_mem_gb | met | `Field(gt=0, allow_inf_nan=False)`; existing load_settings error mapping; 20 acceptance tests |
| AC-3 | mem_need_gb equals setting | met | routes_cast.py `mem_need_gb=ctx.settings.image_mem_gb` (single enqueue path covers generate, regenerate, refine) |
| AC-4 | Cast failure message with hint, others unchanged | met | worker.py:163-168 branches on `GENERATE_JOB`; preflight.py untouched; non-cast test in test_m3c_unchanged.py |
| AC-5 | GENERATE_MEM_GB removed | met | grep of src finds none; no hard-coded cast figure |
| AC-6 | Toolchain and suite | met | checks.md; frozen set intact |
| AC-7 | Manual on reference Mac | not executed | Untestable here; row 14 added to docs/manual-checks.md |

## Spec compliance
R5 docs note and table row 14 present. Nothing built beyond the spec.

## Code quality
Small, follows the existing option and settings patterns. Notes only: the hint string duplicates the generic wording (worker.py:163); unit test file test_cast_mem.py is thin but acceptance tests cover the behaviour.

## Recommendation
Ready for a human reviewer; AC-7 still needs the manual run on the reference Mac.
