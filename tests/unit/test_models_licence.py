import pytest

from reelforge.config import PACKAGED_MODELS
from reelforge.models_registry import (
    ModelEntry,
    ModelLicenceError,
    ModelRegistry,
    check_audio_licences,
    load_models,
)


def _toml(tmp_path, key, licence):
    p = tmp_path / "models.toml"
    p.write_text(
        PACKAGED_MODELS.read_text()
        + f'\n[models.{key}]\nid = "x/y"\nrevision = "r"\nlicense = "{licence}"\n'
    )
    return p


@pytest.mark.parametrize("licence", ["MIT", "apache-2.0", "Unlicense"])
def test_allowed_audio_licences_load(tmp_path, licence):
    assert load_models(_toml(tmp_path, "audio_sfx", licence)).get("audio_sfx").license == licence


@pytest.mark.parametrize("licence", ["", "CC-BY-NC-4.0", "GPL-3.0"])
def test_other_audio_licences_are_refused(tmp_path, licence):
    with pytest.raises(ModelLicenceError):
        load_models(_toml(tmp_path, "audio_sfx", licence))


def test_a_hand_built_registry_skips_the_check():
    bad = ModelEntry(key="audio_x", id="a", revision="r", license="GPL-3.0")
    assert ModelRegistry([bad]).get("audio_x") is bad
    with pytest.raises(ModelLicenceError):
        check_audio_licences([bad])


def test_packaged_stub_is_commercial():
    assert load_models(PACKAGED_MODELS).get("audio_stub").license == "Apache-2.0"
