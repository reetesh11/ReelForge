"""m6c R4, R5, R9, R14, AC-2, AC-3, AC-7, AC-9, AC-15: cue generation, own files, staleness."""

from __future__ import annotations

import json
import time

import pytest
from m4_helpers import read_wav, wav_bytes, wav_seconds
from m6c_helpers import (
    STD_CUES,
    at,
    audio_url,
    cue,
    cue_out,
    generate_cue,
    generated,
    get_audio,
    jobs_of_type,
    light_world,
    put_cue,
    stale_audio,
    story_with_audio,
    take_artifacts,
    take_path,
    upload_cue_file,
)
from m6b_helpers import tone_freq
from rf_helpers import run_async
from story_helpers import put

NOT_AUDIO = "That file is not an audio clip."
NEEDS_APPROVAL = "Approve this cue before generating it."


# mock adapter ---------------------------------------------------------------------------


def _run_mock(tmp_path, kind, seconds):
    from reelforge.adapters.base import CancelToken, TaskSpec
    from reelforge.adapters.mock import MockAdapter
    from reelforge.models_registry import ModelEntry, ModelRegistry

    entry = ModelEntry(key="audio_x", id="test-org/audio-x", revision="r1", license="MIT")
    adapter = MockAdapter(ModelRegistry([entry]), default_timeout_s=30.0, sample_interval_s=0.1)
    params = {"duration_s": seconds}
    if kind:
        params["audio_kind"] = kind
    task = TaskSpec(kind="audio", prompt="p", seed=3, params=params, model=entry)
    out = tmp_path / f"o_{kind}"
    out.mkdir()
    files = run_async(adapter.run(task, out, lambda pct, msg: None, CancelToken()))
    return files[0].path


@pytest.mark.parametrize("kind, hz", [("music", 220.0), ("sfx", 880.0), ("ambience", 330.0)])
def test_mock_audio_is_a_tone_of_the_requested_length_and_kind(tmp_path, kind, hz):
    path = _run_mock(tmp_path, kind, 2.5)
    samples, rate, _, _ = read_wav(path)
    assert len(samples) / rate == pytest.approx(2.5, abs=0.02)
    assert tone_freq(samples, rate) == pytest.approx(hz, rel=0.03)


# generating takes -----------------------------------------------------------------------


def test_generating_a_music_and_an_sfx_cue_gives_takes_of_the_cue_length(tmp_path):
    with light_world(tmp_path, STD_CUES) as (ctx, client, pid):
        body, job = generated(client, ctx, pid, "m1")
        assert body["type"] == "gen_audio_cue" and body["payload"] == {"cue_id": "m1", "stage": "sound"}
        assert body["heavy"] is False
        generated(client, ctx, pid, "fx1")
        for cid, length, prompt in (("m1", 3.0, "festive shehnai and dholak"), ("fx1", 1.2, "gong slam")):
            (art,) = take_artifacts(ctx, pid, cid)
            assert art.owner_type == "audio_cue" and art.kind == "audio_take" and art.take_no == 1
            assert art.prompt == prompt and isinstance(art.seed, int) and art.model_key
            assert art.duration_s == pytest.approx(length, abs=0.05)
            assert art.params.get("model_id")
            assert wav_seconds(take_path(ctx, art)) == pytest.approx(length, abs=0.05)
        out = cue_out(client, pid, "m1")
        assert out["state"] == "ready" and out["duration_s"] == pytest.approx(3.0)
        (t,) = out["takes"]
        assert out["picked_take_id"] == t["id"] and t["picked"] is True and t["take_no"] == 1
        assert t["prompt"] == "festive shehnai and dholak" and t["model"]
        assert t["duration_s"] == pytest.approx(3.0, abs=0.05) and t["url"].startswith("/media/")
        assert isinstance(t["seed"], int) and t["stale"] is False


def test_the_job_result_names_the_new_take(tmp_path):
    with light_world(tmp_path, STD_CUES) as (ctx, client, pid):
        body, job = generated(client, ctx, pid, "fx1")
        res = ctx.queue.get(body["id"]).result
        (art,) = take_artifacts(ctx, pid, "fx1")
        assert res["cue_id"] == "fx1" and res["take_id"] == art.id and res["take_no"] == 1
        assert res["duration_s"] == pytest.approx(1.2, abs=0.05)


