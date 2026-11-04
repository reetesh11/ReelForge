import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "acceptance"))

from story_helpers import story_dict  # noqa: E402

from reelforge.audio.seed import merge_suggestions, suggest_cues  # noqa: E402
from reelforge.story.yamlio import parse_story  # noqa: E402


def _story():
    d = story_dict(5)
    d["scenes"][2]["action"] = "Aloo proudly lifts the sweet box"
    return parse_story(json.dumps(d))


def test_a_sentence_ties_to_the_scene_sharing_most_words():
    (cue,) = [c for c in suggest_cues("A gong slam as Aloo lifts the sweet box.", _story())]
    assert cue.kind == "sfx" and cue.start.scene == "s3" and cue.prompt == "gong slam"


def test_music_and_ambience_cover_to_the_end_of_the_reel():
    cues = suggest_cues("TRACK 3 kicks in. Wedding hall ambience.", _story())
    assert {c.kind for c in cues} == {"music", "ambience"}
    assert all(c.end is not None and c.end.scene == "s5" and c.end.at == "scene_end" for c in cues)
    assert all(c.start.scene == "s1" for c in cues)


def test_silence_has_a_duration_and_no_prompt():
    (cue,) = suggest_cues("Complete silence.", _story())
    assert cue.kind == "silence" and cue.duration == 1.0 and cue.prompt is None


def test_merge_twice_is_the_same_as_once():
    new = suggest_cues("A gong slam. A drum roll. Silence.", _story())
    once = merge_suggestions([], new)
    assert merge_suggestions(once, new) == once and len(once) == 3
