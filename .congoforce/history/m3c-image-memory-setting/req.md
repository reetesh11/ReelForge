---
class: feature
size: small
title: Make the image job memory requirement configurable (image_mem_gb)
---
# Requirements — Make the image job memory requirement configurable (image_mem_gb)

## Problem
Clicking "Generate candidates" on the reference Mac (24 GB) fails with "Only 7.9 GB free, job needs 10.0 GB." because `GENERATE_MEM_GB = 10.0` is hard-coded in `api/routes_cast.py`. The image model already lives in the Draw Things process, so ReelForge's job needs far less, and the user cannot change the figure without editing code. Heavier Phase 2 jobs will use the same pre-flight, so the figure must come from configuration.

## Requirements
- R1. The system shall provide a `Settings.image_mem_gb` float, greater than 0, default 6.0, resolved as defaults, then `config.toml` `[limits] image_mem_gb`, then env `REELFORGE_IMAGE_MEM_GB`, then CLI flag `--image-mem-gb` on `up` and `doctor`.
- R2. When a `cast.generate` job is created (generate, regenerate or refine), the system shall set its `mem_need_gb` to `settings.image_mem_gb`, and the `GENERATE_MEM_GB` constant shall be removed.
- R3. If pre-flight fails for a `cast.generate` job, then the system shall fail it with "Only {free:.1f} GB free, job needs {need:.1f} GB. Close other apps, or lower image_mem_gb in config.toml." (shown in the Cast error panel with Retry). Messages for other job kinds keep their wording.
- R4. If `image_mem_gb` is 0, negative or not a number, then settings validation shall fail with a clear error naming the setting.
- R5. `docs/manual-checks.md` M3 shall describe the setting, the symptom "Only X GB free, job needs Y GB", and how to fix it.

## Acceptance criteria
- AC-1: `Settings().image_mem_gb == 6.0`; `[limits] image_mem_gb` in config.toml, `REELFORGE_IMAGE_MEM_GB`, and `--image-mem-gb` (on `up` and `doctor`) each override it, with precedence CLI > env > config.toml > default (one check per level).
- AC-2: Values 0, -1 and "abc" are rejected by settings validation (config.toml, env and CLI paths give a ConfigError naming `image_mem_gb`).
- AC-3: On the mock backend, jobs created via the API for generate, regenerate and refine report `mem_need_gb == image_mem_gb`; with a configured 3.5 they report 3.5.
- AC-4: With `available_gb` faked below the configured value, the cast job fails with a message containing "image_mem_gb" and the free and needed numbers (format above); with `available_gb` above it, the job succeeds.
- AC-5: `GENERATE_MEM_GB` and any hard-coded cast-job memory figure no longer appear in `src/`.
- AC-6: Ruff, pyright, eslint, `tsc --noEmit`, the web build, the full test suite and the Playwright flow pass; frozen M1 tests (including the pre-flight wording for non-cast jobs) are unchanged.
- AC-7 (manual, reference Mac): with Draw Things and Kontext loaded and about 8 GB available, "Generate candidates" renders 4 images; with `REELFORGE_IMAGE_MEM_GB=20` it fails with the message naming `image_mem_gb`.

## Out of scope
- Settings for ltx or mlx-audio memory (Phase 2).
- Changing `preflight_wait_s`, Ollama unloading, or the pre-flight algorithm.
- Any new UI for editing the setting.
- Changing the default after measuring real usage.

## Assumptions
- `[limits]` is a new config.toml section (existing runtime keys live under `[runtime]`); it needs adding to the TOML key map, which currently rejects unknown sections.
- The generic `preflight()` in `jobs/preflight.py` stays kind-agnostic; the setting hint is added only for `cast.generate` jobs (for example by the worker or caller), not for other kinds.
- `mem_need_gb` is read from settings at job-creation time; changing it needs a restart.

## Suggested split
(not large)

## Open questions
- none
