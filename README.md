# ReelForge

Local-first reel production. This repository holds the M1 backbone: configuration, database,
job queue, mock backend, HTTP API, `doctor`, and a React shell.

## Backend

```sh
uv sync
uv run reelforge doctor                      # environment checks
uv run reelforge up --allow-degraded         # doctor, migrate, recover jobs, serve API + worker
```

`up` refuses to start when a blocking check fails; `--allow-degraded` starts anyway (needed on a
machine without ltx-2-mlx, mlx-audio and Draw Things). The API listens on `127.0.0.1:7400`.
Settings resolve as CLI flag > `REELFORGE_*` environment variable > `<data root>/config.toml` >
defaults. Model IDs live only in `src/reelforge/models.toml`.

## Web

```sh
pnpm --dir web install
pnpm --dir web dev                           # http://127.0.0.1:7401, proxies /api, /health, /media, /ws
pnpm --dir web test --run                    # vitest
pnpm --dir web exec playwright install chromium
pnpm --dir web exec playwright test          # starts the backend and the dev server itself
```

After changing an API route, regenerate the typed client:

```sh
uv run python -m reelforge.api.openapi_export web/openapi.json
pnpm --dir web gen:api
```

## Checks

```sh
uv run ruff check . && uv run ruff format --check . && uv run pyright && uv run pytest
pnpm --dir web lint && pnpm --dir web exec tsc --noEmit && pnpm --dir web build
```
