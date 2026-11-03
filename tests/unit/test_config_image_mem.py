"""Implementation tests for the image_mem_gb setting."""

from __future__ import annotations

from pathlib import Path

import pytest

from reelforge.config import ConfigError, Settings, load_settings


def test_default() -> None:
    assert Settings().image_mem_gb == 6.0


def test_precedence(tmp_path: Path) -> None:
    cfg = tmp_path / "config.toml"
    cfg.write_text("[limits]\nimage_mem_gb = 3.0\n")
    assert load_settings(env={}, config_path=cfg).image_mem_gb == 3.0
    env = {"REELFORGE_IMAGE_MEM_GB": "4.5"}
    assert load_settings(env=env, config_path=cfg).image_mem_gb == 4.5
    assert load_settings(cli={"image_mem_gb": 2.5}, env=env, config_path=cfg).image_mem_gb == 2.5


@pytest.mark.parametrize("bad", ["0", "-1", "abc", ""])
def test_env_invalid(bad: str) -> None:
    with pytest.raises(ConfigError) as exc:
        load_settings(env={"REELFORGE_IMAGE_MEM_GB": bad})
    assert exc.value.key == "image_mem_gb"


def test_limits_unknown_key(tmp_path: Path) -> None:
    cfg = tmp_path / "config.toml"
    cfg.write_text("[limits]\nbogus = 1\n")
    with pytest.raises(ConfigError):
        load_settings(env={}, config_path=cfg)
