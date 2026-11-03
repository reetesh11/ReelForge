# ReelForge Phase 1 / M3c — Configurable image job memory requirement

Binding inputs: `ReelForge — Technical Spec.md` (job queue, GPU lease and pre-flight), `phases/phase-1/m1-backbone.md` (AC-7 pre-flight), `phases/phase-1/m3-cast.md` (R1, R4). Follow-up to M3 found in real use on the reference Mac (24 GB): clicking "Generate candidates" failed with "Only 7.9 GB free, job needs 10.0 GB." although earlier live runs with similar free memory succeeded. Requires `m3b-kontext-fixes` merged.

## Background
- `src/reelforge/api/routes_cast.py` hard-codes `GENERATE_MEM_GB = 10.0` and passes it as `mem_need_gb` for every `cast.generate` job (generate, regenerate, refine).
- `jobs/preflight.py` unloads Ollama, then waits up to `preflight_wait_s` (120 s) for that much memory to be available, and fails the job with "Only X GB free, job needs Y GB." otherwise.
- The image model runs inside the Draw Things app, which already holds the loaded model in its own process, so the extra memory ReelForge's own job needs is far lower than a cold model load. The number is a guess today and cannot be changed without editing code. The same pre-flight will govern heavier ltx and mlx-audio jobs in Phase 2, so the requirement must come from configuration, not constants.

## Requirements
- R1. New setting `image_mem_gb` (float, greater than 0, default 6.0) in `Settings`, resolved with the usual precedence (defaults, `config.toml`, env `REELFORGE_IMAGE_MEM_GB`, CLI flag `--image-mem-gb` on `up` and `doctor`). `config.toml` key: `[limits] image_mem_gb`.
- R2. Every `cast.generate` job (generate, regenerate, refine) uses `settings.image_mem_gb` as its `mem_need_gb`. The constant `GENERATE_MEM_GB` is removed.
- R3. The pre-flight failure message names the setting so the user can act on it: "Only 7.9 GB free, job needs 6.0 GB. Close other apps, or lower image_mem_gb in config.toml." (still shown in the Cast screen error panel with Retry). The existing messages for other job kinds keep their wording unless they also come from a configurable value.
- R4. An invalid value (zero, negative, non-number) fails settings validation with a clear error, like other settings.
- R5. `docs/manual-checks.md` M3 notes the setting and the symptom ("Only X GB free, job needs Y GB") with how to fix it.

## Acceptance criteria
- AC-1: Settings default `image_mem_gb` to 6.0; `config.toml`, `REELFORGE_IMAGE_MEM_GB` and `--image-mem-gb` each override it, in that increasing order of precedence (one check per level).
- AC-2: Values 0, -1 and "abc" are rejected by settings validation.
- AC-3: With the mock backend, a `cast.generate` job created via the API (generate, regenerate and refine) has `mem_need_gb` equal to the configured `image_mem_gb`; with a custom value of 3.5 the job reports 3.5.
- AC-4: With `available_gb` faked below the configured value, the job fails with a message that contains "image_mem_gb" and the free and needed numbers; with `available_gb` above it, the job runs and succeeds (no real memory use).
- AC-5: No other source file contains a hard-coded memory figure for cast jobs (the `GENERATE_MEM_GB` constant is gone).
- AC-6: Ruff, pyright, eslint, `tsc --noEmit`, the web build, the full test suite and the Playwright flow pass.
- AC-7: Manual check on the reference Mac: with Draw Things running and Kontext loaded and about 8 GB available, "Generate candidates" starts and renders 4 images; and with `REELFORGE_IMAGE_MEM_GB=20`, it fails with the new message that names `image_mem_gb`.
