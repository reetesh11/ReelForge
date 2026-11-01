"""structure_story helpers: path removal, evaluation rules, prompt building."""

from __future__ import annotations

import json

from reelforge.adapters.mock_llm import canned_story
from reelforge.api.schemas import StoryAnswer, StructureRequest
from reelforge.story.structure import build_messages, evaluate, remove_path, response_schema


def _req(**over) -> StructureRequest:
    return StructureRequest(storyline="a tale", **over)


def _reply(story, questions=None) -> str:
    return json.dumps({"story": story, "questions": questions or []})


def test_remove_path():
    data = {
        "scenes": [{"id": "s1"}, {"id": "s2", "setting": "x"}],
        "characters": {"a": {"look": "l"}},
    }
    remove_path(data, "scenes[1].setting")
    remove_path(data, "characters.a.look")
    remove_path(data, "scenes[9].setting")
    assert data == {"scenes": [{"id": "s1"}, {"id": "s2"}], "characters": {"a": {}}}


def test_evaluate_valid_sets_suggested_without_dialogue():
    out = evaluate(_reply(canned_story()), _req())
    assert out.errors == [] and out.story is not None
    assert [s.suggested for s in out.story.scenes] == [None, True, True, None, None]


def test_evaluate_scene_count_and_duration_rules():
    story = canned_story()
    story["scenes"] = story["scenes"][:3]
    assert "got 3" in evaluate(_reply(story), _req()).errors[0]
    story = canned_story()
    assert "over the 5 s target" in evaluate(_reply(story), _req(target_seconds=5)).errors[0]


def test_evaluate_not_json_and_questions_only():
    assert evaluate("nope", _req()).errors == ["response: not valid JSON"]
    q = [{"path": "scenes[0].setting", "question": "where?"}]
    out = evaluate(_reply(None, q), _req())
    assert out.questions == q and out.draft_yaml is None and out.story is None


def test_messages_include_answers_and_schema_has_defs():
    req = _req(answers=[StoryAnswer(path="p", question="q", answer="purple cave")])
    assert "purple cave" in build_messages(req)[1]["content"]
    assert "$defs" in response_schema()
