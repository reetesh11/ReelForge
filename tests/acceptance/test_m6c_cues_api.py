"""m6c R10 (API side), AC-8: the audio routes the Sound screen calls."""

from __future__ import annotations

import pytest
from m6c_helpers import (
    STD_CUES,
    at,
    audio_url,
    cue,
    cue_out,
    generated,
    get_audio,
    light_world,
    take_artifacts,
)


def test_get_audio_lists_cues_in_order_with_resolved_times_and_computed_state(tmp_path):
    cues = [*STD_CUES, cue("sug1", "sfx", at("s5", 0.5), duration=0.5, state="suggested")]
    with light_world(tmp_path, cues) as (ctx, client, pid):
        out = get_audio(client, pid)
        assert set(out["engine"]) == {"ok", "message"} and out["engine"]["ok"] is True
        assert out["settings"] == {"duck_db": 9.0, "attack_s": 0.15, "release_s": 0.4, "silence_fade_s": 0.08}
        assert "legacy_music_hint" not in out
        assert [c["id"] for c in out["cues"]] == ["m1", "fx1", "sil1", "f1", "amb1", "sug1"]
        assert [c["order"] for c in out["cues"]] == [1, 2, 3, 4, 5, 6]
        by = {c["id"]: c for c in out["cues"]}
        assert (by["m1"]["start_s"], by["m1"]["end_s"], by["m1"]["duration_s"]) == pytest.approx((0.0, 3.0, 3.0))
        assert (by["fx1"]["start_s"], by["fx1"]["end_s"]) == pytest.approx((2.5, 3.7))
        assert (by["amb1"]["start_s"], by["amb1"]["end_s"]) == pytest.approx((0.0, 10.0))
        assert by["m1"]["state"] == "draft" and by["sug1"]["state"] == "suggested"
        assert by["m1"]["source"] == "generate" and by["f1"]["source"] == "file"
        assert by["m1"]["takes"] == [] and by["m1"]["picked_take_id"] is None and by["m1"]["job"] is None
        assert by["m1"]["licence"] == "" and by["sil1"]["licence"] == ""
        assert "file_name" not in by["m1"] and "flags" not in by["m1"]


def test_a_generated_cue_shows_the_model_licence(tmp_path):
    with light_world(tmp_path, STD_CUES) as (ctx, client, pid):
        generated(client, ctx, pid, "fx1")
        (art,) = take_artifacts(ctx, pid, "fx1")
        assert cue_out(client, pid, "fx1")["licence"] == ctx.registry.get(art.model_key).license != ""


def test_a_cue_running_past_the_reel_end_is_flagged(tmp_path):
    cues = [cue("long", "sfx", at("s5", 1.0), duration=5.0)]
    with light_world(tmp_path, cues) as (_, client, pid):
        assert cue_out(client, pid, "long")["flags"] == ["ends_after_reel"]


def test_add_edit_delete_a_cue(tmp_path):
    with light_world(tmp_path, [cue("a", "sfx", at("s1"), duration=1.0)]) as (ctx, client, pid):
        new = cue("b", "ambience", at("s2"), duration=2.0, prompt="crowd")
        r = client.post(audio_url(pid, "/cues"), json=new)
        assert r.status_code == 201, r.text
        assert [c["id"] for c in r.json()["cues"]] == ["a", "b"]
        r = client.put(audio_url(pid, "/cues/b"), json={**new, "prompt": "louder crowd", "gain_db": -9.0})
        assert r.status_code == 200
        b = cue_out(client, pid, "b")
        assert b["prompt"] == "louder crowd" and b["gain_db"] == -9.0
        assert client.put(audio_url(pid, "/cues/nope"), json=new).status_code == 404
        r = client.delete(audio_url(pid, "/cues/a"))
        assert r.status_code == 200 and [c["id"] for c in r.json()["cues"]] == ["b"]


