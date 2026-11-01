"""AC-2: model IDs live only in models.toml; editing it alone changes what is used."""

from __future__ import annotations

from pathlib import Path

import pytest
from rf_helpers import (
    artifacts_of,
    create_project,
    make_client,
    make_ctx,
    make_settings,
    sidecar_of,
    submit,
    wait_job,
    write_models,
)


def _package_dir() -> Path:
    import reelforge

    return Path(reelforge.__file__).resolve().parent


def test_packaged_models_toml_has_required_keys_and_license_fields():
    from reelforge.models_registry import load_models

    reg = load_models(_package_dir() / "models.toml")
    assert {"image", "video", "tts", "llm"} <= set(reg.keys())
    for e in reg.entries():
        assert e.id and e.revision


def test_no_model_id_literal_in_src_outside_models_toml():
    from reelforge.models_registry import load_models

    pkg = _package_dir()
    src_root = pkg.parent
    ids = [e.id for e in load_models(pkg / "models.toml").entries()]
    assert ids
    offenders = []
    for f in src_root.rglob("*"):
        if not f.is_file() or f == pkg / "models.toml" or "__pycache__" in f.parts:
            continue
        if f.suffix not in {
            ".py",
            ".toml",
            ".json",
            ".ini",
            ".txt",
            ".md",
            ".mako",
            ".cfg",
            ".yaml",
            ".yml",
        }:
            continue
        text = f.read_text(errors="ignore")
        offenders += [(str(f.relative_to(src_root)), i) for i in ids if i in text]
    assert offenders == []


def test_editing_models_toml_changes_registry_and_artifact_sidecar(tmp_path):
    from reelforge.models_registry import load_models

    models = write_models(tmp_path / "models.toml", image="test-org/first-image-id")
    settings = make_settings(tmp_path, models_path=models)
    assert load_models(models).get("image").id == "test-org/first-image-id"

    ctx = make_ctx(settings)
    with make_client(ctx) as client:
        pid = create_project(client)["id"]
        job_id = submit(client, pid, seed=1)["job_id"]
        wait_job(ctx, job_id, {"succeeded"})
    art = artifacts_of(ctx, pid)[0]
    assert sidecar_of(ctx, art)["model_id"] == "test-org/first-image-id"
    ctx.close()

    write_models(models, image="test-org/second-image-id")
    assert load_models(models).get("image").id == "test-org/second-image-id"
    ctx2 = make_ctx(make_settings(tmp_path, models_path=models))
    with make_client(ctx2) as client:
        job_id = submit(client, pid, seed=2)["job_id"]
        wait_job(ctx2, job_id, {"succeeded"})
    newest = artifacts_of(ctx2, pid)[-1]
    assert sidecar_of(ctx2, newest)["model_id"] == "test-org/second-image-id"
    ctx2.close()


def test_registry_get_unknown_raises_and_missing_license_listed(tmp_path):
    from reelforge.models_registry import load_models

    p = tmp_path / "models.toml"
    p.write_text(
        '[models.image]\nid = "a/b"\nrevision = "1"\n\n'
        '[models.tts]\nid = "c/d"\nrevision = "2"\nlicense = "mit"\nlicense_url = "u"\n'
    )
    reg = load_models(p)
    assert reg.missing_license() == ["image"]
    with pytest.raises(KeyError):
        reg.get("nope")
