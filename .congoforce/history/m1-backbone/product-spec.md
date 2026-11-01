# Product spec — Build the ReelForge M1 backbone

The worktree has no existing user-facing surface (no code, screens, routes or CLI). The only references are the repo's Product Spec ("Settings & system status", "States, errors and notifications") and Technical Spec ("Startup, doctor and configuration"). The user is a single local operator on a Mac; everything runs on the `mock` backend, offline, bound to 127.0.0.1. Per `answers.md`, M1 ships as one task.

## User-facing behaviour

### CLI: `reelforge`
- `reelforge doctor`: prints one row per check: name, PASS / FAIL, severity (`blocking` or `warning`), detail, and a one-line fix hint for every failure. Rows, in order: arm64 shell, binaries native, ffmpeg filters, ltx, mlx-audio, Draw Things, Ollama, ports, disk, memory, licenses. Exit code 0 if no blocking check fails (warnings allowed); exit code 1 if any blocking check fails. Last line: `N passed, W warnings, B blocking failures`.
- `reelforge up`: steps print in order: `doctor` -> `migrate` -> `recover jobs` -> `start API + worker`. If a blocking check fails it prints the table, then `Refusing to start: B blocking check(s) failed. Fix them or pass --allow-degraded.` and exits 1. With `--allow-degraded` it prints `Starting in degraded mode` plus the failing checks and continues. Then it logs the API URL `http://127.0.0.1:7400`.
- Flags override everything else (e.g. `--api-port`, `--data-root`, `--allow-degraded`). Invalid values fail with a Pydantic-derived message naming the key and exit code 2.
- Logs are structlog JSON, one object per line, with at least `ts`, `level`, `event`. Adapter commands appear verbatim as a JSON array of arguments.
- `reelforge --help` lists `doctor` and `up`.

### Config
- Precedence: CLI flag > `REELFORGE_*` env var > `config.toml` > default. Defaults include host `127.0.0.1`, `api_port` 7400, `ui_port` 7401, `data_root` `~/ReelForge`.
- `models.toml` holds, per model key: id, revision, license fields. Its entries are the only place a model ID appears in code or config. A missing license field shows as a `licenses` warning in doctor, not an error.

### Jobs (observable behaviour)
- States: `queued`, `running`, `succeeded`, `failed`, `cancelled`. Progress is 0-100.
- Transient failure: one automatic retry, then `failed` with a reason.
- Cancel: a running job stops and ends `cancelled`.
- Restart after a crash: a job that was `running` shows `queued` again and resumes; finished artifacts are kept.
- Memory pre-flight failure shows the reason: `Only {free} GB free, job needs {need} GB.` and the job does not start. Exact fail-vs-wait policy is an open question.
- Child exit -9 or 137: failure reason `killed, likely out of memory`.

### HTTP API (127.0.0.1:7400)
- `GET /health`: JSON with an overall status and the same per-check entries as doctor (name, status pass/fail, severity, detail, fix hint).
- Projects: create, read, list, update, delete. Unknown id returns 404 `{"detail": "project not found"}`. Invalid body returns 422.
- Jobs: list (filterable by status), `POST .../cancel`, `POST .../retry`. Cancelling a finished job or retrying a non-failed job returns 409 with a plain message.
- `GET /media/{artifact_id}`: serves the artifact file with the right content type. With `Range: bytes=a-b` it returns 206 with `Content-Range: bytes a-b/total` and `Accept-Ranges: bytes`. Unknown artifact returns 404; any path resolving outside the data root returns 403 (nothing is served).
- WebSocket `/ws/events`: pushes JSON events `job.updated`, `artifact.created`, `stage.changed`, `health.changed`. Payload shapes follow the Technical Spec.

### Web shell (`web/`)
- Dark-first theme; light follows only if the OS asks.
- Left sidebar: Projects, Settings & status. Cast library and Brand kit are not shown (out of scope).
- Project list: a grid or list of projects with title, stage progress, last edited. Empty state: `No projects yet.` with a `New project` button. Loading: skeleton rows. Error: `Couldn't load projects.` with `Retry`.
- Project route: header with title, and a stage stepper of the six stages in order (Story, Cast, Voices, Key frames, Shots, Assembly). Each shows a state badge from the product-spec state set (Not started, Queued, Rendering with %, Needs review, Approved, Stale, Failed). Stages after the first unapproved one appear locked. In M1 stage bodies are placeholders: `This stage arrives in a later milestone.`
- Settings & status: a row per dependency (Draw Things, ltx-2-mlx, mlx-audio, local LLM, ffmpeg) with a green / amber / red dot, version, port and a "Fix" hint when not green. It updates live on `health.changed`. Editable settings are out of scope.
- Live updates: job progress and state changes appear without a page reload or polling, driven by `/ws/events` invalidating the relevant queries. If the socket drops, a banner shows `Reconnecting...` and it retries with backoff.
- Dev: Vite proxies `/api`-style requests and `/ws` to 127.0.0.1:7400.

