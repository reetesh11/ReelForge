"""AC-1: config precedence cli > env > config.toml > defaults."""

from __future__ import annotations

from pathlib import Path

import pytest


def _toml(tmp_path: Path, text: str) -> Path:
    p = tmp_path / "config.toml"
    p.write_text(text)
    return p


def _root_env(tmp_path: Path) -> dict[str, str]:
    return {"REELFORGE_DATA_ROOT": str(tmp_path / "root")}


def test_default_level(tmp_path):
    from reelforge.config import load_settings

    s = load_settings(env=_root_env(tmp_path))
    assert s.api_port == 7400
    assert s.ui_port == 7401
    assert s.host == "127.0.0.1"
    assert s.backend == "mock"
    assert s.api_url == "http://127.0.0.1:7400"
    assert s.db_path == s.data_root / "reelforge.db"
    assert s.cache_tmp == s.data_root / "cache" / "tmp"


def test_config_toml_overrides_default(tmp_path):
    from reelforge.config import load_settings

    cfg = _toml(tmp_path, "[server]\napi_port = 7411\n[runtime]\nmax_light_jobs = 2\n")
    s = load_settings(env=_root_env(tmp_path), config_path=cfg)
    assert s.api_port == 7411
    assert s.max_light_jobs == 2


def test_env_overrides_config_toml(tmp_path):
    from reelforge.config import load_settings

    cfg = _toml(tmp_path, "[server]\napi_port = 7411\n")
    env = {**_root_env(tmp_path), "REELFORGE_API_PORT": "7422"}
    s = load_settings(env=env, config_path=cfg)
    assert s.api_port == 7422


def test_cli_overrides_env(tmp_path):
    from reelforge.config import load_settings

    cfg = _toml(tmp_path, "[server]\napi_port = 7411\n")
    env = {**_root_env(tmp_path), "REELFORGE_API_PORT": "7422"}
    s = load_settings(cli={"api_port": 7433}, env=env, config_path=cfg)
    assert s.api_port == 7433


def test_cli_none_is_ignored(tmp_path):
    from reelforge.config import load_settings

    env = {**_root_env(tmp_path), "REELFORGE_API_PORT": "7422"}
    s = load_settings(cli={"api_port": None}, env=env)
    assert s.api_port == 7422


def test_config_toml_found_in_data_root(tmp_path):
    from reelforge.config import load_settings

    root = tmp_path / "root"
    root.mkdir()
    (root / "config.toml").write_text("[server]\nui_port = 7499\n")
    s = load_settings(env={"REELFORGE_DATA_ROOT": str(root)})
    assert s.ui_port == 7499


def test_host_must_be_loopback_ip(tmp_path):
    from reelforge.config import ConfigError, load_settings

    for bad in ("0.0.0.0", "localhost", "192.168.1.5"):
        with pytest.raises(ConfigError) as ei:
            load_settings(cli={"host": bad}, env=_root_env(tmp_path))
        assert "host" in str(ei.value)


def test_invalid_port_names_key(tmp_path):
    from reelforge.config import ConfigError, load_settings

    with pytest.raises(ConfigError) as ei:
        load_settings(env={**_root_env(tmp_path), "REELFORGE_API_PORT": "70000"})
    assert "api_port" in str(ei.value)


def test_malformed_toml_names_file_and_line(tmp_path):
    from reelforge.config import ConfigError, load_settings

    cfg = _toml(tmp_path, "[server]\napi_port = 7411\nthis is = = not toml\n")
    with pytest.raises(ConfigError) as ei:
        load_settings(env=_root_env(tmp_path), config_path=cfg)
    msg = str(ei.value)
    assert "config.toml" in msg
    assert "3" in msg


def test_unknown_key_and_missing_explicit_file_rejected(tmp_path):
    from reelforge.config import ConfigError, load_settings

    cfg = _toml(tmp_path, "[server]\nbogus = 1\n")
    with pytest.raises(ConfigError):
        load_settings(env=_root_env(tmp_path), config_path=cfg)
    with pytest.raises(ConfigError):
        load_settings(env=_root_env(tmp_path), config_path=tmp_path / "nope.toml")
