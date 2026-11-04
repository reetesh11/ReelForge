from __future__ import annotations

from pathlib import Path

import pytest

from reelforge.assembly.edl import (
    Edl,
    EdlShot,
    edl_hash,
    load_edl,
    save_edl,
    to_frames,
)


def _edl(*lengths: float, fade: float = 0.0) -> Edl:
    video = [
        EdlShot(
            scene_id=f"s{i}",
            artifact=f"a{i}",
            source_duration_s=n,
            in_s=0.0,
            out_s=n,
            transition_in_s=fade if i else 0.0,
        )
        for i, n in enumerate(lengths)
    ]
    return Edl(project_id="p", video=video, dialogue=[], captions=[])


def test_frame_rounding_is_half_up() -> None:
    assert to_frames(0.5) == 12
    assert to_frames(1.99) == 48
    assert to_frames(0.02) == 0


def test_crossfade_is_clamped_to_half_the_shorter_shot() -> None:
    edl = _edl(1.0, 0.6, fade=0.5)
    assert edl.transition_frames(1) == 7
    assert edl.total_frames == 24 + 14 - 7


def test_hash_changes_with_content_and_round_trips(tmp_path: Path) -> None:
    edl = _edl(2.0, 2.0)
    path = tmp_path / "edl.json"
    save_edl(edl, path)
    assert load_edl(path) == edl
    assert edl_hash(edl) == edl_hash(load_edl(path))
    assert edl_hash(edl) != edl_hash(_edl(2.0, 2.5))


def test_defaults_have_no_music_and_no_end_card() -> None:
    edl = _edl(1.0)
    assert edl.music.tracks == [] and edl.end_card.enabled is False
    with pytest.raises(ValueError):
        Edl.model_validate({**edl.model_dump(), "nope": 1})
