# Acceptance test plan — Build the ReelForge M1 backbone

## Coverage
| Criterion | File | Test names (summary) | Red because |
| --- | --- | --- | --- |
| AC-1 | `tests/acceptance/test_ac01_config.py` | default / toml / env / cli levels, None ignored, data_root discovery, host, port, malformed TOML, unknown key | `reelforge.config` does not exist |
| AC-2 | `tests/acceptance/test_ac02_models.py` | packaged keys, no model id under `src/`, editing models.toml changes sidecar `model_id`, missing license | `reelforge` package / `models.toml` missing |
| AC-3 | `tests/acceptance/test_ac03_artifact_metadata.py` | row vs sidecar for image/audio/video jobs and direct writes | store, service, API not implemented |
| AC-4 | `tests/acceptance/test_ac04_cache.py` | hit with no job, new seed, missing/corrupt file or sidecar, atomic write, fingerprint | `reelforge.artifacts.*` missing |
| AC-5 | `tests/acceptance/test_ac05_recovery.py` | SIGKILL `reelforge up` mid heavy job then `recover_orphans`; dead-pid row | no CLI / queue; `up` exits 2 (unknown command) |
| AC-6 | `tests/acceptance/test_ac06_jobs.py` | cancel running/queued, retry once then failed (2 runs), no retry for AdapterError, exit code, unknown type, manual retry | `reelforge.jobs` missing |
| AC-7 | `tests/acceptance/test_ac07_preflight_lease.py` | preflight reason/unload/wait, job not started on low memory, no lease overlap, lease release | `reelforge.jobs.preflight/lease` missing |
| AC-8 | `tests/acceptance/test_ac08_oom.py` | `classify_exit`, runner on -9/137, job reason | `reelforge.jobs.classify` / runner missing |
| AC-9 | `tests/acceptance/test_ac09_doctor.py` | CHECKS order, report props, `doctor` table + exit codes, `up` refuse / `--allow-degraded` / step order, `/health` parity, disk/memory/ports/licenses rules | `reelforge.doctor`, `cli` missing (disk/memory also need psutil) |
| AC-10 | `tests/acceptance/test_ac10_security.py` | `/media` 403 for `..` and symlink, 404s, host validation, loopback-only listener (lsof), no `shell=True` | API not implemented; `src/reelforge` absent |
| AC-11 | `tests/acceptance/test_ac11_web.py` | runs vitest suite and Playwright flows | `web/package.json` missing |
| AC-12 | `tests/acceptance/test_ac12_network_guard.py` | guard refuses non-loopback, allows loopback (guard is `conftest.py`, active for every test) | green now (unchanged behaviour) |
| AC-13 | `tests/acceptance/test_ac13_database.py` | tables + WAL, pragmas, model table names, ULIDs, relative paths, data root layout | `reelforge.db` missing |
| AC-14 | `tests/acceptance/test_ac14_media_range.py` | 200 full, 206 `a-b`, `a-`, `-n`, 416 | `/media` not implemented |
| AC-15 | `tests/acceptance/test_ac15_api.py` | project CRUD/422/order, stages + locking, artifacts endpoint, jobs list/filter/cancel/retry, WS events, `health.changed`, openapi export + drift | API not implemented |
| AC-16 | `tests/acceptance/test_ac16_runner.py` | JSON logging, `adapter.command` argv verbatim, timeout kill, log file, job timeout reason | `reelforge.logging` / runner missing |

Web tests run through `test_ac11_web.py` (the `test_files` command is pytest only). The suites themselves, which the implementer must make pass:
- `web/tests/acceptance/events.test.tsx`: query keys, `eventToQueryKeys`, `useEventStream` invalidation and 500 ms to 8 s backoff.
- `web/tests/acceptance/projects.test.tsx`: nav, redirect, reconnect banner, dark class in `index.html`, skeleton/list/empty/error/create.
- `web/tests/acceptance/stages.test.tsx`: stepper badges, `aria-disabled`, placeholder text, not found.
- `web/tests/acceptance/settings.test.tsx`: dependency rows (green/amber/red, `Fix:`), refresh on `health.changed`.
- `web/e2e/live-progress.spec.ts`: list and stepper render; progress over `/ws/events` with zero `/api/v1/jobs` requests.
- Frozen config: `web/vitest.config.ts`, `web/playwright.config.ts`; helpers: `web/tests/setup.ts`, `web/tests/acceptance/helpers.tsx`.

## Approach
- Public surfaces from the interface contract only. Shared helpers in `tests/acceptance/rf_helpers.py` (lazy imports, so each test fails on its own). `conftest.py` blocks all non-loopback sockets for the whole suite (AC-12).
- In-process tests build `AppContext.create(...)` with injected `available_gb`, `ollama_unload`, `doctor`, and a `CountingAdapter` wrapping `MockAdapter` to count `run` calls. Jobs run through `TestClient(create_app(ctx))` as a context manager, which starts the real worker with real mock child processes.
- AC-5 and the loopback listener test start `uv run reelforge up --allow-degraded --backend mock` as a real subprocess and `SIGKILL` its process group.
- Doctor tests replace `CHECKS` entries via `monkeypatch.setitem`; `serve` is replaced via `monkeypatch.setattr("reelforge.startup.serve", ...)`.
- Today `reelforge` is not importable, so nearly every test fails with `ModuleNotFoundError: reelforge` (or `psutil`/`pydantic`, which the project must add); the subprocess tests fail because `uv run reelforge` exits 2. `try-tests` reports PASS. Only AC-12 tests are green now (`expect_red: false`).

## Untestable criteria
- AC-17: Ruff, pyright, eslint, `tsc --noEmit` and the web build are the standards' lint, typecheck and build commands; the verifier runs them. (The test files themselves are ruff-clean and formatted with default settings.)

## Open questions
- Assumptions the tests pin where the contract is silent: `request_artifact` is synchronous; a persistently failing transient job ends with `attempts == 2` and exactly 2 adapter runs; `poll_once` returns nothing changed on a second identical poll; disk checks read free space through `shutil.disk_usage` or `psutil.disk_usage`; the mock `kill`/OOM job ends `failed` with error exactly `killed, likely out of memory`.
- AC-7: with `preflight_wait_s=0` the tests accept either `queued` or `failed` as long as the reason text is in `message` or `error`, the job never runs and no lease is held.