## Acceptance criteria
- AC-1: Four tests, one per level. A key set only in defaults yields the default; set also in `config.toml` yields the toml value; also in `REELFORGE_<KEY>` yields the env value; also as a CLI flag yields the flag value.
- AC-2: A test greps `src/` (excluding `models.toml` and the single adapter module per tool) for every model id listed in `models.toml` and finds none. A second test changes one entry in `models.toml` only (temp copy) and shows the resolved model, and what the mock adapter receives, changes.
- AC-3: For every artifact written, the DB row and sidecar `.json` both contain non-empty `prompt`, `seed`, `model` and `version`, and the values are equal (the test compares field by field).
- AC-4: Re-requesting with the same `inputs_fp` and an existing file returns the existing artifact, enqueues zero new jobs, and reports a cache hit. A request with a new seed, or a missing/hash-mismatched file, creates a new job and never reports a hit.
- AC-5: After killing the process while a job is `running`, restart leaves that job `queued`, its `pid` cleared, the GPU lease row deleted/empty, and previously succeeded artifacts untouched (same sha256, no new jobs for them).
- AC-6: Cancelling a running job ends in `cancelled` and the child process is gone. A job whose first run raises a transient failure runs a second time automatically, and if that also fails ends `failed` with attempt count 2. No third attempt.
- AC-7: When available memory is below the job's declared need, the job stays out of `running`, the lease is not taken, and the job's reason text states free and needed GB. Concurrency test: two heavy jobs submitted together never both hold the lease; the second starts only after the first releases it. Ollama unload is called before the pre-flight.
- AC-8: A child exiting with -9 yields failure classification `killed, likely out of memory`, and 137 yields the same string; other non-zero codes do not.
- AC-9: `doctor` prints pass/fail for each R9 dependency (11 rows), and `GET /health` returns the same names and pass/fail statuses. With a blocking failure `doctor` exits non-zero and `up` exits non-zero without starting servers; `up --allow-degraded` starts.
- AC-10: `GET /media/...` that resolves outside the data root (including `..` and symlink escapes) returns 403 and serves no bytes. API and UI servers bind to 127.0.0.1 only (a config of `0.0.0.0` is rejected by validation). A grep test finds no `shell=True` in `src/`, `tests/` helpers and scripts.
- AC-11: With the mock backend, a Playwright test enqueues a job and sees its progress advance in the UI without any polling request to the jobs endpoint, and the project list and stage stepper render.
- AC-12: The full Python and web suite passes with outbound network blocked (socket guard that fails on any non-loopback connection).
- AC-13: `alembic upgrade head` on an empty DB creates projects, story_versions, characters, voices, project_characters, scenes, lines, artifacts, artifact_inputs, jobs, approvals, reel_versions, brand_kits, settings; `PRAGMA journal_mode` returns `wal`; primary keys are 26-char ULIDs; stored file paths contain no leading `/` or data root prefix.
- AC-14: `GET /media/{artifact_id}` with `Range: bytes=0-99` returns 206, 100 bytes, `Content-Range: bytes 0-99/<size>`. An unsatisfiable range returns 416 with `Content-Range: bytes */<size>`. Without Range returns 200.
- AC-15: Through the API against the mock backend: create returns 201 with the project; read returns it; update changes it; delete returns 204 and later read is 404. Jobs list returns jobs; cancel on a running job yields `cancelled`; retry on a failed job creates/re-queues a job that runs to `succeeded`.
- AC-16: For each adapter run, the log contains the command as a JSON array of strings, identical to what was executed. A command exceeding its timeout is killed and the job fails with reason `timed out after {n}s`.
- AC-17: `ruff check`, `ruff format --check`, `pyright`, web `lint` (eslint), `tsc --noEmit` and `pnpm build` all exit 0.

## Edge cases and errors
- Port 7400 in use: `doctor` ports check fails, detail `Port 7400 is used by another process.`, hint names the holder and next free port.
- Disk: pass at >= 30 GB free, warning below 30 GB, blocking below 5 GB. Memory: warning below 24 GB total; available is shown.
- Doctor checks for ltx, mlx-audio, Draw Things, Ollama are stubs in M1: they report real reachability/presence but never run a real model. On the mock backend a missing real tool still fails as written; the user uses `--allow-degraded`. (See open question.)
- Duplicate project title: allowed (ids differ).
- Corrupt or missing sidecar/file for a cached artifact: treated as a cache miss.
- Concurrent cancel and completion: final state is whichever occurred first; never both.
- Media for an artifact whose file was removed: 404 `file missing`.
- WebSocket client disconnect: no effect on jobs.
- Config file malformed: `config.toml: <line> <message>`, exit 2.

## Out of scope
- Story, cast, voice, frame, shot and assembly features.
- Real Draw Things, Ollama, ltx and mlx-audio adapters (mock and health stubs only).
- Brand kit and library screens; editable settings, ports and storage UI; `setup` and `models pull` commands; `doctor --deep`.
- macOS notifications and activity panel.

## Open questions
- On a Mac without ltx/mlx-audio/Draw Things installed, the spec makes them blocking in `doctor`, so `up` refuses to start. Should the mock backend downgrade these to warnings, or must the user always pass `--allow-degraded`?
- Memory pre-flight: does the job fail immediately or wait (and for how long) when memory is insufficient? The spec above only requires a clear reason and no start.
- Should `up` also serve the built UI on 7401 / open the browser in M1, or only the API and worker (the UI via the Vite dev server)?
- Stage stepper in M1 has no approvals flow; is locking later stages visual-only, driven by seed data in the `approvals` table?
