# Standards — ReelForge

Every CongoForce agent follows this file. The human owns it: edit anything,
then approve with `congoforce standards approve`. Agents never edit it,
except a bootstrap task, which may fill in the test commands.

## Stack

- Backend: Python 3.12 managed by uv, FastAPI, Pydantic v2, SQLAlchemy 2 + Alembic, pytest. Code in `src/reelforge/`, tests in `tests/`.
- Frontend: TypeScript (strict), React 19, Vite, pnpm, vitest, Playwright. Code in `web/`.
- Acceptance tests live in `tests/acceptance/` (backend) and `web/tests/acceptance/` (UI, vitest) unless the repo already has a convention. Playwright flows live in `web/e2e/`.

## Conventions

- Match the style, naming and structure of the surrounding code.
- Reuse existing utilities before adding new ones.
- Keep each commit to one task from tech.md, with the build green after it.
- Model IDs appear only in `models.toml` and the adapter for that tool; never hard-code them elsewhere.
- Subprocesses and ffmpeg calls use argument lists, never `shell=True`.
- All services bind to `127.0.0.1`; no outbound network calls while rendering.
- Python: ruff for lint and format, pyright for types. TypeScript: eslint, `tsc --noEmit`, no `any`.
- Tests run on the `mock` backend; real-model checks are manual on the reference Mac.
- `web/tsconfig.json` excludes `tests/acceptance` from `tsc` (a frozen helper has a type error). Do not fix it by editing frozen tests; vitest and eslint still cover those files.
- Real-tool checks (`docs/manual-checks.md`) run on the reference Mac before a PR that touches an adapter is merged. Mock stubs must mirror real server limits, for example Draw Things rejects width or height below 128 with 422.
- Per-model settings such as `steps` live in `models.toml`, not in adapter constants.
- Keep to one commit per task in tech.md, even when the change is small.

## Docs agents should read

- `ReelForge — Requirements Document.md`, `ReelForge — Product Spec.md` and `ReelForge — Technical Spec.md` in the repo root. The Technical Spec wins on design; the Requirements Document wins on acceptance.
- The phase file the task came from, in `phases/`.

## Gotchas

- Run `congoforce map` before starting a task when the base branch has moved; the requirements agent trusts a stale repo map.
- `git push` over HTTPS needs `gh auth setup-git` once per machine, or the ship stage blocks.
- Keep `monaco-editor` at 0.52.2 while `monaco-yaml` is 5.5.1; newer Monaco changes its export map and breaks the build.
- Frozen M1 tests pin API shapes: `GET /jobs` items keep exactly the M1 `JobOut` keys unless a job has a `result`. Omit new fields on existing responses when empty, or revise the frozen test at a Gate 2.
- Pass `--base origin/main` to `congoforce new`; a task can otherwise inherit a stale base. Check that the new worktree contains `origin/main` before the spec stage.
- Never hand-edit a frozen test to get around a failure; the frozen-hash and red checks then fail. Revise it through Gate 2, or the escalation "Revisit a test" route before implementing.
- Stop any running ReelForge app (ports 7400 and 7401) before a task's test stages; the Playwright wrapper needs both ports, and a busy port shows up as a pre-existing baseline failure.

## Draft notes

- Commands are written to be safe before the project exists: Python and frontend steps are skipped until `pyproject.toml` and `web/package.json` exist.
- The `test` command runs pytest, then vitest. Only pytest writes JUnit XML; `test_files` is pytest only, so frozen acceptance tests that must be tracked in `tests.json` should be pytest tests.
- Tests run with PYTHONPATH set so the worktree's own code is imported (PYTHONPATH=.).
- pytest writes JUnit XML with junit_family=xunit1 so each test carries its file path.

## Commands (machine-readable)

Each command runs from the task worktree root under `command_timeout`.
`{junit}` is replaced with the JUnit XML path the helper reads; `{files}`
with the test files to run. Leave a command empty to skip it.

```toml
[preset]
name = "python"

[commands]
install = "{ [ ! -f pyproject.toml ] || { uv sync; }; } && { [ ! -f web/package.json ] || { pnpm --dir web install --frozen-lockfile; }; }"
lint = "{ [ ! -f pyproject.toml ] || { uv run ruff check . && uv run ruff format --check .; }; } && { [ ! -f web/package.json ] || { pnpm --dir web lint; }; }"
typecheck = "{ [ ! -f pyproject.toml ] || { uv run pyright; }; } && { [ ! -f web/package.json ] || { pnpm --dir web exec tsc --noEmit; }; }"
build = "{ [ ! -f web/package.json ] || { pnpm --dir web build; }; }"
test = "PYTHONPATH=. uv run --with pytest python -m pytest -q -o junit_family=xunit1 --continue-on-collection-errors --junitxml={junit} && { [ ! -f web/package.json ] || { pnpm --dir web test --run; }; }"
test_files = "PYTHONPATH=. uv run --with pytest python -m pytest -q -o junit_family=xunit1 --continue-on-collection-errors --junitxml={junit} {files}"
e2e = "{ [ ! -f web/package.json ] || { pnpm --dir web exec playwright test; }; }"

[paths]
package_dir = "."

[freeze]
# Frozen at Gate 2 with the acceptance tests: test config the implementer must not touch.
globs = ["**/conftest.py", "pytest.ini", "tox.ini", "setup.cfg", "**/vitest.config.*", "**/playwright.config.*"]
keys = []
```
