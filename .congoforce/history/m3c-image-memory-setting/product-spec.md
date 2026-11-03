# Product spec — Make the image job memory requirement configurable (image_mem_gb)

## User-facing behaviour

### The setting
A new setting `image_mem_gb` tells ReelForge how much available memory (GB) an image job (Cast "Generate candidates", regenerate, refine) needs before it starts. Default: 6.0 (was a fixed 10.0). Sources, lowest to highest precedence:
1. Default: `6.0`
2. `config.toml`, new `[limits]` section:
   ```toml
   [limits]
   image_mem_gb = 6.0
   ```
3. Environment variable `REELFORGE_IMAGE_MEM_GB` (for example `REELFORGE_IMAGE_MEM_GB=20`)
4. CLI flag `--image-mem-gb <float>` on `reelforge up` and `reelforge doctor` (listed in each command's `--help`, like the other overrides, for example "Memory (GB) an image job needs free before it starts.")

The value is read when a job is created. Changing it requires restarting `up`. There is no UI for editing it.

### Cast flow
- Clicking "Generate candidates", regenerating, or refining creates a job whose `mem_need_gb` (visible in the job API response) equals the configured `image_mem_gb` (6.0 by default, 3.5 if configured as 3.5).
- If enough memory is available (after the existing Ollama unload and wait), the job runs as today. On the reference Mac with Draw Things and Kontext loaded and about 8 GB available, 4 images render.
- If not, the job fails and the existing Cast error panel shows, with its existing Retry button, exactly:
  `Only 7.9 GB free, job needs 6.0 GB. Close other apps, or lower image_mem_gb in config.toml.`
  The numbers are the actual free and needed values, each with one decimal place (`{free:.1f}`, `{need:.1f}`). The sentence structure and wording are otherwise fixed.
- Failure messages for any other job kind are unchanged: `Only {free:.1f} GB free, job needs {need:.1f} GB.`

### Docs
`docs/manual-checks.md`, section "M3 Cast (AC-13)", gains a note covering: the `image_mem_gb` setting and its default (6.0) with all four ways to set it; the symptom "Only X GB free, job needs Y GB"; and the fix (close other apps, or lower `image_mem_gb` in `[limits]` of config.toml, or set `REELFORGE_IMAGE_MEM_GB` / `--image-mem-gb`, then restart).

## Acceptance criteria
- AC-1: With no overrides, `Settings().image_mem_gb == 6.0`. Each of these alone sets the value (one check per level): `[limits] image_mem_gb` in config.toml; `REELFORGE_IMAGE_MEM_GB`; `--image-mem-gb` on `up`; `--image-mem-gb` on `doctor`. When several are present, precedence is CLI > env > config.toml > default. The `[limits]` section is accepted in config.toml without an unknown-section error.
- AC-2: The values `0`, `-1` and `"abc"` are each rejected when supplied via config.toml, env var, or CLI flag. The error is a `ConfigError` whose message names `image_mem_gb` (and, where the existing settings errors do so, the offending source). Startup does not proceed. `doctor` reports the same error. A positive value such as `0.5` is accepted.
- AC-3: On the mock backend, jobs created through the API for generate, regenerate and refine all report `mem_need_gb == settings.image_mem_gb`: 6.0 by default, 3.5 when configured as 3.5.
- AC-4: With `available_gb` faked below the configured value, the cast job ends failed with the message `Only {free:.1f} GB free, job needs {need:.1f} GB. Close other apps, or lower image_mem_gb in config.toml.` (contains "image_mem_gb" and both numbers). With `available_gb` above the configured value, the job succeeds. A non-cast job failing pre-flight keeps `Only {free:.1f} GB free, job needs {need:.1f} GB.` with no setting hint.
- AC-5: `GENERATE_MEM_GB` and any hard-coded memory figure for cast jobs no longer appear in `src/`.
- AC-6: Ruff, pyright, eslint, `tsc --noEmit`, the web build, the full test suite and the Playwright flow pass. Frozen M1 tests, including the pre-flight wording for non-cast jobs, are unchanged.
- AC-7 (manual, reference Mac): with Draw Things and Kontext loaded and about 8 GB available, "Generate candidates" renders 4 images. With `REELFORGE_IMAGE_MEM_GB=20` it fails, and the Cast error panel shows the message naming `image_mem_gb` with Retry available.

## Edge cases and errors
- Invalid values (0, negative, non-numeric, empty string): rejected at settings validation, before any job exists (AC-2).
- Value so high it can never be met (for example 20 on a 24 GB Mac): the job waits up to the existing pre-flight wait, then fails with the cast message; Retry stays available. The wait time is unchanged.
- Very small positive values (for example 0.1) are valid.
- Retry after failure creates a new job using the same configured value; the user must restart ReelForge after changing the setting for it to take effect.
- The numbers in the message are formatted to one decimal, so 6 configures and displays as `6.0`.
- Regenerate and refine use the same value and the same failure message as generate.

## Out of scope
- Memory settings for ltx or mlx-audio (Phase 2).
- Changing `preflight_wait_s`, Ollama unloading, or the pre-flight algorithm.
- Any UI for editing the setting.
- Changing the default after measuring real usage.

## Open questions
- none
