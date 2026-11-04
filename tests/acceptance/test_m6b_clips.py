"""m6b AC-15 (clip used for its emotion), AC-16 (upload, from-take, content check, stale on remove)."""

from __future__ import annotations

from pathlib import Path

from m3_helpers import png_bytes
from m6b_helpers import (
    LINES,
    UNKNOWN_JOY,
    active_take,
    base,
    emo_world,
    gen_lines,
    get_voices,
    inputs_of,
    project_with_presets,
    rows_for,
    set_emotion,
    take_rows,
    wav_bytes,
    wrap_worker,
)
from rf_helpers import artifacts_of

NEUTRAL_TEXT = "ye neutral clip ka text hai"
SAD_TEXT = "ye udaas clip ka text hai"


def _clone(client, pid, key="tomato"):
    files = {"file": ("n.wav", wav_bytes(6.0, freq=300.0), "audio/wav")}
    r = client.post(f"{base(pid)}/voices/characters/{key}:upload-reference", files=files,
                    data={"reference_text": NEUTRAL_TEXT})
    assert r.status_code == 201, r.text
    r = client.post(f"{base(pid)}/voices/characters/{key}:set",
                    json={"mode": "cloned", "reference_text": NEUTRAL_TEXT})
    assert r.status_code == 200, r.text


def _clip_url(pid, emotion, verb, key="tomato"):
    return f"{base(pid)}/voices/characters/{key}/emotion-clips/{emotion}:{verb}"


def _upload(client, pid, emotion, data=None, transcript=SAD_TEXT, key="tomato"):
    files = {"file": ("secret_name.wav", data if data is not None else wav_bytes(6.0, freq=500.0), "audio/wav")}
    form = {"transcript": transcript} if transcript is not None else None
    return client.post(_clip_url(pid, emotion, "upload", key), files=files, data=form)


def _voice(client, pid, key="tomato"):
    return next(c for c in get_voices(client, pid)["characters"] if c["key"] == key)["voice"]


def _path(ctx, art) -> Path:
    return Path(ctx.store.absolute_path(art)).resolve()


def _ids(ctx, pid):
    return {a.id for a in artifacts_of(ctx, pid)}


# AC-15 --------------------------------------------------------------------------


def test_sad_clip_is_the_reference_for_sad_lines_only(tmp_path, monkeypatch):
    ctx, client, _ = emo_world(tmp_path)
    log = wrap_worker(tmp_path, monkeypatch)
    with client:
        pid = project_with_presets(client, ctx)
        _clone(client, pid)
        neutral = next(a for a in artifacts_of(ctx, pid) if a.kind == "voice_reference")
        before = _ids(ctx, pid)
        r = _upload(client, pid, "sad")
        assert r.status_code == 201, r.text
        clip = next(a for a in artifacts_of(ctx, pid) if a.id not in before)
        assert _path(ctx, clip) != _path(ctx, neutral)

        assert set_emotion(client, pid, "s1", "sad").status_code == 200
        assert set_emotion(client, pid, "s3", "happy").status_code == 200
        gen_lines(client, ctx, pid, "s1", "s3", "s5")
        sad_row, happy_row, plain_row = (rows_for(log, s)[0] for s in ("s1", "s3", "s5"))
        assert Path(sad_row["ref_audio"]).resolve() == _path(ctx, clip) and sad_row["ref_text"] == SAD_TEXT
        for row in (happy_row, plain_row):
            assert Path(row["ref_audio"]).resolve() == _path(ctx, neutral) and row["ref_text"] == NEUTRAL_TEXT

        assert clip.id in inputs_of(ctx, take_rows(ctx, pid, "s1")[0].id)
        for s in ("s3", "s5"):
            assert clip.id not in inputs_of(ctx, take_rows(ctx, pid, s)[0].id)
        ph = take_rows(ctx, pid, "s1")[0].params["phrases"][0]
        assert ph["reference"] == "emotion" and ph["reference_artifact_id"] == clip.id
        assert take_rows(ctx, pid, "s3")[0].params["phrases"][0]["reference"] == "neutral"
        line = next(x for x in get_voices(client, pid)["lines"] if x["scene_id"] == "s1")
        assert line["effective"]["phrases"][0]["reference_label"] == "Sad reference clip"


def test_voice_without_clips_behaves_as_before(tmp_path, monkeypatch):
    ctx, client, _ = emo_world(tmp_path)
    log = wrap_worker(tmp_path, monkeypatch)
    with client:
        pid = project_with_presets(client, ctx)
        _clone(client, pid)
        neutral = next(a for a in artifacts_of(ctx, pid) if a.kind == "voice_reference")
        assert "emotion_clips" not in _voice(client, pid)
        assert set_emotion(client, pid, "s1", "sad").status_code == 200
        gen_lines(client, ctx, pid, "s1", "s3")
        for s in ("s1", "s3"):
            row = rows_for(log, s)[0]
            assert Path(row["ref_audio"]).resolve() == _path(ctx, neutral)
            assert inputs_of(ctx, take_rows(ctx, pid, s)[0].id) == [neutral.id]
        assert "reference_kind" not in take_rows(ctx, pid, "s3")[0].params["voice"]


# AC-16 --------------------------------------------------------------------------


