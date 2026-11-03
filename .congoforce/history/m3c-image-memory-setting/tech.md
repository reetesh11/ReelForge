# Tech spec — Make the image job memory requirement configurable (image_mem_gb)

## Approach
Add `image_mem_gb` as a plain field on the frozen pydantic `Settings` in `src/reelforge/config.py`. The existing resolution (`load_settings`) already maps `REELFORGE_<FIELD>` env vars and CLI overrides generically, so only the `[limits]` TOML section (`_TOML_MAP`) and the CLI option need adding. Validation uses `Field(default=6.0, gt=0, allow_inf_nan=False)`; `load_settings` already turns pydantic errors into `ConfigError(msg, key=loc)`, so the key `image_mem_gb` is named for all three sources. `routes_cast.py` drops `GENERATE_MEM_GB` and enqueues with `ctx.settings.image_mem_gb` (read at job creation). The cast-specific hint is added in `jobs/worker.py::_run_heavy` where the failure is written: when `job.type == state.GENERATE_JOB` the error/message is rebuilt from `result.free_gb` and `result.need_gb`. `jobs/preflight.py` stays kind-agnostic, so non-cast wording and the frozen M1 tests are untouched. In `cli.py` a shared `ImageMemGb` Annotated option (same style as `Host`, `ApiPort`) is added to `doctor` and `up` and passed to `_settings`. No Architecture diagram (small change).

## Interface contract
- `reelforge.config.Settings.image_mem_gb: float` — default `6.0`; must be > 0 and finite. `Settings(image_mem_gb=0)`, `-1`, `"abc"` raise pydantic `ValidationError`.
- `reelforge.config.load_settings(cli=..., env=..., config_path=...) -> Settings`:
  - config.toml: `[limits]` section with key `image_mem_gb = <float>`; accepted without unknown-section error. Any other key under `[limits]` is `ConfigError`.
  - env: `REELFORGE_IMAGE_MEM_GB` (string, parsed to float).
  - CLI mapping key: `cli={"image_mem_gb": <float>}`.
  - Precedence CLI > env > config.toml > default.
  - Invalid values (0, -1, "abc", "") from any of the three sources raise `reelforge.config.ConfigError` with `.key == "image_mem_gb"` and `"image_mem_gb"` in `str(exc)`.
- CLI: `reelforge up --image-mem-gb <float>` and `reelforge doctor --image-mem-gb <float>`; help text "Memory (GB) an image job needs free before it starts." Invalid value: stderr `config error: image_mem_gb: ...`, exit code 2 (existing `_settings` behaviour); for `doctor` too. Valid value is passed into `Settings` handed to `run_doctor` / `run_up` (tests may monkeypatch those as existing CLI tests do).
- HTTP: `POST /api/projects/{project_id}/cast/{key}:generate` (existing route, unchanged path and body, including regenerate and refine bodies) returns 202 with job JSON whose `mem_need_gb == settings.image_mem_gb` (6.0 default; 3.5 when configured as 3.5).
- Job outcome: a `cast.generate` job whose pre-flight fails (fake `available_gb` below `image_mem_gb`, after `preflight_wait_s`) ends `status == "failed"` with `error` and `message` exactly `Only {free:.1f} GB free, job needs {need:.1f} GB. Close other apps, or lower image_mem_gb in config.toml.` With `available_gb` at or above the value, the job completes as before. Any other heavy job kind failing pre-flight keeps `Only {free:.1f} GB free, job needs {need:.1f} GB.`
- `reelforge.jobs.preflight.preflight(...)` and `PreflightResult.reason` are unchanged (non-cast wording).
- Removal: the name `GENERATE_MEM_GB` and any numeric cast-job memory literal no longer appear under `src/` (`reelforge.api.routes_cast.GENERATE_MEM_GB` no longer exists).
- Docs: `docs/manual-checks.md`, section "M3 Cast (AC-13)", mentions `image_mem_gb`, `REELFORGE_IMAGE_MEM_GB`, `--image-mem-gb`, `[limits]`, and the text "Only X GB free, job needs Y GB".

## Data and state changes
- Config: new `Settings.image_mem_gb: float = 6.0`; new TOML section `[limits]` (key `image_mem_gb`); new env var `REELFORGE_IMAGE_MEM_GB`; new CLI flag `--image-mem-gb`.
- No DB schema change (`mem_need_gb` column exists).

## Tasks
1. **Add the image_mem_gb setting** — `src/reelforge/config.py` (modified): add `image_mem_gb: float = Field(default=6.0, gt=0, allow_inf_nan=False)` to `Settings`; add `"limits": {"image_mem_gb": "image_mem_gb"}` to `_TOML_MAP`. `src/reelforge/cli.py` (modified): add `ImageMemGb = Annotated[float | None, typer.Option("--image-mem-gb", help="Memory (GB) an image job needs free before it starts.")]`; add `image_mem_gb: ImageMemGb = None` to `doctor` and `up` and pass `image_mem_gb=image_mem_gb` to `_settings`. Tests: `tests/unit/test_config_image_mem.py` (new).
2. **Use the setting for cast jobs and add the failure hint** — `src/reelforge/api/routes_cast.py` (modified): delete `GENERATE_MEM_GB`, use `mem_need_gb=ctx.settings.image_mem_gb`. `src/reelforge/jobs/worker.py` (modified): import `from reelforge.cast import state as cast_state` (or reuse an existing import of `GENERATE_JOB` if any; avoid circular imports, otherwise compare to the literal via a constant from `cast/state.py`), and in `_run_heavy`'s `if not result.ok:` branch set `reason = f"Only {result.free_gb:.1f} GB free, job needs {result.need_gb:.1f} GB. Close other apps, or lower image_mem_gb in config.toml."` when `job.type == cast_state.GENERATE_JOB`, else `result.reason`; use it for `error` and `message`. Tests: `tests/unit/test_cast_mem.py` (new).
3. **Document the setting** — `docs/manual-checks.md` (modified): under "M3 Cast (AC-13)" add a note (after the setup paragraph) on the setting, default 6.0, four ways to set it, the symptom, the fix, and restart requirement; add table row 14 for AC-7 (about 8 GB available renders 4 images; `REELFORGE_IMAGE_MEM_GB=20` fails with the message naming `image_mem_gb` and Retry).

Existing tests that reference 10.0 for cast jobs: grep `tests/` for `mem_need_gb` and `10.0` before commit 2; adjust only non-frozen tests, never frozen M1 ones.

## Implementation tests
- `tests/unit/test_config_image_mem.py`: default 6.0; each source alone (toml, env, CLI); precedence order; 0, -1, "abc", "" rejected per source with `ConfigError.key == "image_mem_gb"`; 0.5 and 0.1 accepted; `[limits]` unknown key rejected; CLI flag via Typer `CliRunner` on `up` and `doctor` (monkeypatch `run_up`/`run_doctor`), invalid gives exit 2.
- `tests/unit/test_cast_mem.py`: mock-backend API client, generate/regenerate/refine jobs report `mem_need_gb` equal to settings (default and 3.5); worker run with fake `available_gb` below value fails with exact cast message, above succeeds; a non-cast heavy job keeps the generic message; `GENERATE_MEM_GB` absent from `src/` (grep test).

## Risks and rollout
- Changing the default from 10.0 to 6.0 is intended; no migration. Queued jobs already in the DB keep their stored `mem_need_gb`.
- Waiting-state `message` (via `on_wait`) stays generic; only the final failure carries the hint.
- Restart required after changing the setting.

## Open questions
- none
