# Interface contract — m3c-image-memory-setting

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
