import pytest

from reelforge.config import ConfigError, Settings, load_settings


def _load(tmp_path, *, cli=None, env=None, toml=None):
    cfg = None
    if toml is not None:
        cfg = tmp_path / "config.toml"
        cfg.write_text(toml)
    return load_settings(
        cli={"data_root": tmp_path / "d", **(cli or {})}, env=env or {}, config_path=cfg
    )


def test_defaults():
    s = Settings()
    assert (s.voice_model, s.voice_mem_gb) == ("omnivoice", 4.0)


def test_voice_model_precedence(tmp_path):
    toml = '[runtime]\nvoice_model = "kokoro"\n'
    assert _load(tmp_path, toml=toml).voice_model == "kokoro"
    assert (
        _load(tmp_path, toml=toml, env={"REELFORGE_VOICE_MODEL": "omnivoice"}).voice_model
        == "omnivoice"
    )
    env = {"REELFORGE_VOICE_MODEL": "omnivoice"}
    assert _load(tmp_path, env=env, cli={"voice_model": "kokoro"}).voice_model == "kokoro"


def test_voice_model_error_lists_choices(tmp_path):
    with pytest.raises(ConfigError, match="omnivoice.*kokoro"):
        _load(tmp_path, cli={"voice_model": "bark"})


def test_voice_mem_precedence_and_rejects(tmp_path):
    toml = "[limits]\nvoice_mem_gb = 2.0\n"
    assert _load(tmp_path, toml=toml).voice_mem_gb == 2.0
    assert _load(tmp_path, toml=toml, env={"REELFORGE_VOICE_MEM_GB": "3"}).voice_mem_gb == 3.0
    for bad in ("0", "-2", "x", "nan"):
        with pytest.raises(ConfigError) as ei:
            _load(tmp_path, env={"REELFORGE_VOICE_MEM_GB": bad})
        assert ei.value.key == "voice_mem_gb"
