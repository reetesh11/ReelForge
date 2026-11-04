import json

import pytest
import yaml_samples as ys

from reelforge.adapters.mock_llm import canned_story
from reelforge.api.schemas import StructureRequest
from reelforge.story.errors import StoryInvalid
from reelforge.story.staleness import LINE_KINDS, diff_stories
from reelforge.story.structure import evaluate
from reelforge.story.yamlio import parse_story


def _with_emotion(emotion):
    return ys.STORY.replace("id: s2\n", f"id: s2\n    emotion: {emotion}\n")


def test_scene_emotion_loads_and_unknown_is_rejected():
    assert parse_story(_with_emotion("sad")).scenes[1].emotion == "sad"
    with pytest.raises(StoryInvalid) as ei:
        parse_story(_with_emotion("joy"))
    assert 'Unknown emotion "joy"' in str(ei.value.errors[0])


def test_character_age_loads_and_bad_is_rejected():
    text = ys.STORY.replace('    name: "Tamatar"', '    age: 67\n    name: "Tamatar"')
    assert parse_story(text).characters["tomato"].age == 67
    with pytest.raises(StoryInvalid) as ei:
        parse_story(text.replace("age: 67", "age: 0"))
    assert "Age must be a whole number from 1 to 120." in str(ei.value.errors[0])


def test_line_markup_validated():
    with pytest.raises(StoryInvalid):
        parse_story(ys.STORY.replace('line: "Hello"', 'line: "<sad>Hello"'))
    assert parse_story(ys.STORY.replace('line: "Hello"', 'line: "<sad>Hello</sad>"'))


def test_emotion_change_is_a_line_change():
    old = parse_story(ys.STORY)
    new = parse_story(_with_emotion("sad"))
    affected = diff_stories(old, new)
    assert [(a.owner_id, a.kinds) for a in affected] == [("s2", LINE_KINDS)]


def test_structuring_drops_a_bad_proposed_age_and_keeps_a_good_one():
    story = canned_story()
    keys = list(story["characters"])
    story["characters"][keys[0]]["age"] = 200
    story["characters"][keys[1]]["age"] = 40
    out = evaluate(json.dumps({"story": story, "questions": []}), StructureRequest(storyline="t"))
    assert out.errors == [] and out.story is not None
    assert out.story.characters[keys[0]].age is None and out.story.characters[keys[1]].age == 40