def test_a_second_take_is_a_new_version_and_the_first_is_kept(tmp_path):
    with light_world(tmp_path, STD_CUES) as (ctx, client, pid):
        generated(client, ctx, pid, "fx1")
        first = take_artifacts(ctx, pid, "fx1")[0]
        generated(client, ctx, pid, "fx1")
        arts = take_artifacts(ctx, pid, "fx1")
        assert [a.take_no for a in arts] == [1, 2]
        assert take_path(ctx, arts[0]).is_file() and arts[0].id == first.id
        out = cue_out(client, pid, "fx1")
        assert [t["take_no"] for t in out["takes"]] == [1, 2]
        assert out["picked_take_id"] == arts[1].id
        assert [t["picked"] for t in out["takes"]] == [False, True]


def test_re_take_while_a_job_is_running_returns_the_same_job(tmp_path):
    with light_world(tmp_path, STD_CUES) as (ctx, client, pid):
        r1 = client.post(audio_url(pid, "/cues/fx1:generate"))
        r2 = client.post(audio_url(pid, "/cues/fx1:generate"))
        assert r1.status_code == 202 and r2.status_code == 202
        assert r1.json()["id"] == r2.json()["id"]
        from m6c_helpers import TERMINAL
        from rf_helpers import wait_job

        assert wait_job(ctx, r1.json()["id"], TERMINAL, timeout=60).status == "succeeded"
        assert len(jobs_of_type(ctx, pid, "gen_audio_cue")) == 1
        assert [a.take_no for a in take_artifacts(ctx, pid, "fx1")] == [1]


def test_generate_refuses_what_cannot_be_generated(tmp_path):
    cues = [
        *STD_CUES,
        cue("empty", "sfx", at("s1"), duration=1.0, prompt=""),
    ]
    with light_world(tmp_path, cues) as (ctx, client, pid):
        def post(cid):
            return client.post(audio_url(pid, f"/cues/{cid}:generate"))

        r = post("empty")
        assert r.status_code == 422 and r.json()["detail"] == 'Cue "empty": prompt is empty.'
        r = post("sil1")
        assert r.status_code == 422 and r.json()["detail"] == 'Cue "sil1": a silence cue has no audio.'
        r = post("f1")
        assert r.status_code == 422 and r.json()["detail"] == 'Cue "f1": this cue uses your own file.'
        assert post("nope").status_code == 404
        assert jobs_of_type(ctx, pid, "gen_audio_cue") == []
        assert take_artifacts(ctx, pid) == []


# suggested cues (AC-9, API side) ----------------------------------------------------------


def test_a_suggested_cue_cannot_be_generated_until_it_is_approved(tmp_path):
    cues = [cue("sug1", "sfx", at("s2"), duration=1.0, prompt="drum roll", state="suggested")]
    with light_world(tmp_path, cues) as (ctx, client, pid):
        assert cue_out(client, pid, "sug1")["state"] == "suggested"
        r = client.post(audio_url(pid, "/cues/sug1:generate"))
        assert r.status_code == 409 and r.json()["detail"] == NEEDS_APPROVAL
        assert jobs_of_type(ctx, pid, "gen_audio_cue") == []
        r = client.post(audio_url(pid, "/cues/sug1:approve"))
        assert r.status_code == 200
        assert next(c for c in r.json()["cues"] if c["id"] == "sug1")["state"] == "draft"
        assert client.post(audio_url(pid, "/cues/sug1:approve")).status_code == 200
        generated(client, ctx, pid, "sug1")
        assert cue_out(client, pid, "sug1")["state"] == "ready"


def test_dismiss_deletes_a_suggested_cue(tmp_path):
    cues = [cue("sug1", "sfx", at("s2"), duration=1.0, state="suggested"), cue("keep", "sfx", at("s1"), duration=1.0)]
    with light_world(tmp_path, cues) as (ctx, client, pid):
        r = client.post(audio_url(pid, "/cues/sug1:dismiss"))
        assert r.status_code == 200
        assert [c["id"] for c in r.json()["cues"]] == ["keep"]
        assert jobs_of_type(ctx, pid, "gen_audio_cue") == []


# own files (AC-3) -----------------------------------------------------------------------


def test_a_non_audio_file_is_rejected_by_content_and_makes_no_take(tmp_path):
    with light_world(tmp_path, STD_CUES) as (ctx, client, pid):
        for data in (b"%PDF-1.4 not audio at all", b"", b"RIFF" + b"\x00" * 20):
            r = upload_cue_file(client, pid, "f1", data, name="song.wav")
            assert r.status_code == 415, r.text
            assert r.json()["detail"] == NOT_AUDIO
        assert take_artifacts(ctx, pid) == []
        assert cue_out(client, pid, "f1")["takes"] == []


