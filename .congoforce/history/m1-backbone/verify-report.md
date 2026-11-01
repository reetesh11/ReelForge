# Verify report: m1-backbone

**Result: PASS**

## Pass 1: spec compliance
All executable checks passed (checks.md: lint, typecheck, build, 150 tests, frozen set intact). I judged each criterion from the code and tests.

| AC | Verdict | Evidence |
| --- | --- | --- |
| AC-1 config precedence | met | config.py, test_ac01 |
| AC-2 model registry | met | models.toml and models_registry.py. Model ids appear only in toml and adapter modules. |
| AC-3 artifact metadata | met | artifacts/store.py and service.py write the DB row and sidecar together. |
| AC-4 cache | met | fingerprint.py, store.py. Cache hits enqueue no job. |
| AC-5 recovery | met | queue.recover_orphans clears pid and lease. |
| AC-6 cancel and retry | met | worker.py: MAX_ATTEMPTS=2, cancel token. |
| AC-7 preflight and lease | met | preflight.py, worker._run_heavy: Ollama unload, wait, fail with the GB reason. Lease lock held across the job. |
| AC-8 OOM | met | classify.py |
| AC-9 doctor, /health, up | met | doctor.py and startup.run_up print the specified messages. |
| AC-10 security | met | routes_media.py resolves symlinks and `..` and returns 403 when outside the root. |
| AC-11 web | met | Components and routes match the spec. Playwright and vitest are run through test_ac11. |
| AC-12 network guard | met | conftest |
| AC-13 database | met | 0001_initial migration, WAL |
| AC-14 range | met | parse_range returns 206, 416 and 200 as specified. |
| AC-15 API | met | routes_projects, routes_jobs, ws |
| AC-16 runner | met | runner.py |
| AC-17 lint, typecheck, build | met | checks.md |

Unrequested additions: the uv parent watchdog in startup.py. The human accepted it.

## Pass 2: quality
No blocking or major findings. The code matches the tech.md architecture: config, db, artifacts, jobs (queue, worker, lease, preflight), adapters, events, health, api and web. No component or data flow was dropped or rewired.

Notes (not blocking):
- startup.py:44: the watchdog is extra and polls every 10 ms.
- routes_media.py: sync IO in an async handler. This is acceptable for a local single-user app.
- lease.py:21 and worker.py:62: the asyncio.Lock is created twice.
- web/tsconfig.json: frozen web acceptance tests are excluded from tsc. The human accepted this.

## Open items
None.
