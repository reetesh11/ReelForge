"""story.yaml round-trip and safe loading."""

from __future__ import annotations

import pytest
import yaml_samples as ys

from reelforge.story.errors import StoryInvalid
from reelforge.story.yamlio import dump_story_text, load_story_text, parse_story, story_to_yaml


def test_roundtrip_string_equal() -> None:
    assert dump_story_text(load_story_text(ys.STORY)) == ys.STORY


def test_quoting_and_comments_survive_edit() -> None:
    doc = load_story_text(ys.STORY)
    doc["fps"] = 30
    out = dump_story_text(doc)
    assert "fps: 30" in out and "# a tale" in out and '"Tamatar"   # grumpy' in out


def test_story_to_yaml_roundtrip() -> None:
    story = parse_story(ys.STORY)
    assert parse_story(story_to_yaml(story)) == story


def test_unsafe_tag_rejected() -> None:
    with pytest.raises(StoryInvalid) as ei:
        load_story_text("title: !!python/object:os.system {}\nversion: 1\n")
    assert [e.message for e in ei.value.errors] == ["unsafe or unsupported YAML tag"]


def test_duplicate_key() -> None:
    with pytest.raises(StoryInvalid) as ei:
        load_story_text("a: 1\na: 2\n")
    assert ei.value.errors[0].line is not None


def test_syntax_error_has_line_and_column() -> None:
    with pytest.raises(StoryInvalid) as ei:
        load_story_text("a: 1\nb: [oops\nc: 2\n")
    e = ei.value.errors[0]
    assert e.line and e.column


@pytest.mark.parametrize("text", ["", "  \n", "# only a comment\n"])
def test_empty(text: str) -> None:
    with pytest.raises(StoryInvalid) as ei:
        load_story_text(text)
    assert ei.value.errors[0].message == "story.yaml is empty"


def test_non_mapping_root() -> None:
    with pytest.raises(StoryInvalid):
        load_story_text("- a\n- b\n")