def test_an_oversize_file_is_rejected_with_the_size_message(tmp_path):
    with light_world(tmp_path, STD_CUES, max_upload_mb=1) as (ctx, client, pid):
        big = wav_bytes(25.0, rate=24000)
        assert len(big) > 1024 * 1024
        r = upload_cue_file(client, pid, "f1", big)
        assert r.status_code == 413 and r.json() == {"detail": "That clip is larger than 1 MB."}
        assert take_artifacts(ctx, pid) == []


@pytest.mark.parametrize("seconds", [0.7, 5.0])
def test_a_short_clip_is_looped_and_a_long_one_trimmed_to_the_cue_length(tmp_path, seconds):
    with light_world(tmp_path, STD_CUES) as (ctx, client, pid):
        r = upload_cue_file(client, pid, "f1", wav_bytes(seconds, rate=24000), name="my song.wav", note="mine, 2026")
        assert r.status_code == 201, r.text
        out = next(c for c in r.json()["cues"] if c["id"] == "f1")
        (art,) = take_artifacts(ctx, pid, "f1")
        assert art.model_key == "upload" and art.take_no == 1
        assert art.params["source"] == "upload"
        assert art.params["file_name"] == "my song.wav" and art.params["licence_note"] == "mine, 2026"
        assert art.duration_s == pytest.approx(2.0, abs=0.05)
        assert wav_seconds(take_path(ctx, art)) == pytest.approx(2.0, abs=0.05)
        assert out["picked_take_id"] == art.id and out["state"] == "ready"
        assert out["licence"] == "Your file: mine, 2026" and out["file_name"] == "my song.wav"


def test_an_upload_without_a_licence_note_is_flagged(tmp_path):
    with light_world(tmp_path, STD_CUES) as (ctx, client, pid):
        r = upload_cue_file(client, pid, "f1", wav_bytes(1.0, rate=24000))
        assert r.status_code == 201, r.text
        assert cue_out(client, pid, "f1")["licence"] == "No licence note"


def test_an_upload_to_a_cue_that_is_not_a_file_cue_is_refused(tmp_path):
    with light_world(tmp_path, STD_CUES) as (ctx, client, pid):
        r = upload_cue_file(client, pid, "m1", wav_bytes(1.0, rate=24000))
        assert r.status_code == 422, r.text
        assert take_artifacts(ctx, pid) == []


def test_fit_to_length_loops_a_short_source_with_a_crossfade(tmp_path):
    from reelforge.audio.fit import fit_to_length

    src, dst = tmp_path / "s.wav", tmp_path / "d.wav"
    src.write_bytes(wav_bytes(3.0, rate=48000, freq=440.0, amp=0.5))
    run_async(fit_to_length(src, dst, 8.0, crossfade_s=1.0))
    samples, rate, channels, _ = read_wav(dst)
    assert (rate, channels) == (48000, 2)
    assert len(samples) / rate / channels == pytest.approx(8.0, abs=0.001)
    left = samples[0::2]
    win = rate // 10
    levels = [
        (sum(x * x for x in left[i : i + win]) / win) ** 0.5 for i in range(0, len(left) - win, win)
    ]
    assert min(levels) > 0.3 * max(levels), "a loop joint dips or goes silent"


def test_fit_to_length_trims_a_long_source(tmp_path):
    from reelforge.audio.fit import fit_to_length

    src, dst = tmp_path / "s.wav", tmp_path / "d.wav"
    src.write_bytes(wav_bytes(6.0, rate=48000, freq=440.0, amp=0.5))
    run_async(fit_to_length(src, dst, 2.5))
    samples, rate, channels, _ = read_wav(dst)
    assert len(samples) / rate / channels == pytest.approx(2.5, abs=0.001)


# staleness (AC-7, AC-15) -------------------------------------------------------------------


def _approved(client, pid):
    assert client.post(f"/api/v1/projects/{pid}/story:approve").status_code == 200


def _with_takes(client, ctx, pid):
    _approved(client, pid)
    generated(client, ctx, pid, "m1")
    generated(client, ctx, pid, "fx1")
    time.sleep(1.1)


def test_editing_a_prompt_marks_only_that_cue_stale_and_starts_no_job(tmp_path):
    with light_world(tmp_path, STD_CUES) as (ctx, client, pid):
        _with_takes(client, ctx, pid)
        assert stale_audio(client, pid) == set()
        jobs_before = len(jobs_of_type(ctx, pid, "gen_audio_cue"))
        body = {c["id"]: c for c in json.loads(story_with_audio(STD_CUES))["audio"]}["fx1"]
        r = put_cue(client, pid, {**body, "prompt": "a much bigger gong slam"})
        assert r.status_code == 200, r.text
        assert stale_audio(client, pid) == {("fx1", "audio_take")}
        (item,) = [i for i in client.get(f"/api/v1/projects/{pid}/stale").json()["items"] if i["owner_type"] == "audio_cue"]
        (art,) = take_artifacts(ctx, pid, "fx1")
        assert item["artifact_id"] == art.id
        assert cue_out(client, pid, "fx1")["state"] == "stale"
        assert cue_out(client, pid, "fx1")["takes"][0]["stale"] is True
        assert cue_out(client, pid, "m1")["state"] == "ready"
        assert len(jobs_of_type(ctx, pid, "gen_audio_cue")) == jobs_before
        assert len(take_artifacts(ctx, pid, "fx1")) == 1


