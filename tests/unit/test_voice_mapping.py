from pathlib import Path

import pytest

from reelforge.config import Settings
from reelforge.voice.mapping import PACKAGED_MAPPING, MappingError, load_mapping

BASE = """\
[phrase]
gap_ms = 200
{emotions}
"""


def _emotion(name, scale=1.0, pitch="", tags="[]"):
    return f'[emotion.{name}]\ntags = {tags}\npitch = "{pitch}"\nduration_scale = {scale}\n'


def _write(tmp_path, names=("happy", "sad", "fear", "anger"), **kw) -> Path:
    p = tmp_path / "m.toml"
    p.write_text(BASE.format(emotions="\n".join(_emotion(n, **kw) for n in names)))
    return p


def test_default_setting_points_at_the_packaged_table():
    assert Settings().emotion_mapping_path == PACKAGED_MAPPING and PACKAGED_MAPPING.is_file()


def test_packaged_table_loads_every_emotion():
    m = load_mapping(PACKAGED_MAPPING)
    for name in ("happy", "sad", "fear", "anger"):
        assert m.rule(name) is not None
    assert m.kokoro_age("elderly") is not None and m.kokoro_age("young adult") is None


def test_defaults_for_optional_values(tmp_path):
    m = load_mapping(_write(tmp_path))
    rule = m.rule("sad")
    assert (
        rule and rule.generation == {} and rule.post.tempo == 1.0 and rule.tag_position == "prefix"
    )
    assert m.phrase_gap_ms == 200


def test_missing_emotion_table_is_an_error(tmp_path):
    with pytest.raises(MappingError, match=r"has no \[emotion.anger\] table"):
        load_mapping(_write(tmp_path, names=("happy", "sad", "fear")))


def test_missing_file_and_bad_values(tmp_path):
    with pytest.raises(MappingError):
        load_mapping(tmp_path / "nope.toml")
    bad = tmp_path / "bad.toml"
    bad.write_text("[emotion")
    with pytest.raises(MappingError, match="not valid TOML"):
        load_mapping(bad)
    with pytest.raises(MappingError, match="duration_scale must be a number"):
        load_mapping(_write(tmp_path, scale='"fast"'))


def test_file_is_read_again_on_every_load(tmp_path):
    p = _write(tmp_path, scale=1.0)
    assert (load_mapping(p).rule("sad") or pytest.fail()).duration_scale == 1.0
    _write(tmp_path, scale=2.0)
    assert (load_mapping(p).rule("sad") or pytest.fail()).duration_scale == 2.0
