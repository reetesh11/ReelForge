from pathlib import Path

import pytest
from pydantic import ValidationError

import reelforge
from reelforge.models_registry import load_models

PKG = Path(reelforge.__file__).resolve().parent


def test_packaged_registry():
    reg = load_models(PKG / "models.toml")
    assert {"image", "video", "tts", "llm"} <= set(reg.keys())
    assert reg.missing_license() == []


def test_edit_changes_entry(tmp_path):
    p = tmp_path / "models.toml"
    p.write_text('[models.image]\nid = "a/one"\nrevision = "1"\n')
    reg = load_models(p)
    assert reg.get("image").id == "a/one" and reg.missing_license() == ["image"]
    p.write_text('[models.image]\nid = "a/two"\nrevision = "1"\n')
    assert load_models(p).get("image").id == "a/two"


def test_no_model_id_literals_in_src():
    ids = [e.id for e in load_models(PKG / "models.toml").entries()]
    for f in PKG.rglob("*"):
        if f.is_file() and f.suffix in {".py", ".toml", ".json"} and f.name != "models.toml":
            text = f.read_text(errors="ignore")
            assert not [i for i in ids if i in text], f


def test_steps_loads_and_defaults_to_none(tmp_path):
    p = tmp_path / "models.toml"
    p.write_text(
        '[models.a]\nid = "x"\nrevision = "1"\nsteps = 20\n[models.b]\nid = "y"\nrevision = "1"\n'
    )
    reg = load_models(p)
    assert reg.get("a").steps == 20 and reg.get("b").steps is None


@pytest.mark.parametrize("bad", ["0", "-1"])
def test_invalid_steps_raises(tmp_path, bad):
    p = tmp_path / "models.toml"
    p.write_text(f'[models.a]\nid = "x"\nrevision = "1"\nsteps = {bad}\n')
    with pytest.raises(ValidationError):
        load_models(p)


def test_packaged_image_entry_is_kontext():
    e = load_models(PKG / "models.toml").get("image")
    assert e.id == "flux_1_kontext_dev_q8p.ckpt" and e.steps == 20
    assert "Non-Commercial" in e.license
