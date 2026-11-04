"""m6b AC-9 (stale only what changed), AC-3 (no markup or [..] tags on screen or in captions)."""

from __future__ import annotations

import json
import re

from m4_helpers import rendered_project
from m5_helpers import frames_approved, shots_approved, story_text, voices_approved, world
from m6_helpers import build, get_edl
from m6b_helpers import (
    LINES,
    UNKNOWN_JOY,
    action,
    approve_all,
    emo_world,
    get_voices,
    line_of,
    set_age,
    set_emotion,
    take_rows,
)

IDS = list(LINES)
TAG = re.compile(r"</?(happy|sad|fear|anger)>|\[[^\]]*\]")


# AC-9 ---------------------------------------------------------------------------


def _states(client, pid):
    v = get_voices(client, pid)
    return v, {x["scene_id"]: x for x in v["lines"]}


def test_emotion_change_stales_only_that_line_and_starts_no_job(tmp_path):
    ctx, client, _ = emo_world(tmp_path)
    with client:
        pid = rendered_project(client, ctx)
        approve_all(client, pid)
        jobs = len(client.get("/api/v1/jobs").json())
        r = set_emotion(client, pid, "s2", "sad")
        assert r.status_code == 200, r.text
        assert r.json()["line"]["emotion"] == "sad"
        v, by = _states(client, pid)
        assert v["stale_count"] == 1 and by["s2"]["state"] == "stale"
        assert by["s2"]["takes"][0]["stale"] is True and by["s2"]["shot_length_stale"] is True
        for s in IDS:
            if s != "s2":
                assert by[s]["state"] == "approved", s
                assert by[s]["shot_length_stale"] is False and all(t["stale"] is False for t in by[s]["takes"])
        assert len(client.get("/api/v1/jobs").json()) == jobs  # nothing regenerates
        # clearing an emotion that was never set changes nothing
        assert set_emotion(client, pid, "s4", None).status_code == 200
        assert _states(client, pid)[0]["stale_count"] == 1


def test_age_change_stales_only_that_characters_takes(tmp_path):
    ctx, client, _ = emo_world(tmp_path)
    with client:
        pid = rendered_project(client, ctx)
        approve_all(client, pid)
        jobs = len(client.get("/api/v1/jobs").json())
        assert set_age(client, pid, "tomato", 67).status_code == 200
        v, by = _states(client, pid)
        for s in ("s1", "s3", "s5"):  # tomato speaks the odd scenes
            assert by[s]["takes"][0]["stale"] is True and by[s]["shot_length_stale"] is True, s
        for s in ("s2", "s4"):
            assert by[s]["state"] == "approved" and by[s]["takes"][0]["stale"] is False, s
            assert by[s]["shot_length_stale"] is False
        assert len(client.get("/api/v1/jobs").json()) == jobs
        assert set_age(client, pid, "tomato", 67).status_code == 200  # same age: no change
        assert _states(client, pid)[0]["stale_count"] == 3
        assert [len(take_rows(ctx, pid, s)) for s in IDS] == [1] * 5


def test_set_emotion_unknown_value_and_unknown_line(tmp_path):
    ctx, client, _ = emo_world(tmp_path)
    with client:
        pid = rendered_project(client, ctx)
        r = set_emotion(client, pid, "s2", "joy")
        assert r.status_code == 422 and r.json() == {"detail": UNKNOWN_JOY}
        assert "emotion" not in line_of(client, pid, "s2")
        assert line_of(client, pid, "s2")["takes"][0]["stale"] is False
        assert set_emotion(client, pid, "s99", "sad").status_code == 404


# AC-3 ---------------------------------------------------------------------------


def test_voice_card_text_is_clean_and_edit_box_keeps_markup(tmp_path):
    ctx, client, _ = emo_world(tmp_path)
    with client:
        pid = rendered_project(client, ctx)
        raw = "Tum kahan ho? <sad>[sigh] Mujhe akela chhod diya.</sad>"
        r = action(client, pid, "s2", "edit-text", text=raw)
        assert r.status_code == 200, r.text
        ln = line_of(client, pid, "s2")
        assert ln["text"] == "Tum kahan ho? Mujhe akela chhod diya."
        assert ln["edit_text"] == raw
        assert r.json()["line"]["text"] == ln["text"]
        for s in IDS:
            if s != "s2":
                assert "edit_text" not in line_of(client, pid, s)
        r = action(client, pid, "s2", "edit-text", text="<sad>[sigh]</sad>")
        assert r.status_code == 422 and r.json() == {"detail": "The line can't be empty."}
        r = action(client, pid, "s2", "edit-text", text="<joy>Arre</joy> yaar")
        assert r.status_code == 422 and r.json() == {"detail": UNKNOWN_JOY}
        assert line_of(client, pid, "s2")["edit_text"] == raw


def test_captions_in_the_edl_have_no_markup_or_tags(tmp_path):
    d = json.loads(story_text())
    d["scenes"][0]["line"] = "<sad>Arre Aloo itni der kyun aaye ho aaj</sad>"
    d["scenes"][1]["line"] = "[sigh] Mithai ke bina shaadi nahi hoti yaar"
    d["scenes"][4]["line"] = "Chalo ab <happy>sab milkar</happy> thekua khaate hain"
    w = world(tmp_path)
    with w.client:
        pid = voices_approved(w, json.dumps(d, ensure_ascii=False))
        frames_approved(w, pid)
        shots_approved(w, pid)
        build(w, pid)
        caps = get_edl(w, pid)["captions"]
        text = " ".join(" ".join(c["text"].split()) for c in caps)
        assert caps and not TAG.search(text), text
        assert "Arre Aloo itni der kyun aaye ho aaj" in text and "Mithai ke bina shaadi nahi hoti yaar" in text
        assert "Chalo ab sab milkar thekua khaate hain" in text
