from __future__ import annotations

from pathlib import Path

from reelforge.api.stages import derive_stages, stages_approved
from reelforge.config import Settings, load_settings


def test_toml_runtime_keys(tmp_path: Path) -> None:
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        '[runtime]\npreview_debounce_s = 0.5\ndevanagari_font = "/tmp/x.ttf"\n'
        'devanagari_font_family = "Fam"\n'
    )
    s = load_settings(env={}, config_path=cfg)
    assert s.preview_debounce_s == 0.5
    assert s.devanagari_font == Path("/tmp/x.ttf")
    assert s.devanagari_font_family == "Fam"
    assert Settings(data_root=tmp_path).preview_debounce_s == 1.0


def test_reel_exported_stage() -> None:
    assert stages_approved("REEL_EXPORTED") == 6
    assert stages_approved("EXPORTED") == 6
    stages = derive_stages("REEL_EXPORTED", [])
    assert stages[-1].state == "approved"
