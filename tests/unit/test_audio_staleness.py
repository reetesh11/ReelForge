import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "acceptance"))

from story_helpers import story_dict  # noqa: E402  # pyright: ignore[reportMissingImports]

from reelforge.story.staleness import diff_stories  # noqa: E402
from reelforge.story.yamlio import parse_story  # noqa: E402


def _cue(id_, **over):
    base = {"id": id_, "kind": "sfx", "start": {"scene": "s2"}, "duration": 1.0, "prompt": "gong"}
    base.update(over)
    return base


def _story(cues, **over):
    return parse_story(json.dumps(story_dict(5, audio=cues, **over)))


def _cue_changes(old, new):
    return [(a.owner_id, a.kinds) for a in diff_stories(old, new) if a.owner_type == "audio_cue"]


def test_take_and_mix_edits_give_different_kinds():
    old = _story([_cue("a"), _cue("b")])
    new = _story([_cue("a", prompt="bigger"), _cue("b", gain_db=-3.0, duck=True)])
    assert _cue_changes(old, new) == [("a", ["audio_take"]), ("b", ["audio_mix"])]


def test_unchanged_and_state_only_edits_write_nothing():
    old = _story([_cue("a", state="suggested")])
    assert _cue_changes(old, _story([_cue("a")])) == []


def test_added_and_removed_cues_are_star():
    old = _story([_cue("a")])
    new = _story([_cue("b")])
    assert sorted(_cue_changes(old, new)) == [("a", ["*"]), ("b", ["*"])]


def test_a_scene_length_change_only_hits_cues_whose_length_changes():
    cues = [
        _cue("a"),
        _cue("amb", kind="ambience", duration=None, end={"scene": "s5", "at": "scene_end"}),
    ]
    old = _story(cues)
    d = story_dict(5, audio=cues)
    d["scenes"][4]["duration"] = 3.0
    new = parse_story(json.dumps(d))
    assert _cue_changes(old, new) == [("amb", ["audio_take"])]


def test_music_note_is_ignored_when_audio_exists():
    music = {"mode": "library", "track": "a"}
    old = _story([_cue("a")], music=music)
    new = _story([_cue("a")], music={"mode": "library", "track": "b"})
    assert diff_stories(old, new) == []
