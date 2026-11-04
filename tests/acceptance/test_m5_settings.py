"""m5 AC-7 (shot_mem_gb precedence and validation), R5/R7 settings, models.toml steps."""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _load(tmp_path, *, cli=None, env=None, toml: str | None = None):
    from reelforge.config import load_settings

    cfg = None
    if toml is not None:
        cfg = tmp_path / "config.toml"
        cfg.write_text(toml)
    return load_settings(cli={"data_root": tmp_path / "data", **(cli or {})}, env=env or {}, config_path=cfg)


def test_shot_mem_default_and_precedence(tmp_path):
    from reelforge.config import Settings

    assert Settings().shot_mem_gb == 16.0
    toml = "[limits]\nshot_mem_gb = 12.0\n"
    env = {"REELFORGE_SHOT_MEM_GB": "13.0"}
    assert _load(tmp_path, toml=toml).shot_mem_gb == 12.0
    assert _load(tmp_path, toml=toml, env=env).shot_mem_gb == 13.0
    assert _load(tmp_path, toml=toml, env=env, cli={"shot_mem_gb": 14.5}).shot_mem_gb == 14.5


@pytest.mark.parametrize("bad", ["0", "-1", "abc", "nan", "inf"])
def test_shot_mem_rejects_bad_values(tmp_path, bad):
    from reelforge.config import ConfigError

    with pytest.raises(ConfigError) as ei:
        _load(tmp_path, env={"REELFORGE_SHOT_MEM_GB": bad})
    assert ei.value.key == "shot_mem_gb"
    if bad in ("0", "-1"):
        with pytest.raises(ConfigError) as ei:
            _load(tmp_path, toml=f"[limits]\nshot_mem_gb = {bad}\n")
        assert ei.value.key == "shot_mem_gb"
        with pytest.raises(ConfigError) as ei:
            _load(tmp_path, cli={"shot_mem_gb": float(bad)})
        assert ei.value.key == "shot_mem_gb"


@pytest.mark.parametrize("cmd", ["up", "doctor"])
def test_shot_mem_flag_reaches_settings_and_help(monkeypatch, tmp_path, cmd):
    from reelforge import cli as cli_mod
    from typer.testing import CliRunner

    seen: list = []
    if cmd == "doctor":
        monkeypatch.setattr(cli_mod, "run_doctor", lambda s: seen.append(s) or None)
        monkeypatch.setattr(cli_mod, "format_report", lambda r: [])
    else:
        monkeypatch.setattr(cli_mod, "run_up", lambda s, allow_degraded=False: seen.append(s) or 0)
    res = CliRunner().invoke(cli_mod.app, [cmd, "--data-root", str(tmp_path / "d"), "--shot-mem-gb", "11.5"])
    assert seen, res.output
    assert seen[0].shot_mem_gb == 11.5
    assert "--shot-mem-gb" in CliRunner().invoke(cli_mod.app, [cmd, "--help"]).output


def test_shot_quality_and_sizes_defaults_and_levels(tmp_path):
    from reelforge.config import Settings

    s = Settings()
    assert (s.shot_quality, s.shot_draft_size, s.shot_final_size) == ("draft", "320x576", "448x768")
    assert (s.shot_timeout_s, s.max_clip_mb) == (1800.0, 100)
    toml = '[runtime]\nshot_quality = "final"\nshot_draft_size = "352x640"\nshot_timeout_s = 90.0\nmax_clip_mb = 7\n'
    got = _load(tmp_path, toml=toml)
    assert (got.shot_quality, got.shot_draft_size, got.shot_timeout_s, got.max_clip_mb) == (
        "final", "352x640", 90.0, 7)
    env = {"REELFORGE_SHOT_QUALITY": "draft", "REELFORGE_SHOT_DRAFT_SIZE": "384x672",
           "REELFORGE_SHOT_FINAL_SIZE": "480x832"}
    got = _load(tmp_path, toml=toml, env=env)
    assert (got.shot_quality, got.shot_draft_size, got.shot_final_size) == ("draft", "384x672", "480x832")


@pytest.mark.parametrize("field,bad", [
    ("shot_draft_size", "300x576"), ("shot_draft_size", "320x500"), ("shot_draft_size", "320"),
    ("shot_final_size", "abc"), ("shot_final_size", "448x770"),
])
def test_shot_size_must_be_wxh_multiples_of_32(tmp_path, field, bad):
    from reelforge.config import ConfigError

    with pytest.raises(ConfigError) as ei:
        _load(tmp_path, env={f"REELFORGE_{field.upper()}": bad})
    assert ei.value.key == field


def test_packaged_video_model_has_steps_and_keeps_id():
    from reelforge.models_registry import load_models

    reg = load_models(ROOT / "src" / "reelforge" / "models.toml")
    assert reg.get("video").steps == 8
    assert reg.get("video").id == "dgrauet/ltx-2.3-mlx-q4"
