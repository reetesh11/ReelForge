"""m6b AC-6 (emotion validation), AC-7 (age and band), AC-3 (display text), story and cast API."""

from __future__ import annotations

import json

import pytest
from m3_helpers import approved_project, cast_item, get_cast, new_world
from m6b_helpers import AGE_ERROR, UNKNOWN_JOY, base, set_age
from rf_helpers import create_project
from story_helpers import STORY_YAML, put, story_dict

BAD_MARKUP = "Emotion markup is not valid: close every <emotion> tag and do not nest them."


def _yaml(client, pid):
    import yaml

    return yaml.safe_load(client.get(f"{base(pid)}/story").json()["yaml_text"])


def _messages(r) -> list[str]:
    return [e["message"] for e in r.json()["errors"]]


# markup module ------------------------------------------------------------------


def test_emotions_and_check_emotion():
    from reelforge.story.markup import EMOTIONS, check_emotion

    assert EMOTIONS == ("happy", "sad", "fear", "anger")
    assert check_emotion(None) is None
    for e in EMOTIONS:
        assert check_emotion(e) == e
    for bad in ("joy", "Happy", "", "SAD"):
        with pytest.raises(ValueError) as ei:
            check_emotion(bad)
        assert str(ei.value) == f'Unknown emotion "{bad}". Use one of: happy, sad, fear, anger.'


def test_parse_segments_splits_in_order():
    from reelforge.story.markup import Segment, parse_segments

    assert parse_segments("Tum kahan ho? <sad>Mujhe akela chhod diya.</sad>") == [
        Segment("Tum kahan ho?", None),
        Segment("Mujhe akela chhod diya.", "sad"),
    ]
    assert parse_segments("<happy>Wah</happy> <fear>Arre</fear>") == [
        Segment("Wah", "happy"),
        Segment("Arre", "fear"),
    ]
    assert parse_segments("Sirf seedha vakya") == [Segment("Sirf seedha vakya", None)]
    kept = parse_segments("<sad>[sigh] haan</sad>")
    assert len(kept) == 1 and kept[0].emotion == "sad" and "[sigh]" in kept[0].text


def test_parse_segments_rejects_unknown_and_malformed():
    from reelforge.story.markup import parse_segments

    with pytest.raises(ValueError) as ei:
        parse_segments("<joy>hello</joy>")
    assert str(ei.value) == UNKNOWN_JOY
    for raw in ("<sad>never closed", "<sad>a <happy>b</happy> c</sad>", "<sad></sad>"):
        with pytest.raises(ValueError) as ei:
            parse_segments(raw)
        assert str(ei.value) == BAD_MARKUP, raw


def test_display_and_speech_text():
    from reelforge.story.markup import display_text, speech_text

    raw = "Tum kahan ho?   <sad>[sigh]  Mujhe akela chhod diya.</sad>"
    assert display_text(raw) == "Tum kahan ho? Mujhe akela chhod diya."
    sp = speech_text(raw)
    assert "<" not in sp and ">" not in sp and "[sigh]" in sp and "Mujhe akela chhod diya." in sp
    assert display_text("<happy>Wah</happy>") == "Wah"
    assert display_text("plain") == "plain"


# AC-6 story schema --------------------------------------------------------------


def _story_with(**scene_over):
    d = story_dict(3)
    d["scenes"][1].update(scene_over)
    return json.dumps(d)


def test_story_accepts_emotion_and_rejects_unknown(tmp_path):
    ctx, client, _ = new_world(tmp_path)
    with client:
        pid = create_project(client)["id"]
        ok = put(client, pid, _story_with(emotion="sad"))
        assert ok.status_code == 200, ok.text
        assert _yaml(client, pid)["scenes"][1]["emotion"] == "sad"
        saved = client.get(f"{base(pid)}/story").json()["yaml_text"]
        bad = put(client, pid, _story_with(emotion="joy"))
        assert bad.status_code == 422, bad.text
        assert any(UNKNOWN_JOY in m for m in _messages(bad))
        assert client.get(f"{base(pid)}/story").json()["yaml_text"] == saved


