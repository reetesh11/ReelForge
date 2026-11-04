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
- Run the real worker or adapter once on the reference Mac before shipping an adapter task (stub tests cannot see real-model defects), and say in the PR body what was and was not checked.
- Test helpers that fake low free memory apply the limit only to the job under test, not to setup steps that run other heavy jobs.
- In `tests.json`, write one entry per acceptance criterion id; never put several ids in one `criterion` string and never map a criterion only to the file it happens to appear in (the helper rejects the stage).
- Specs and `tech.md` must name only commands that exist: the CLI has `reelforge up` and `reelforge doctor`. Check `--help` before writing a flag onto a command.

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
- Acceptance tests are written before any implementation, so a test that raises whatever the code returns (for example `dict >= dict`) looks red for the right reason. The test-author must run each assertion expression against a hand-built sample value before freezing.
- Caption burn-in needs an ffmpeg with libass. On macOS plain Homebrew `ffmpeg` lacks the `subtitles` filter: use `brew install ffmpeg-full` and `brew link --force ffmpeg-full`.
- After a frozen test is revised through "Revisit a test", the red check fails because the code already exists, and Gate 2 opens with a failed-red warning. Approve when the diff is limited to the lines named in the note. The implement stage then needs at least one real commit after the re-freeze.
- `congoforce check` runs the whole suite and takes about 10 minutes; run it in the background.
- Stop any running ReelForge app (ports 7400 and 7401) before a task's test stages; the Playwright wrapper needs both ports, and a busy port shows up as a pre-existing baseline failure.
- A script that runs inside another uv environment must not sit next to a module named like a package it imports (for example `adapters/mlx_audio.py` and `import mlx_audio`): as a script, its folder is first on `sys.path` and shadows the package. Scrub `sys.path` before the real import.
- Select frozen tests with `pytest -k` instead of naming the frozen file; a hook blocks any shell command that names a frozen file, even to run it.
- The generated PR body marks manual criteria as met; edit it to say what was actually run on the reference Mac before shipping.
- `.congoforce/standards.md` and `config.toml` are tracked on `main`; do not leave them untracked, because switching branches would remove them and CongoForce would regenerate a default.

- When an owner answer changes what a criterion means, edit `req.md` and `product-spec.md` so the AC text matches before Gate 2; otherwise the Gate 2 packet and the PR body carry the stale wording.
- Push the `--base` branch to origin before the ship stage when it is not `main`; `gh pr create` fails otherwise and the task stays blocked until `congoforce answer`.
- The verifier does not run vitest. For UI criteria run `pnpm --dir web test --run` and state the result in the PR body.
- When a frozen test measures exact timing (for example a silence gap), check the default trim or padding in the audio path against its tolerance before implementing.

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
