# ReelForge Phase 1 — Foundation, story and cast

Binding inputs: `ReelForge — Requirements Document.md`, `ReelForge — Product Spec.md` (Stages 1–2, story.yaml format, States), `ReelForge — Technical Spec.md` (milestones M1, M2, M3). Where they differ, the Technical Spec wins on design and the Requirements Document wins on acceptance.

Scope is Tech Spec milestones **M1 Backbone**, **M2 Story** and **M3 Cast**. Everything runs on the `mock` backend in CI; real Draw Things and Ollama calls are checked manually on the reference Mac.

## Prerequisites (human)
- Spike S1 (Draw Things API: routes, Kontext edit with reference image, model selection, speed) is done and its finding is added to the Technical Spec. If S1 fails, mflux becomes the primary image adapter.
- `.congoforce/standards.md` has commands for the Python backend (uv, ruff, mypy or pyright, pytest) and the React/Vite/TypeScript UI (pnpm install, tsc, lint, vitest).

## Requirements
- R1 (M1). Python 3.12 / uv project with the `reelforge` Typer CLI; config precedence CLI flags > env vars > `config.toml` > defaults, validated with Pydantic; `models.toml` model registry as the only place model IDs appear.
- R2 (M1). SQLite (WAL) via SQLAlchemy 2 + Alembic with the Technical Spec tables; ULIDs; artifact rows with `inputs_fp`, sha256, seed, model and params; sidecar `.json` per generated file; atomic writes via `cache/tmp` then rename.
- R3 (M1). Persistent job queue with retry (one automatic), cancel, resume; one GPU lease with a DB holder row, crash recovery on startup, memory pre-flight and the "free memory" order (Ollama unload first).
- R4 (M1). Adapter protocol (`health`, `capabilities`, `run`) with a `mock` backend producing placeholder images, sine WAVs and test-pattern MP4s.
- R5 (M1). `reelforge doctor` with a pass/fail per dependency and `GET /health` on port 7400 returning all dependency statuses; WebSocket `/ws/events`; all servers bind `127.0.0.1`.
- R6 (M1). React UI shell: project list, project route with stage stepper, Settings and status panel, generated typed API client.
- R7 (M2). Story input screen and `structure_story` via Ollama with JSON-schema output, one repair round, gap questions, 4–8 scenes sized to target length; `story.yaml` validated with unknown fields rejected; form view and Monaco YAML view in sync; import/export; story versions and Approve story gate.
- R8 (M3). Draw Things adapter (4 candidates with seeds s..s+3, health, model check) and mflux fallback adapter; Cast screen with candidate grid, approve / regenerate / edit look text / upload own image; look-text normalisation; cast library with reuse across projects and project-level variants that never edit the library character.

## Acceptance criteria
- AC-1: Given a storyline with 2 characters and 5 scenes on the mock LLM, the system produces a `story.yaml` that passes schema validation, can be edited in form and YAML views, and re-saved as a new version.
- AC-2: A `story.yaml` with an unknown field or invalid value is rejected with a message naming the field; nothing is silently dropped.
- AC-3: Given an approved cast saved to the library, a second project reuses those characters with identical master image, look text, seed and voice reference.
- AC-4: Editing a character's outfit in a project creates a linked variant and leaves the library character unchanged.
- AC-5: Every artifact records prompt, seed, model and version; swapping a model needs a change only in `models.toml` and one adapter (no model ID elsewhere in code).
- AC-6: `doctor` reports pass/fail for each dependency (arm64, ffmpeg features, ltx, mlx-audio, Draw Things, Ollama, ports, disk, memory, licenses), and `GET /health` returns the same statuses.
- AC-7: If the process is killed while a job is running, on restart the job returns to `queued`, the GPU lease is cleared, and completed artifacts are not regenerated (cache hit on `inputs_fp`).
- AC-8: Cancel stops a running job and marks it `cancelled`; a transient failure retries once automatically.
- AC-9: A pre-flight with insufficient free memory fails or waits with a clear reason instead of starting the job.
- AC-10: Steps for AC-1..AC-4 complete with no outbound network connection.
- AC-11: UI shell lists projects, shows the stage stepper, and updates job state live over the WebSocket without polling (Playwright against the mock backend).

## Out of scope
- Voice, key frames, shots, assembly and export (Phases 2 and 3).
- 3-view character sheets, ensembles, voice design, templates beyond the four listed (v1.1).
- Real-model quality checks (human visual check on the Mac).

## Open questions
- Which Ollama model is the default (`qwen3:8b` in the Technical Spec)?
