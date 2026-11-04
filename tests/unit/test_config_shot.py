from __future__ import annotations

import pytest

from reelforge.config import ConfigError, Settings, load_settings


def test_defaults():
    s = Settings()
    assert (s.shot_mem_gb, s.shot_quality) == (16.0, "draft")
    assert (s.shot_draft_size, s.shot_final_size) == ("320x576", "448x768")
    assert (s.shot_timeout_s, s.max_clip_mb) == (1800.0, 100)


def test_precedence(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text("[limits]\nshot_mem_gb = 12.0\n")
    env = {"REELFORGE_SHOT_MEM_GB": "13"}
    base = {"data_root": tmp_path}
    assert load_settings(cli=base, env={}, config_path=cfg).shot_mem_gb == 12.0
    assert load_settings(cli=base, env=env, config_path=cfg).shot_mem_gb == 13.0
    both = load_settings(cli={**base, "shot_mem_gb": 14.0}, env=env, config_path=cfg)
    assert both.shot_mem_gb == 14.0


@pytest.mark.parametrize("value", ["0", "-2", "abc", "nan"])
def test_bad_mem_value(tmp_path, value):
    with pytest.raises(ConfigError) as ei:
        load_settings(cli={"data_root": tmp_path}, env={"REELFORGE_SHOT_MEM_GB": value})
    assert ei.value.key == "shot_mem_gb"


@pytest.mark.parametrize("value", ["300x576", "320x500", "320", "axb", "0x32"])
def test_bad_size(tmp_path, value):
    with pytest.raises(ConfigError) as ei:
        load_settings(cli={"data_root": tmp_path}, env={"REELFORGE_SHOT_DRAFT_SIZE": value})
    assert ei.value.key == "shot_draft_size"
