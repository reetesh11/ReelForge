"""AC-3 and AC-10 at the module level: round-trip, safe loading, JSON Schema; AC-2 messages."""

from __future__ import annotations

import pytest
from story_helpers import STORY_YAML


def test_roundtrip_preserves_comments_and_order():
    from reelforge.story.yamlio import dump_story_text, load_story_text

    assert dump_story_text(load_story_text(STORY_YAML)) == STORY_YAML


def test_parse_story_valid_and_story_to_yaml_roundtrips():
    from reelforge.story.yamlio import parse_story, story_to_yaml

    story = parse_story(STORY_YAML)
    assert [s.id for s in story.scenes] == ["s1", "s2", "s3", "s4", "s5"]
    assert parse_story(story_to_yaml(story)) == story


def test_unknown_field_and_invalid_value_all_reported_with_paths():
    from reelforge.story.errors import StoryInvalid
    from reelforge.story.yamlio import parse_story

    text = STORY_YAML.replace("fps: 24", 'fps: "abc"') + "foo: 1\n"
    with pytest.raises(StoryInvalid) as ei:
        parse_story(text)
    rendered = {str(e) for e in ei.value.errors}
    assert "foo: unknown field" in rendered
    assert "fps: must be an integer" in rendered


def test_nested_unknown_field_path():
    from reelforge.story.errors import StoryInvalid
    from reelforge.story.yamlio import parse_story

    text = STORY_YAML.replace("  - id: s3\n", "  - id: s3\n    fps: 30\n")
    with pytest.raises(StoryInvalid) as ei:
        parse_story(text)
    assert "scenes[2].fps: unknown field" in {str(e) for e in ei.value.errors}


@pytest.mark.parametrize(
    "old,new,path",
    [
        ("language: hinglish ", "language: klingon ", "language"),
        ("speaker: tomato", "speaker: ghost", "scenes[1].speaker"),
        ("continue_from: s3", "continue_from: s9", "scenes[3].continue_from"),
        ("  - id: s5\n", "  - id: s4\n", "scenes"),
        ("target_seconds: 12", "target_seconds: 61", "target_seconds"),
        ("fps: 24", "fps: 0", "fps"),
        ('aspect: "9:16"', 'aspect: "wide"', "aspect"),
    ],
)
def test_invalid_values_name_the_field(old, new, path):
    from reelforge.story.errors import StoryInvalid
    from reelforge.story.yamlio import parse_story

    assert old in STORY_YAML
    with pytest.raises(StoryInvalid) as ei:
        parse_story(STORY_YAML.replace(old, new, 1))
    assert any(e.path.startswith(path) for e in ei.value.errors), [str(e) for e in ei.value.errors]


def test_unsafe_tag_rejected():
    from reelforge.story.errors import StoryInvalid
    from reelforge.story.yamlio import load_story_text

    text = "version: 1\ntitle: !!python/object/apply:os.system [echo hi]\n" + STORY_YAML.split("\n", 3)[3]
    with pytest.raises(StoryInvalid) as ei:
        load_story_text(text)
    assert [e.message for e in ei.value.errors] == ["unsafe or unsupported YAML tag"]


def test_empty_and_syntax_errors():
    from reelforge.story.errors import StoryInvalid
    from reelforge.story.yamlio import load_story_text

    with pytest.raises(StoryInvalid) as ei:
        load_story_text("   \n")
    assert ei.value.errors[0].message == "story.yaml is empty"
    with pytest.raises(StoryInvalid) as ei2:
        load_story_text("title: [unclosed\nfps: 1\n")
    e = ei2.value.errors[0]
    assert e.line is not None and e.line >= 1 and e.column is not None and e.column >= 1


def test_json_schema_matches_story_model():
    from reelforge.story.schema import Story, story_json_schema

    schema = story_json_schema()
    assert schema == Story.model_json_schema()
    assert "scenes" in schema["properties"] and schema.get("additionalProperties") is False