def test_a_story_save_reports_which_cue_kinds_changed(tmp_path):
    with light_world(tmp_path, STD_CUES) as (ctx, client, pid):
        _with_takes(client, ctx, pid)
        story = json.loads(story_with_audio(STD_CUES))

        def affected(edit):
            d = json.loads(json.dumps(story))
            edit(d)
            r = put(client, pid, json.dumps(d))
            assert r.status_code == 200, r.text
            assert client.post(f"/api/v1/projects/{pid}/story:approve").status_code == 200
            return [a for a in r.json()["affected"] if a["owner_type"] == "audio_cue"]

        def cues_of(d):
            return {c["id"]: c for c in d["audio"]}

        got = affected(lambda d: cues_of(d)["fx1"].update(prompt="a bigger gong"))
        assert got == [{"owner_type": "audio_cue", "owner_id": "fx1", "kinds": ["audio_take"]}]
        story = json.loads(json.dumps({**story, "audio": [*story["audio"]]}))
        for c in story["audio"]:
            if c["id"] == "fx1":
                c["prompt"] = "a bigger gong"
        time.sleep(1.1)
        got = affected(lambda d: cues_of(d)["m1"].update(gain_db=-9.0, fade_in_s=0.5, duck=False))
        assert got == [{"owner_type": "audio_cue", "owner_id": "m1", "kinds": ["audio_mix"]}]
        for c in story["audio"]:
            if c["id"] == "m1":
                c.update(gain_db=-9.0, fade_in_s=0.5, duck=False)
        time.sleep(1.1)
        got = affected(lambda d: cues_of(d)["fx1"].update(start=at("s3", 0.25)))
        assert got == [{"owner_type": "audio_cue", "owner_id": "fx1", "kinds": ["audio_take"]}]


def test_changing_only_gain_fades_or_duck_leaves_the_take_not_stale(tmp_path):
    with light_world(tmp_path, STD_CUES) as (ctx, client, pid):
        _with_takes(client, ctx, pid)
        body = {c["id"]: c for c in json.loads(story_with_audio(STD_CUES))["audio"]}["m1"]
        r = put_cue(client, pid, {**body, "gain_db": -3.0, "fade_out_s": 0.5, "duck": False})
        assert r.status_code == 200, r.text
        assert stale_audio(client, pid) == set()
        out = cue_out(client, pid, "m1")
        assert out["state"] == "ready" and out["takes"][0]["stale"] is False
        assert len(take_artifacts(ctx, pid, "m1")) == 1


def test_a_scene_length_change_stales_only_the_cues_whose_length_it_changes(tmp_path):
    with light_world(tmp_path, STD_CUES) as (ctx, client, pid):
        _approved(client, pid)
        generated(client, ctx, pid, "m1")
        generated(client, ctx, pid, "fx1")
        generated(client, ctx, pid, "amb1")
        time.sleep(1.1)
        d = json.loads(story_with_audio(STD_CUES))
        d["scenes"][4]["duration"] = 3.0  # s5 is amb1's end
        r = put(client, pid, json.dumps(d))
        assert r.status_code == 200, r.text
        assert stale_audio(client, pid) == {("amb1", "audio_take")}
        assert cue_out(client, pid, "amb1")["duration_s"] == pytest.approx(10.0)


def test_saving_the_story_again_without_a_cue_change_keeps_takes_and_marks_nothing(tmp_path):
    with light_world(tmp_path, STD_CUES) as (ctx, client, pid):
        _with_takes(client, ctx, pid)
        ids = [a.id for a in take_artifacts(ctx, pid)]
        r = put(client, pid, story_with_audio(STD_CUES))
        assert r.status_code == 200, r.text
        assert [a for a in r.json().get("affected", []) if a["owner_type"] == "audio_cue"] == []
        assert stale_audio(client, pid) == set()
        assert [a.id for a in take_artifacts(ctx, pid)] == ids
        assert [c["state"] for c in get_audio(client, pid)["cues"] if c["id"] in ("m1", "fx1")] == ["ready", "ready"]