def test_story_rejects_bad_markup_in_line(tmp_path):
    ctx, client, _ = new_world(tmp_path)
    with client:
        pid = create_project(client)["id"]
        bad = put(client, pid, _story_with(line="<joy>Arre</joy> Aloo"))
        assert bad.status_code == 422 and any(UNKNOWN_JOY in m for m in _messages(bad))
        bad = put(client, pid, _story_with(line="<sad>Arre Aloo"))
        assert bad.status_code == 422 and any(BAD_MARKUP in m for m in _messages(bad))
        good = put(client, pid, _story_with(line="<sad>Arre</sad> Aloo [sigh]"))
        assert good.status_code == 200, good.text


def test_schema_models_have_emotion_and_age():
    from reelforge.story.schema import Character, Scene

    assert "emotion" in Scene.model_fields and "age" in Character.model_fields
    assert Scene.model_fields["emotion"].default is None
    assert Character.model_fields["age"].default is None


# AC-7 age -----------------------------------------------------------------------


def test_check_age_values():
    from reelforge.story.age import AGE_ERROR as MSG
    from reelforge.story.age import check_age

    assert MSG == AGE_ERROR
    assert check_age(None) is None
    assert check_age(1) == 1 and check_age(120) == 120 and check_age(67) == 67
    for bad in (0, 121, -5, 12.5, 30.0, "30", "x", True, False):
        with pytest.raises(ValueError) as ei:
            check_age(bad)
        assert str(ei.value) == AGE_ERROR, bad


def test_age_band_boundaries():
    from reelforge.story.age import age_band

    expect = {
        1: "child", 12: "child", 13: "teenager", 19: "teenager", 20: "young adult",
        39: "young adult", 40: "middle-aged", 59: "middle-aged", 60: "elderly", 120: "elderly",
    }
    for age, band in expect.items():
        assert age_band(age) == band, age


def test_story_character_age_valid_and_invalid(tmp_path):
    ctx, client, _ = new_world(tmp_path)
    with client:
        pid = create_project(client)["id"]
        d = story_dict(3)
        d["characters"]["tomato"]["age"] = 67
        assert put(client, pid, json.dumps(d)).status_code == 200
        assert _yaml(client, pid)["characters"]["tomato"]["age"] == 67
        saved = client.get(f"{base(pid)}/story").json()["yaml_text"]
        for bad in (0, 121, -1, 7.5, "old"):
            d["characters"]["tomato"]["age"] = bad
            r = put(client, pid, json.dumps(d))
            assert r.status_code == 422, (bad, r.text)
            assert any(AGE_ERROR in m for m in _messages(r)), bad
        assert client.get(f"{base(pid)}/story").json()["yaml_text"] == saved


def test_set_age_api_and_cast_listing(tmp_path):
    ctx, client, _ = new_world(tmp_path)
    with client:
        pid = approved_project(client)
        assert STORY_YAML  # approved project uses the sample story with tomato and potato
        assert "age" not in cast_item(client, pid, "tomato")
        r = set_age(client, pid, "tomato", 67)
        assert r.status_code == 200, r.text
        body = r.json()
        assert {"project_stage", "approved_count", "total", "character"} <= set(body)
        assert body["character"]["age"] == 67 and body["character"]["age_band"] == "elderly"
        item = cast_item(client, pid, "tomato")
        assert item["age"] == 67 and item["age_band"] == "elderly"
        assert "age" not in cast_item(client, pid, "potato")
        for age, band in ((12, "child"), (13, "teenager"), (19, "teenager"), (20, "young adult"),
                          (39, "young adult"), (40, "middle-aged"), (59, "middle-aged"), (60, "elderly")):
            r = set_age(client, pid, "tomato", age)
            assert r.status_code == 200, r.text
            assert r.json()["character"]["age_band"] == band, age
        r = set_age(client, pid, "tomato", None)
        assert r.status_code == 200 and "age" not in cast_item(client, pid, "tomato")


def test_set_age_rejects_invalid_and_saves_nothing(tmp_path):
    ctx, client, _ = new_world(tmp_path)
    with client:
        pid = approved_project(client)
        assert set_age(client, pid, "tomato", 30).status_code == 200
        for bad in (0, 121, -4, 12.5, "abc", True):
            r = set_age(client, pid, "tomato", bad)
            assert r.status_code == 422, (bad, r.text)
            assert r.json() == {"detail": AGE_ERROR}, bad
        assert cast_item(client, pid, "tomato")["age"] == 30
        assert get_cast(client, pid)["characters"]
        assert set_age(client, pid, "ghost", 30).status_code == 404
