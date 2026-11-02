---
class: bug
size: small
title: Switch default image model to Kontext, add per-model steps, fix Draw Things doctor probe
---
# Requirements — Switch default image model to Kontext, add per-model steps, fix Draw Things doctor probe

## Problem
A live run on the reference Mac showed three defects after M3. Doctor always reports the pinned Draw Things model as missing because the 64 x 64 probe is rejected with HTTP 422 by the real server. The built-in 4 steps suits FLUX.1 Schnell but gives badly blurred images with Kontext (20 steps is sharp). The registry default should be Kontext, which is non-commercial, so licence warnings and approval confirmation now apply by default.

## Requirements
- R1. When the Draw Things health check probes for the model, the system shall request 128 x 128 at 1 step (`src/reelforge/adapters/drawthings.py`, currently 64 x 64).
- R2. If the probe gets HTTP 422 for an unknown model, then doctor shall fail with "Draw Things doesn't have the model <id>"; when the probe times out, doctor shall treat it as fine.
- R3. Where a `models.toml` entry has an optional `steps` field, the Draw Things adapter shall send it as `steps` in txt2img and img2img requests when the task gives no `steps`. Precedence: task param, then model entry, then built-in default 4.
- R4. The cast job (generate and refine) shall use the model entry's steps.
- R5. The packaged `models.toml` `[models.image]` shall be `id = "flux_1_kontext_dev_q8p.ckpt"`, `steps = 20`, license `FLUX.1 Kontext [dev] Non-Commercial License`, license_url `https://huggingface.co/black-forest-labs/FLUX.1-Kontext-dev`.
- R6. While the image model has a non-permissive licence, the system shall show the licence warning in `/health` (`image_licence_warning`), the Status panel and the Cast screen, and approval shall require confirmation ("Approve anyway").
- R7. Tests pinning the old Schnell/permissive default (`test_permissive_licence_has_no_warning_in_cast`, `test_health_has_no_licence_key_for_permissive_default_model`) shall be revised to set a permissive model explicitly via a temporary `models.toml` and still assert no warning. `web/e2e/cast.spec.ts` shall click "Approve anyway".
- R8. `docs/manual-checks.md` M3 steps 2 and 11 shall state the amber licence row and confirmation dialog are expected; step 4 shall note about 1 minute per image at 20 steps and that images must be sharp.

## Acceptance criteria
- AC-1: Against a stub returning 422 for width or height below 128, the doctor model check passes for a known model and fails with "Draw Things doesn't have the model <id>" when the stub rejects the model name. A timeout still passes.
- AC-2: A `steps` value in a `models.toml` entry appears as `steps` in txt2img and img2img request bodies when the task gives none; a task `steps` overrides it; with neither, the body carries 4.
- AC-3: With the packaged `models.toml`, the cast job's Draw Things requests (generate and refine, stub server) carry `model` `flux_1_kontext_dev_q8p.ckpt` and `steps` 20.
- AC-4: With the packaged `models.toml`, `/health` has `image_licence_warning` naming the Kontext non-commercial licence, the Cast screen displays it, approval succeeds after confirming, and each artifact sidecar records the licence.
- AC-5: With an explicit permissive model entry in a temporary `models.toml`, no licence warning appears in `/health`, Status or Cast, and approval needs no confirmation.
- AC-6: Ruff, pyright, eslint, `tsc --noEmit`, web build, full test suite and the Playwright flow pass.
- AC-7: `docs/manual-checks.md` M3 steps 2, 4 and 11 contain the changes in R8 (checked by reading).
- AC-8 (manual, reference Mac): with Draw Things and Kontext loaded, `reelforge doctor` shows `draw_things` passing and one `cast.generate` job renders 4 sharp 9:16 candidates in about 1 minute each.

## Out of scope
- Changing other models' entries or adding `steps` to non-image models.
- New sampler options beyond `steps`.
- Editing frozen M3 tests beyond the two named in R7 (any other pinning the old default is revised only at Gate 2).

## Assumptions
- Commit `097e493` on the old `congoforce/m3-cast` branch may be reused for R1 (size 128 plus one unit test); it may not be reachable in this repo, so re-implement if absent.
- `steps` in `models.toml` is a positive integer; an invalid value is a config error handled like other registry errors.
- Classified as bug (the doctor probe and blurry output are defects) with a small default-model change attached.

## Open questions
- none
