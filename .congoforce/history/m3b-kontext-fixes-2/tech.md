# Tech spec — Switch default image model to Kontext, add per-model steps, fix Draw Things doctor probe

## Approach
Four small edits. (1) Probe size 128 x 128 in `DrawThingsAdapter._model_check`; commit `097e493` (reachable in this repo) already does this plus a unit test, so cherry-pick it. The 422 and timeout handling already exists in `_model_check`. (2) Add optional `steps: int | None = None` (positive, `Field(gt=0)`) to `ModelEntry` in `src/reelforge/models_registry.py`; an invalid value raises the pydantic `ValidationError` at load, as other registry errors do. (3) In `DrawThingsAdapter.run`, resolve steps as task param, then `task.model.steps`, then `DEFAULT_STEPS`. The cast job already passes the registry entry as `TaskSpec.model` and puts no `steps` in params, so generate and refine pick up the entry steps with no change to `cast/generate.py`. (4) Change the packaged `models.toml` image entry to Kontext with `steps = 20`. The existing licence code (`cast/licence.py`, `/health`, Status, Cast UI) already warns on "Non-Commercial", so R6 follows from the data change. Then revise the two pinned tests, the e2e flow and the manual-checks doc.

## Interface contract
- `reelforge.models_registry.ModelEntry`: new optional field `steps: int | None = None`. `ModelEntry(key=..., id=..., revision=..., steps=20).steps == 20`; omitted gives `None`; `steps <= 0` or non-int raises `pydantic.ValidationError`. `load_models(path)` reads `steps` from a `[models.<key>]` table and raises the same error for an invalid value.
- `reelforge.adapters.drawthings.DrawThingsAdapter(url, *, model_id=None, timeout_s=600.0)`:
  - `.check() -> HealthReport`: with `model_id` set, POSTs `{url}/sdapi/v1/txt2img` with JSON `width=128`, `height=128`, `steps=1`, `model=<model_id>`, `seed=0`, `prompt="health check"`. HTTP 422 gives `ok=False`, `detail="Draw Things doesn't have the model <id>"`. Timeout gives ok. 2xx gives ok.
  - `await .run(task, out_dir, progress, cancel)`: request body `steps` = `task.params["steps"]` if present, else `task.model.steps` if not None, else `4`. Applies to both `/sdapi/v1/txt2img` and `/sdapi/v1/img2img`. The body `model` is `task.model.id`.
- Packaged `src/reelforge/models.toml` `[models.image]`: `id = "flux_1_kontext_dev_q8p.ckpt"`, `revision = "unpinned"`, `steps = 20`, `license = "FLUX.1 Kontext [dev] Non-Commercial License"`, `license_url = "https://huggingface.co/black-forest-labs/FLUX.1-Kontext-dev"`.
- Cast job `cast.generate` (generate and refine) with the packaged registry sends Draw Things requests with `model` `flux_1_kontext_dev_q8p.ckpt` and `steps` 20.
- HTTP `GET /health`: includes `image_licence_warning` (string naming "FLUX.1 Kontext [dev] Non-Commercial License") with the packaged registry; the key is absent when the image model's licence is permissive (e.g. Apache-2.0 in a temporary `models.toml` passed via `Settings.models_path`).
- Cast API/UI: `GET /api/v1/projects/{id}/cast` has `licence_warning` only for a non-permissive image model; the Cast screen shows it and the approve flow needs the "Approve anyway" confirmation button. Each artifact sidecar records the model licence (existing behaviour).
- Docs: `docs/manual-checks.md` M3 rows 2, 4 and 11 as in R8.

## Data and state changes
Config only: optional `steps` key in `models.toml` entries. No DB or env changes.

## Tasks
1. **Fix the Draw Things probe size** — `src/reelforge/adapters/drawthings.py`, `tests/unit/test_drawthings_adapter.py` (modified): `git cherry-pick 097e493` (64 to 128 plus its unit test). Re-implement by hand if the pick conflicts.
2. **Per-model steps** — `src/reelforge/models_registry.py` (add `steps: int | None = Field(default=None, gt=0)`), `src/reelforge/adapters/drawthings.py` (`steps = params["steps"]` if present, else `task.model.steps`, else `DEFAULT_STEPS`), `tests/unit/test_models_registry.py`, `tests/unit/test_drawthings_adapter.py` (modified): add the implementation tests below.
3. **Kontext default and revised tests** — `src/reelforge/models.toml` (modified: image entry per R5), `tests/acceptance/test_m3_unchanged.py` (`test_health_has_no_licence_key_for_permissive_default_model`: write a temporary `models.toml` with an Apache-2.0 image entry and pass it as `models_path` in `make_settings`, then assert no key), `tests/acceptance/test_m3_cast_approve.py` (`test_permissive_licence_has_no_warning_in_cast`: same). Keep the other entries identical. Fix any other unit test that pins `flux_1_schnell_q5p.ckpt` or Apache for the image entry (grep `tests/unit`); leave frozen acceptance tests beyond the two named alone and report them.
4. **E2E and manual-check docs** — `web/e2e/cast.spec.ts` (after clicking "Approve this one", click the "Approve anyway" button in the confirmation dialog, then the existing assertions), `docs/manual-checks.md` (row 2: the amber "Image model licence" row is expected with Kontext; row 4: about 1 minute per image at 20 steps, and images must be sharp; row 11: the licence warning and "Approve anyway" confirmation dialog are expected).

## Implementation tests
- `tests/unit/test_models_registry.py`: `steps` loads from TOML; absent gives `None`; `0` and `-1` raise `ValidationError`; the packaged registry image entry has the Kontext id, steps 20 and a non-commercial licence.
- `tests/unit/test_drawthings_adapter.py` (stub server): the probe body is 128 x 128 with steps 1; a stub that returns 422 for width < 128 passes for a known model; a model-rejecting stub fails with the "doesn't have the model" message; a timeout passes. Body steps: entry 20 with no task param gives 20 (txt2img and img2img); a task param of 8 gives 8; neither gives 4.
- `tests/unit/` cast job test with the packaged registry and the stub server: generate and refine requests carry the Kontext model id and steps 20.

## Risks and rollout
The new default is non-commercial, so the licence warning and confirmation now show by default. Existing tests that implicitly assumed a permissive default may fail in task 3 and must be revised or reported. Real sharpness and timing (AC-8) are manual on the reference Mac. Reachability of 097e493 was confirmed (`git cat-file -t` returns commit).

## Open questions
- none
