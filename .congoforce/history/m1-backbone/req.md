---
class: feature
size: large
title: Build the ReelForge M1 backbone (config, data, jobs, API, doctor, UI shell)
---
# Requirements — Build the ReelForge M1 backbone

## Problem
ReelForge has specs but no code. Later milestones (M2 story, M3 cast) need a working foundation: a Python service with config, a SQLite data model, an artifact store, a persistent job queue with a GPU lease, a mock adapter, an HTTP/WebSocket API, a `doctor` health check, and a React UI shell. Everything runs on the `mock` backend, offline, on 127.0.0.1.

## Requirements
- R1. The repo shall provide a Python 3.12 / uv project (`pyproject.toml`, `src/reelforge/`) with a Typer CLI `reelforge` (`doctor`, `up`) and structlog JSON logging.
- R2. When a setting is defined at several levels, the system shall resolve it as CLI flags > `REELFORGE_*` env vars > `config.toml` > defaults, validated by Pydantic; `models.toml` shall hold model keys, revisions and license fields.
- R3. The system shall store data in SQLite (WAL) via SQLAlchemy 2 + Alembic, covering projects, story_versions, characters, voices, project_characters, scenes, lines, artifacts, artifact_inputs, jobs, approvals, reel_versions, brand_kits and settings, using ULIDs and data-root-relative paths.
- R4. When an artifact is written, the system shall write atomically via `cache/tmp` then rename, add a sidecar `.json` (prompt, seed, model, params, `inputs_fp`, job id), record sha256, keep one active artifact per owner and kind, and reuse the cache when `inputs_fp` and the file match.
- R5. The system shall run jobs from a persistent SQLite queue with an in-process async worker (queued, running, succeeded, failed, cancelled), one automatic retry for transient failures, cancel, and orphan recovery on startup (dead `pid` returns to `queued`, GPU lease cleared).
- R6. While a heavy job runs, the system shall hold a single GPU lease (holder row in the DB), run a memory pre-flight (`psutil` available memory vs. declared need), unload Ollama first, and sample child-process memory.
- R7. The system shall define an adapter protocol (`health`, `capabilities`, `run`) and a `mock` backend producing placeholder images, sine WAVs and test-pattern MP4s; commands are argument lists, logged verbatim, with a timeout.
- R8. The system shall serve a FastAPI app on 127.0.0.1:7400 with `GET /health`, project CRUD, jobs list/cancel/retry, `GET /media/{artifact_id}` with range support scoped to the data root, and WebSocket `/ws/events` (`job.updated`, `artifact.created`, `stage.changed`, `health.changed`).
- R9. When `reelforge doctor` runs, the system shall report pass/fail per dependency (arm64, native binaries, ffmpeg filters, ltx, mlx-audio, Draw Things, Ollama, ports, disk, memory, licenses) with blocking vs. warning severity; `reelforge up` shall run doctor, migrate, recover jobs, then start API and worker.
- R10. The repo shall provide a `web/` shell (React 19, Vite, TypeScript strict) with a generated typed API client, a WebSocket hook invalidating TanStack Query keys, project list, project route with stage stepper, Settings & status panel, dark-first theme, and Vite dev proxy.
- R11. If a child process exits with -9 or 137, then the system shall classify the failure as "killed, likely out of memory".

## Acceptance criteria
- AC-1: Config precedence: for a key set at defaults, `config.toml`, env `REELFORGE_*` and CLI flag, each level is overridden by the next higher one (one test per level).
- AC-2: A grep test finds no model ID string in code outside `models.toml` and one adapter per tool; changing a model entry in `models.toml` alone changes what is used.
- AC-3: Every artifact has prompt, seed, model and version in both its DB row and its sidecar `.json`, with matching values.
- AC-4: A request whose `inputs_fp` is unchanged and whose file exists is served from cache with no new job enqueued; a "new take" (new seed) never hits the cache.
- AC-5: If the process is killed while a job is `running`, after restart the job is `queued`, the GPU lease row is cleared, and already-completed artifacts are not regenerated.
- AC-6: Cancelling a running job stops it and marks it `cancelled`; a transient failure is retried once automatically, then the job is `failed`.
- AC-7: With insufficient free memory the pre-flight fails or waits with a clear reason and the job does not start; two heavy jobs never hold the lease simultaneously.
- AC-8: Exit code -9 and 137 each yield the classification "killed, likely out of memory".
- AC-9: `doctor` prints pass/fail per dependency listed in R9 and `GET /health` on 7400 returns the same statuses; a failing blocking check makes `doctor` exit non-zero and `up` refuse to start unless `--allow-degraded`.
- AC-10: `GET /media/...` for a path outside the data root is rejected; all servers bind to 127.0.0.1; a grep test finds no `shell=True`.
- AC-11: With the mock backend, a job's progress reaches the UI over `/ws/events` without polling, and the project list and stage stepper render (Playwright).
- AC-12: The full suite passes with outbound network blocked.
- AC-13: Alembic upgrade on an empty DB creates all R3 tables with WAL enabled; IDs are ULIDs and stored file paths are relative to the data root.
- AC-14: `GET /media/{artifact_id}` honours a `Range` header (206 with correct `Content-Range`).
- AC-15: Project create/read/update/delete, and jobs list/cancel/retry, work through the API against the mock backend.
- AC-16: Each adapter-run command is logged verbatim as an argument list and is aborted when its timeout elapses.
- AC-17: Ruff, pyright, eslint, `tsc --noEmit` and the web build pass.

## Out of scope
- Story, cast, voice, frame, shot and assembly features.
- Real Draw Things, Ollama, ltx and mlx-audio adapters (mock adapter and health stubs only).
- Brand kit screens and library screens.

## Assumptions
- No existing code; the project and `web/` are created from scratch, following the standards' layout (`tests/acceptance/`, `web/tests/acceptance/`, `web/e2e/`).
- The Technical Spec is authoritative for table columns, endpoint shapes and event payloads; the specs were not re-read in detail here.
- AC-13 to AC-17 are added to make R3, R8, R7 and the standards checkable; they restate the requirements.
- pnpm is the web package manager (per standards).

## Suggested split
Too big for one implement/verify loop. Ship in order; each leaves the build green:
1. M1a Foundation: R1, R2, R3 (project scaffold, CLI shell, logging, config/`models.toml`, DB schema + migrations). AC-1, AC-2, AC-13, part of AC-10 and AC-17.
2. M1b Artifacts and mock adapter: R4, R7, R11. AC-3, AC-4, AC-8, AC-16.
3. M1c Jobs and GPU lease: R5, R6. AC-5, AC-6, AC-7.
4. M1d API and doctor: R8, R9. AC-9, AC-10, AC-14, AC-15.
5. M1e Web shell: R10. AC-11, plus AC-12 and AC-17 for the full run.

## Open questions
- Confirm the split above, or approve as one large task anyway?
