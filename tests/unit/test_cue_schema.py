import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "acceptance"))

from story_helpers import story_dict  # noqa: E402

from reelforge.story.errors import StoryInvalid  # noqa: E402
from reelforge.story.yamlio import parse_story  # noqa: E402


def _story(audio, **over):
    return parse_story(json.dumps(story_dict(5, audio=audio, **over)))


def _cue(id_="c", **over):
    base = {"id": id_, "kind": "sfx", "start": {"scene": "s1"}, "duration": 1.0}
    base.update(over)
    return base


def _messages(audio):
    with pytest.raises(StoryInvalid) as ei:
        _story(audio)
    return [e.message for e in ei.value.errors]


def test_a_valid_cue_list_loads():
    assert [c.id for c in _story([_cue("a"), _cue("b")]).audio] == ["a", "b"]


def test_either_end_or_duration():
    both = _cue("g", end={"scene": "s2"})
    assert 'Cue "g": give either end or duration.' in _messages([both])
    neither = {"id": "g", "kind": "sfx", "start": {"scene": "s1"}}
    assert 'Cue "g": give either end or duration.' in _messages([neither])


def test_zero_length_cue_is_refused():
    zero = _cue(
        "z", duration=None, start={"scene": "s2", "offset": 1.0}, end={"scene": "s2", "offset": 1.0}
    )
    assert 'Cue "z": end (3.0 s) is not after start (3.0 s).' in _messages([zero])


def test_the_music_block_is_kept_next_to_audio():
    story = _story([_cue()], music={"mode": "library", "track": "t"})
    assert story.music is not None and story.audio is not None