def test_upload_clip_listed_on_the_voice_and_stored_as_artifact(tmp_path):
    ctx, client, _ = emo_world(tmp_path)
    with client:
        pid = project_with_presets(client, ctx)
        _clone(client, pid)
        before = _ids(ctx, pid)
        data = wav_bytes(6.0, freq=500.0)
        r = _upload(client, pid, "sad", data)
        assert r.status_code == 201, r.text
        clips = r.json()["emotion_clips"]
        assert set(clips) == {"sad"} and clips["sad"]["transcript"] == SAD_TEXT
        assert abs(clips["sad"]["clip_seconds"] - 6.0) < 0.2
        assert clips["sad"]["url"].startswith("/media/")
        served = client.get(clips["sad"]["url"])
        assert served.status_code == 200 and served.content == data
        assert _voice(client, pid)["emotion_clips"]["sad"]["transcript"] == SAD_TEXT
        new = [a for a in artifacts_of(ctx, pid) if a.id not in before]
        assert len(new) == 1
        path = _path(ctx, new[0])
        assert path.exists() and "secret_name" not in str(path)
        assert str(path).startswith(str(Path(ctx.settings.data_root).resolve()))


def test_upload_clip_rejections_save_nothing(tmp_path):
    ctx, client, _ = emo_world(tmp_path, max_upload_mb=1)
    with client:
        pid = project_with_presets(client, ctx)
        _clone(client, pid)
        before = _ids(ctx, pid)
        for bad in (b"just words pretending to be a clip", png_bytes(), b"RIFF\x00\x00\x00\x00WAVEjunk"):
            r = _upload(client, pid, "sad", bad)
            assert r.status_code == 415 and r.json() == {"detail": "That file isn't an audio clip."}
        r = _upload(client, pid, "sad", wav_bytes(25.0))
        assert r.status_code == 413 and r.json() == {"detail": "That clip is larger than 1 MB."}
        for blank in (None, "", "   "):
            r = _upload(client, pid, "sad", transcript=blank)
            assert r.status_code == 422 and r.json() == {"detail": "A transcript is required."}, blank
        r = _upload(client, pid, "joy")
        assert r.status_code == 422 and r.json() == {"detail": UNKNOWN_JOY}
        assert _ids(ctx, pid) == before and "emotion_clips" not in _voice(client, pid)


def test_clips_are_only_for_cloned_voices(tmp_path):
    ctx, client, _ = emo_world(tmp_path)
    with client:
        pid = project_with_presets(client, ctx)  # tomato is a preset voice
        r = _upload(client, pid, "sad")
        assert r.status_code == 409 and r.json() == {"detail": "Emotion clips are only for cloned voices."}


def test_clip_from_an_existing_take(tmp_path, monkeypatch):
    ctx, client, _ = emo_world(tmp_path)
    wrap_worker(tmp_path, monkeypatch)
    with client:
        pid = project_with_presets(client, ctx)
        _clone(client, pid)
        gen_lines(client, ctx, pid, "s1", "s2")
        mine = active_take(client, pid, "s1")["id"]
        theirs = active_take(client, pid, "s2")["id"]  # spoken by potato
        r = client.post(_clip_url(pid, "happy", "from-take"), json={"scene_id": "s1", "take_id": mine, "transcript": None})
        assert r.status_code == 201, r.text
        assert r.json()["emotion_clips"]["happy"]["transcript"] == LINES["s1"]
        r = client.post(_clip_url(pid, "anger", "from-take"),
                        json={"scene_id": "s1", "take_id": mine, "transcript": "ghussa vakya"})
        assert r.status_code == 201 and r.json()["emotion_clips"]["anger"]["transcript"] == "ghussa vakya"
        clip = r.json()["emotion_clips"]["anger"]
        assert client.get(clip["url"]).status_code == 200 and clip["clip_seconds"] > 0
        r = client.post(_clip_url(pid, "sad", "from-take"), json={"scene_id": "s2", "take_id": theirs, "transcript": None})
        assert r.status_code == 404 and r.json() == {"detail": "take not found"}
        assert "sad" not in _voice(client, pid)["emotion_clips"]


def test_removing_or_replacing_a_clip_stales_only_takes_made_with_it(tmp_path, monkeypatch):
    ctx, client, _ = emo_world(tmp_path)
    wrap_worker(tmp_path, monkeypatch)
    with client:
        pid = project_with_presets(client, ctx)
        _clone(client, pid)
        assert _upload(client, pid, "sad").status_code == 201
        assert _upload(client, pid, "happy", transcript="khush clip").status_code == 201
        for sid, emo in (("s1", "sad"), ("s3", "happy"), ("s5", None)):
            assert set_emotion(client, pid, sid, emo).status_code == 200
        gen_lines(client, ctx, pid, "s1", "s3", "s5")

        def stale():
            by = {x["scene_id"]: x for x in get_voices(client, pid)["lines"]}
            return {s: by[s]["takes"][0]["stale"] for s in ("s1", "s3", "s5")}

        assert stale() == {"s1": False, "s3": False, "s5": False}
        jobs = len(client.get("/api/v1/jobs").json())
        r = client.post(_clip_url(pid, "sad", "remove"))
        assert r.status_code == 200, r.text
        assert "sad" not in r.json().get("emotion_clips", {}) and "happy" in r.json()["emotion_clips"]
        assert stale() == {"s1": True, "s3": False, "s5": False}
        assert len(client.get("/api/v1/jobs").json()) == jobs

        assert _upload(client, pid, "happy", data=wav_bytes(7.0, freq=600.0), transcript="naya khush").status_code == 201
        assert stale() == {"s1": True, "s3": True, "s5": False}
