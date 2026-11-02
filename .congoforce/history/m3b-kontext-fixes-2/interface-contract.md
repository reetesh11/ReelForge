# Interface contract — m3b-kontext-fixes-2

- `reelforge.models_registry.ModelEntry`: new optional field `steps: int | None = None`. `ModelEntry(key=..., id=..., revision=..., steps=20).steps == 20`; omitted gives `None`; `steps <= 0` or non-int raises `pydantic.ValidationError`. `load_models(path)` reads `steps` from a `[models.<key>]` table and raises the same error for an invalid value.
- `reelforge.adapters.drawthings.DrawThingsAdapter(url, *, model_id=None, timeout_s=600.0)`:
  - `.check() -> HealthReport`: with `model_id` set, POSTs `{url}/sdapi/v1/txt2img` with JSON `width=128`, `height=128`, `steps=1`, `model=<model_id>`, `seed=0`, `prompt="health check"`. HTTP 422 gives `ok=False`, `detail="Draw Things doesn't have the model <id>"`. Timeout gives ok. 2xx gives ok.
  - `await .run(task, out_dir, progress, cancel)`: request body `steps` = `task.params["steps"]` if present, else `task.model.steps` if not None, else `4`. Applies to both `/sdapi/v1/txt2img` and `/sdapi/v1/img2img`. The body `model` is `task.model.id`.
- Packaged `src/reelforge/models.toml` `[models.image]`: `id = "flux_1_kontext_dev_q8p.ckpt"`, `revision = "unpinned"`, `steps = 20`, `license = "FLUX.1 Kontext [dev] Non-Commercial License"`, `license_url = "https://huggingface.co/black-forest-labs/FLUX.1-Kontext-dev"`.
- Cast job `cast.generate` (generate and refine) with the packaged registry sends Draw Things requests with `model` `flux_1_kontext_dev_q8p.ckpt` and `steps` 20.
- HTTP `GET /health`: includes `image_licence_warning` (string naming "FLUX.1 Kontext [dev] Non-Commercial License") with the packaged registry; the key is absent when the image model's licence is permissive (e.g. Apache-2.0 in a temporary `models.toml` passed via `Settings.models_path`).
- Cast API/UI: `GET /api/v1/projects/{id}/cast` has `licence_warning` only for a non-permissive image model; the Cast screen shows it and the approve flow needs the "Approve anyway" confirmation button. Each artifact sidecar records the model licence (existing behaviour).
- Docs: `docs/manual-checks.md` M3 rows 2, 4 and 11 as in R8.
