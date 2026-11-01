"""Story schema: valid example, invalid-value rules, all errors at once, wording."""

from __future__ import annotations

import pytest
import yaml_samples as ys

from reelforge.story.errors import StoryInvalid
from reelforge.story.yamlio import parse_story


def _errors(text: str) -> set[str]:
    with pytest.raises(StoryInvalid) as ei:
        parse_story(text)
    return {str(e) for e in ei.value.errors}


def test_valid_example_parses() -> None:
    story = parse_story(ys.STORY)
    assert story.title == "Wedding"
    assert story.target_seconds == 12 and story.aspect == "9:16"


def test_all_errors_reported_together() -> None:
    errs = _errors(ys.STORY.replace("fps: 24", 'fps: "x"') + "foo: 1\nbar: 2\n")
    assert {"foo: unknown field", "bar: unknown field", "fps: must be an integer"} <= errs


def test_missing_required_fields() -> None:
    errs = _errors("version: 1\n")
    assert {"title: field required", "language: field required", "scenes: field required"} <= errs


def test_cross_field_paths() -> None:
    errs = _errors(
        ys.STORY.replace("speaker: tomato", "speaker: ghost").replace("id: s2", "id: s1")
    )
    assert "scenes[1].id: duplicate scene id s1" in errs
    assert any(e.startswith("scenes[1].speaker:") for e in errs)


def test_continue_from_unknown_scene() -> None:
    errs = _errors(ys.STORY.replace("id: s2\n", "id: s2\n    continue_from: s9\n"))
    assert any(e.startswith("scenes[1].continue_from:") for e in errs)


@pytest.mark.parametrize(
    ("old", "new", "path"),
    [
        ("target_seconds: 12", "target_seconds: 61", "target_seconds"),
        ("fps: 24", "fps: 0", "fps"),
        ('aspect: "9:16"', 'aspect: "wide"', "aspect"),
        ("language: english", "language: klingon", "language"),
        ("tomato:", "Tomato:", "characters.Tomato"),
    ],
)
def test_invalid_values_name_field(old: str, new: str, path: str) -> None:
    assert any(e.startswith(path) for e in _errors(ys.STORY.replace(old, new, 1)))
