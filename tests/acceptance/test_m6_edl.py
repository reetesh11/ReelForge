"""m6 R1/R2 (typed models), R8, AC-15: EDL schema, hashing, settings, stage order."""

from __future__ import annotations

import json
import pytest


def _edl(durations=(2.0, 3.0), transitions=(0.0, 0.0), **over):
    from reelforge.assembly.edl import Edl, EdlEndCard, EdlMusic, EdlShot

    video = [
        EdlShot(
            scene_id=f"s{i + 1}", artifact=f"a{i + 1}", source_duration_s=d, in_s=0.0, out_s=d,
            transition_in_s=t,
        )
        for i, (d, t) in enumerate(zip(durations, transitions))
    ]
    return Edl(
        project_id="p1", video=video, dialogue=[], captions=[], music=EdlMusic(),
        end_card=EdlEndCard(), **over,
    )


def test_default_edl_has_empty_music_slots_and_disabled_end_card():
    edl = _edl()
    d = edl.model_dump(mode="json")
    assert d["music"]["tracks"] == [] and d["music"]["duck"] is False
    assert d["end_card"]["enabled"] is False
    assert d["end_card"]["duration_s"] == 1.5 and d["end_card"]["template"] == "default"
    assert (d["version"], d["fps"], d["width"], d["height"]) == (1, 24, 1080, 1920)
    assert d["caption_style"] == "auto"
    for key in ("video", "dialogue", "captions", "caption_style", "music", "end_card", "project_id"):
        assert key in d


def test_constants_and_extra_fields_are_rejected():
    from pydantic import ValidationError
    from reelforge.assembly.edl import FPS, HEIGHT, WIDTH, Edl, EdlShot

    assert (FPS, WIDTH, HEIGHT) == (24, 1080, 1920)
    good = _edl().model_dump(mode="json")
    Edl.model_validate(good)
    with pytest.raises(ValidationError):
        Edl.model_validate({**good, "bogus": 1})
    with pytest.raises(ValidationError):
        EdlShot(scene_id="s1", artifact="a", source_duration_s=1.0, in_s=0.0, out_s=1.0, bogus=1)  # type: ignore[call-arg]


def test_timeline_maths_with_crossfades():
    edl = _edl((2.0, 3.0), (0.0, 0.5))
    assert edl.shot_start_s(0) == 0.0
    assert edl.shot_start_s(1) == pytest.approx(1.5)
    assert edl.total_duration_s == pytest.approx(4.5)
    assert edl.total_frames == 108
    # the first shot's transition is ignored
    edl = _edl((2.0, 3.0), (0.5, 0.0))
    assert edl.shot_start_s(1) == pytest.approx(2.0)
    assert edl.total_duration_s == pytest.approx(5.0) and edl.total_frames == 120


def test_timeline_uses_trimmed_length():
    edl = _edl((4.0, 3.0))
    shots = [edl.video[0].model_copy(update={"in_s": 0.5, "out_s": 2.0}), edl.video[1]]
    edl = edl.model_copy(update={"video": shots})
    assert edl.shot_start_s(1) == pytest.approx(1.5)
    assert edl.total_duration_s == pytest.approx(4.5)


def test_hash_is_stable_sensitive_and_key_order_independent():
    from reelforge.assembly.edl import Edl, edl_hash

    edl = _edl()
    h = edl_hash(edl)
    assert len(h) == 64 and int(h, 16) >= 0
    assert edl_hash(_edl()) == h
    shuffled = json.loads(json.dumps(edl.model_dump(mode="json")))
    shuffled = dict(reversed(list(shuffled.items())))
    assert edl_hash(Edl.model_validate(shuffled)) == h
    assert edl_hash(edl.model_copy(update={"caption_style": "bold_pop"})) != h


def test_save_load_round_trip_is_atomic(tmp_path):
    from reelforge.assembly.edl import load_edl, save_edl

    edl = _edl()
    path = tmp_path / "sub" / "edl.json"
    path.parent.mkdir()
    save_edl(edl, path)
    assert load_edl(path) == edl
    assert json.loads(path.read_text())["music"]["tracks"] == []
    assert [p.name for p in path.parent.iterdir()] == ["edl.json"]
    save_edl(edl.model_copy(update={"caption_style": "clean_subtitle"}), path)
    assert load_edl(path).caption_style == "clean_subtitle"


def test_caption_presets():
    from reelforge.assembly.edl import CAPTION_PRESETS

    assert CAPTION_PRESETS == {
        "bold_pop": "Bold pop",
        "clean_subtitle": "Clean subtitle",
        "hindi_devanagari": "Hindi Devanagari",
    }


def test_new_settings_fields(tmp_path):
    from pathlib import Path

    from pydantic import ValidationError
    from reelforge.config import Settings, load_settings

    s = Settings(data_root=tmp_path)
    assert s.preview_debounce_s == 1.0
    assert s.devanagari_font == Path("/System/Library/Fonts/Kohinoor.ttc")
    assert s.devanagari_font_family == "Kohinoor Devanagari"
    with pytest.raises(ValidationError):
        Settings(data_root=tmp_path, preview_debounce_s=-0.1)
    loaded = load_settings(
        env={
            "REELFORGE_DATA_ROOT": str(tmp_path),
            "REELFORGE_PREVIEW_DEBOUNCE_S": "0.25",
            "REELFORGE_DEVANAGARI_FONT": "/tmp/f.ttf",
            "REELFORGE_DEVANAGARI_FONT_FAMILY": "Fam",
        }
    )
    assert loaded.preview_debounce_s == 0.25
    assert loaded.devanagari_font == Path("/tmp/f.ttf") and loaded.devanagari_font_family == "Fam"


def test_stage_order_has_reel_exported():
    from reelforge.api.stages import STAGE_ORDER, derive_stages, stages_approved

    assert STAGE_ORDER == [
        "DRAFT", "STORY_APPROVED", "CAST_APPROVED", "VOICES_APPROVED", "FRAMES_APPROVED",
        "SHOTS_APPROVED", "REEL_EXPORTED", "EXPORTED",
    ]
    assert stages_approved("REEL_EXPORTED") == 6
    stages = derive_stages("REEL_EXPORTED", [])
    assert [s.state for s in stages] == ["approved"] * 6
    assert stages[-1].key == "assembly"
