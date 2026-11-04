"""Emotion and age edits through the API: what is saved, what is left alone."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "acceptance"))

from m6b_helpers import (  # noqa: E402  # pyright: ignore[reportMissingImports]
    action,
    base,
    emo_world,
    gen_lines,
    get_voices,
    line_of,
    project_with_presets,
    set_age,
    set_emotion,
    take_rows,
    voice_world,
)


def _versions(client, pid):
    return len(client.get(f"{base(pid)}/story/versions").json())


def test_same_emotion_saves_no_new_story_version_and_clearing_removes_the_key(tmp_path):
    ctx, client, _ = emo_world(tmp_path)
    with client:
        pid = project_with_presets(client, ctx)
        assert set_emotion(client, pid, "s2", "sad").status_code == 200
        n = _versions(client, pid)
        assert set_emotion(client, pid, "s2", "sad").status_code == 200
        assert _versions(client, pid) == n
        assert set_emotion(client, pid, "s2", None).status_code == 200
        assert "emotion" not in line_of(client, pid, "s2")
        assert "emotion:" not in client.get(f"{base(pid)}/story").json()["yaml_text"]


def test_invalid_markup_is_rejected_and_the_line_is_unchanged(tmp_path):
    ctx, client, _ = emo_world(tmp_path)
    with client:
        pid = project_with_presets(client, ctx)
        before = line_of(client, pid, "s2")["text"]
        n = _versions(client, pid)
        r = action(client, pid, "s2", "edit-text", text="<sad>never closed")
        assert r.status_code == 422 and "close every <emotion> tag" in r.json()["detail"]
        assert line_of(client, pid, "s2")["text"] == before and _versions(client, pid) == n


def test_age_can_be_cleared_and_its_band_listed_on_the_voice_board(tmp_path):
    ctx, client, _ = emo_world(tmp_path)
    with client:
        pid = project_with_presets(client, ctx)
        assert set_age(client, pid, "tomato", 8).status_code == 200
        tomato = next(c for c in get_voices(client, pid)["characters"] if c["key"] == "tomato")
        assert tomato["age"] == 8 and tomato["age_band"] == "child"
        assert set_age(client, pid, "tomato", None).status_code == 200
        tomato = next(c for c in get_voices(client, pid)["characters"] if c["key"] == "tomato")
        assert "age" not in tomato


def test_kokoro_age_is_recorded_and_lengths_stay_plain(tmp_path):
    ctx, client = voice_world(tmp_path)  # the packaged mapping, with its experimental Kokoro shift
    with client:
        pid = project_with_presets(client, ctx)
        client.put("/api/v1/voice-model", json={"voice_model": "kokoro"})
        for key, vid in (("tomato", "hm_omega"), ("potato", "hf_alpha")):
            client.post(
                f"{base(pid)}/voices/characters/{key}:set", json={"mode": "preset", "voice_id": vid}
            )
        assert set_age(client, pid, "tomato", 70).status_code == 200
        gen_lines(client, ctx, pid, "s1")
        params = take_rows(ctx, pid, "s1")[0].params
        assert params["age_band"] == "elderly" and "phrases" not in params
        assert line_of(client, pid, "s1")["effective"]["age_band"] == "elderly"
        assert line_of(client, pid, "s1")["takes"][0]["stale"] is False