def test_adding_a_bad_cue_is_a_422_naming_the_cue(tmp_path):
    with light_world(tmp_path, [cue("a", "sfx", at("s1"), duration=1.0)]) as (_, client, pid):
        r = client.post(audio_url(pid, "/cues"), json=cue("gong1", "boom", at("s1"), duration=1.0))
        assert r.status_code == 422, r.text
        body = r.json()
        assert body["detail"] == "story.yaml is invalid"
        assert any(
            e["message"] == 'Cue "gong1": unknown kind "boom"; use music, sfx, ambience or silence.'
            for e in body["errors"]
        )
        assert [c["id"] for c in get_audio(client, pid)["cues"]] == ["a"]


def test_move_a_cue_up_and_down(tmp_path):
    cues = [cue(i, "sfx", at("s1"), duration=1.0) for i in ("a", "b", "c")]
    with light_world(tmp_path, cues) as (_, client, pid):
        r = client.post(audio_url(pid, "/cues/c:move"), json={"direction": "up"})
        assert r.status_code == 200 and [c["id"] for c in r.json()["cues"]] == ["a", "c", "b"]
        r = client.post(audio_url(pid, "/cues/a:move"), json={"direction": "down"})
        assert [c["id"] for c in r.json()["cues"]] == ["c", "a", "b"]
        assert [c["order"] for c in r.json()["cues"]] == [1, 2, 3]


def test_pick_an_earlier_take(tmp_path):
    with light_world(tmp_path, STD_CUES) as (ctx, client, pid):
        generated(client, ctx, pid, "fx1")
        generated(client, ctx, pid, "fx1")
        t1, t2 = cue_out(client, pid, "fx1")["takes"]
        r = client.post(audio_url(pid, "/cues/fx1:select-take"), json={"take_id": t1["id"]})
        assert r.status_code == 200
        out = next(c for c in r.json()["cues"] if c["id"] == "fx1")
        assert out["picked_take_id"] == t1["id"]
        assert [t["picked"] for t in out["takes"]] == [True, False]
        generated(client, ctx, pid, "m1")
        m1_take = cue_out(client, pid, "m1")["takes"][0]
        r = client.post(audio_url(pid, "/cues/fx1:select-take"), json={"take_id": m1_take["id"]})
        assert r.status_code == 404


def test_mix_settings_read_and_update(tmp_path):
    with light_world(tmp_path, STD_CUES) as (_, client, pid):
        r = client.get(audio_url(pid, "/settings"))
        assert r.status_code == 200
        assert r.json() == {"duck_db": 9.0, "attack_s": 0.15, "release_s": 0.4, "silence_fade_s": 0.08}
        r = client.put(audio_url(pid, "/settings"), json={"duck_db": 12.0})
        assert r.status_code == 200
        assert r.json() == {"duck_db": 12.0, "attack_s": 0.15, "release_s": 0.4, "silence_fade_s": 0.08}
        assert get_audio(client, pid)["settings"]["duck_db"] == 12.0
        for bad in ({"duck_db": 41}, {"duck_db": -1}, {"attack_s": -0.1}, {"silence_fade_s": -1}):
            assert client.put(audio_url(pid, "/settings"), json=bad).status_code == 422
        assert client.get(audio_url(pid, "/settings")).json()["duck_db"] == 12.0


def test_audio_state_module_exposes_the_documented_constants_and_settings(tmp_path):
    from reelforge.audio.state import (
        AUDIO_JOB,
        DEFAULT_MIX,
        NEEDS_APPROVAL,
        NOT_AUDIO,
        AudioError,
        get_mix_settings,
        put_mix_settings,
    )

    assert AUDIO_JOB == "gen_audio_cue"
    assert NEEDS_APPROVAL == "Approve this cue before generating it."
    assert NOT_AUDIO == "That file is not an audio clip."
    assert DEFAULT_MIX == {"duck_db": 9.0, "attack_s": 0.15, "release_s": 0.4, "silence_fade_s": 0.08}
    assert issubclass(AudioError, Exception)
    with light_world(tmp_path, STD_CUES) as (ctx, _, pid):
        assert get_mix_settings(ctx, pid) == DEFAULT_MIX
        assert put_mix_settings(ctx, pid, duck_db=6.0)["duck_db"] == 6.0
        assert get_mix_settings(ctx, pid)["duck_db"] == 6.0

