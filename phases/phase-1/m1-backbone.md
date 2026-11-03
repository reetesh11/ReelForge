# ReelForge Phase 1 / M1 — Backbone

Binding inputs: `ReelForge — Requirements Document.md`, `ReelForge — Product Spec.md` (States, errors and notifications; Settings & system status), `ReelForge — Technical Spec.md` (Key decisions, Architecture, Process and memory model, Data model, File system layout, Pipeline engine, Adapters, Startup/doctor/configuration, Testing and security). The Technical Spec wins on design; the Requirements Document wins on acceptance. Parent: `phases/phase-1-foundation-story-cast.md`. Next: `m2-story.md`, `m3-cast.md` (both need this merged).

Everything runs on the `mock` backend; no real model is called. This task creates the Python project and the `web/` project from scratch.

## Requirements
- R1. Python 3.12 / uv project (`pyproject.toml`, `src/reelforge/`) with a `reelforge` Typer CLI (`doctor`, `up`) and structlog JSON logging.
- R2. Configuration with precedence CLI flags > env vars (`REELFORGE_*`) > `config.toml` > defaults, validated with Pydantic; `models.toml` registry with keys, revisions and license fields as the only place model IDs appear.
- R3. SQLite (WAL) with SQLAlchemy 2 + Alembic migrations for the Technical Spec data model (projects, story_versions, characters, voices, project_characters, scenes, lines, artifacts, artifact_inputs, jobs, approvals, reel_versions, brand_kits, settings); ULIDs; relative paths under the data root.
- R4. Artifact store: atomic write via `cache/tmp` then rename, sidecar `.json` (prompt, seed, model, params, `inputs_fp`, job id), sha256, `inputs_fp` fingerprint, one active artifact per owner and kind, cache reuse when `inputs_fp` and the file match.
- R5. Persistent job queue in SQLite with an in-process async worker: queued → running → succeeded / failed / cancelled, one automatic retry for transient failures, cancel, orphan recovery on startup (dead `pid` → `queued`, GPU lease cleared).
- R6. GPU lease (one heavy job at a time, holder row in the DB) with a memory pre-flight (`psutil` available memory vs. the job's declared need), Ollama unload first, and child-process memory sampling.
- R7. Adapter protocol (`health`, `capabilities`, `run`) and a `mock` backend emitting placeholder images, sine WAVs and test-pattern MP4s; commands built as argument lists, logged verbatim, with a timeout.
- R8. FastAPI app on 127.0.0.1:7400 with `GET /health` (every dependency status), project CRUD, jobs list / cancel / retry, `GET /media/{artifact_id}` with range support scoped to the data root, and WebSocket `/ws/events` (`job.updated`, `artifact.created`, `stage.changed`, `health.changed`).
- R9. `reelforge doctor` with pass/fail per dependency (arm64, binaries native, ffmpeg filters, ltx, mlx-audio, Draw Things, Ollama, ports, disk, memory, licenses) and blocking vs. warning severity; `reelforge up` runs doctor, migrates, recovers jobs, starts API + worker.
- R10. React 19 / Vite / TypeScript-strict UI shell in `web/`: generated typed API client, WebSocket hook invalidating TanStack Query keys, project list, project route with stage stepper, Settings & status panel, dark-first theme, Vite dev proxy.

## Acceptance criteria
- AC-1: Config precedence holds: a value set at each of the four levels is overridden by the next higher level (test per level).
- AC-2: No model ID string appears in code outside `models.toml` and one adapter per tool (grep test); swapping a model needs changes only there.
- AC-3: Every artifact has prompt, seed, model and version in both its DB row and its sidecar `.json`.
- AC-4: A job with an unchanged `inputs_fp` and present file is served from the cache without enqueuing a new job; a "new take" (new seed) never hits the cache.
- AC-5: If the process is killed while a job is `running`, on restart the job returns to `queued`, the GPU lease row is cleared, and completed artifacts are not regenerated.
- AC-6: Cancel stops a running job and marks it `cancelled`; a transient failure retries once automatically, then fails.
- AC-7: A pre-flight with insufficient free memory fails or waits with a clear reason and does not start the job; only one heavy job holds the lease at a time.
- AC-8: Exit code −9 / 137 is classified "killed, likely out of memory".
- AC-9: `doctor` reports pass/fail for each dependency and `GET /health` on port 7400 returns the same statuses; a failing blocking check makes `doctor` exit non-zero and `up` refuse to start unless `--allow-degraded`.
- AC-10: Media requests for paths outside the data root are rejected; all servers bind to `127.0.0.1`; no `shell=True` anywhere (grep test).
- AC-11: With the mock backend, a job's progress reaches the UI over the WebSocket without polling, and the project list and stage stepper render (Playwright).
- AC-12: Everything above runs with no outbound network connection.

## Out of scope
- Story, cast, voice, frame, shot and assembly features; real Draw Things, Ollama, ltx and mlx-audio adapters (only the mock adapter and health stubs).
- Brand kit screens, library screens.

## Open questions
- None.
