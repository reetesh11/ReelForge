import pytest

from reelforge.config import ConfigError, Settings, load_settings


def _root(tmp_path):
    return {"REELFORGE_DATA_ROOT": str(tmp_path)}


def test_defaults(tmp_path):
    s = load_settings(env=_root(tmp_path))
    assert (s.api_port, s.ui_port, s.host) == (7400, 7401, "127.0.0.1")
    assert s.models_path.name == "models.toml"


def test_precedence(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text("[server]\napi_port = 7411\n[services.ollama]\nurl = 'http://127.0.0.1:1'\n")
    env = {**_root(tmp_path), "REELFORGE_API_PORT": "7422"}
    assert load_settings(env=_root(tmp_path), config_path=cfg).api_port == 7411
    assert load_settings(env=env, config_path=cfg).api_port == 7422
    assert load_settings(cli={"api_port": 7433}, env=env, config_path=cfg).api_port == 7433
    assert load_settings(cli={"api_port": None}, env=env).api_port == 7422
    assert load_settings(env=_root(tmp_path), config_path=cfg).ollama_url == "http://127.0.0.1:1"


def test_toml_discovery_in_data_root(tmp_path):
    (tmp_path / "config.toml").write_text("[server]\nui_port = 7499\n")
    assert load_settings(env=_root(tmp_path)).ui_port == 7499


def test_errors(tmp_path):
    bad = tmp_path / "config.toml"
    bad.write_text("[server]\nx = = 1\n")
    with pytest.raises(ConfigError, match=r"config\.toml.*line 2"):
        load_settings(env=_root(tmp_path), config_path=bad)
    bad.write_text("[server]\nbogus = 1\n")
    with pytest.raises(ConfigError, match="bogus"):
        load_settings(env=_root(tmp_path), config_path=bad)
    with pytest.raises(ConfigError):
        load_settings(env=_root(tmp_path), config_path=tmp_path / "missing.toml")
    bad.unlink()
    with pytest.raises(ConfigError, match="host"):
        load_settings(cli={"host": "0.0.0.0"}, env=_root(tmp_path))
    with pytest.raises(ConfigError, match="api_port"):
        load_settings(cli={"api_port": 0}, env=_root(tmp_path))


def test_settings_rejects_unknown_field(tmp_path):
    with pytest.raises(ValueError):
        Settings(data_root=tmp_path, nope=1)  # type: ignore[call-arg]
