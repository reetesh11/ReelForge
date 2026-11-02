import pytest

from reelforge.config import ConfigError, load_settings


def _root(tmp_path):
    return {"REELFORGE_DATA_ROOT": str(tmp_path)}


def test_defaults(tmp_path):
    s = load_settings(env=_root(tmp_path))
    assert s.backend == "mock"
    assert s.image_fallback == "none"
    assert s.mflux_command is None
    assert s.max_upload_mb == 10


def test_env(tmp_path):
    env = {
        **_root(tmp_path),
        "REELFORGE_BACKEND": "real",
        "REELFORGE_IMAGE_FALLBACK": "mflux",
        "REELFORGE_MFLUX_COMMAND": "~/bin/mflux",
        "REELFORGE_MAX_UPLOAD_MB": "3",
    }
    s = load_settings(env=env)
    assert s.backend == "real" and s.image_fallback == "mflux" and s.max_upload_mb == 3
    assert s.mflux_command is not None and "~" not in str(s.mflux_command)


def test_toml(tmp_path):
    (tmp_path / "config.toml").write_text(
        "[runtime]\nimage_fallback = 'mflux'\nmax_upload_mb = 2\n"
        "[tools.mflux]\ncommand = '/x/mflux'\n"
    )
    s = load_settings(env=_root(tmp_path))
    assert s.image_fallback == "mflux" and s.max_upload_mb == 2
    assert str(s.mflux_command) == "/x/mflux"


def test_bad_upload_limit(tmp_path):
    with pytest.raises(ConfigError):
        load_settings(env={**_root(tmp_path), "REELFORGE_MAX_UPLOAD_MB": "0"})
