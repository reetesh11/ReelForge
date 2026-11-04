"""m6b AC-1, AC-2, AC-4, AC-8, AC-11: speed, emotion mapping, phrases, age in `instruct`, full mock path."""

from __future__ import annotations

from m6b_helpers import (
    LINES,
    MAPPING,
    action,
    active_take,
    approve_all,
    base,
    emo_world,
    gen_lines,
    generate,
    get_voices,
    line_of,
    longest_gap_s,
    project_with_presets,
    rows_for,
    set_age,
    set_emotion,
    take_rows,
    wav_bytes,
    wrap_worker,
    write_mapping,
)

TWO = "<happy>Wah kya baat hai yaar</happy> <fear>Arre yeh kaun hai wahan</fear>"


def _parts(instruct: str | None) -> list[str]:
    return [p.strip() for p in (instruct or "").split(",")]


# AC-1 ---------------------------------------------------------------------------


def test_speed_changes_take_length_in_the_right_direction(tmp_path, monkeypatch):
    ctx, client, _ = emo_world(tmp_path)
    log = wrap_worker(tmp_path, monkeypatch)
    with client:
        pid = project_with_presets(client, ctx)
        gen_lines(client, ctx, pid, "s2")
        d_base = active_take(client, pid, "s2")["duration_s"]
        durations = {}
        for speed in (0.8, 1.25):
            assert action(client, pid, "s2", "set-timing", speed=speed).status_code == 200
            gen_lines(client, ctx, pid, "s2")
            durations[speed] = active_take(client, pid, "s2")["duration_s"]
        assert durations[1.25] < d_base < durations[0.8]
        assert abs(durations[0.8] / d_base - 1.25) <= 0.125
        assert abs(durations[1.25] / d_base - 0.8) <= 0.08

        rows = rows_for(log, "s2")
        assert [r["target_speed"] for r in rows] == [1.0, 0.8, 1.25]
        assert all(r["speed"] == 1.0 and r["duration_scale"] == 1.0 for r in rows)

        takes = take_rows(ctx, pid, "s2")
        assert [t.params["speed"] for t in takes] == [1.0, 0.8, 1.25]
        assert "duration_requested_s" not in takes[0].params
        assert takes[1].params["duration_requested_s"] > takes[2].params["duration_requested_s"] > 0


# AC-2 ---------------------------------------------------------------------------


def test_sad_line_records_mapping_values_and_table_edit_affects_next_take_only(tmp_path, monkeypatch):
    ctx, client, path = emo_world(tmp_path)
    log = wrap_worker(tmp_path, monkeypatch)
    with client:
        pid = project_with_presets(client, ctx)
        gen_lines(client, ctx, pid, "s1")  # a plain line, never stale from a mapping change
        assert set_emotion(client, pid, "s2", "sad").status_code == 200
        gen_lines(client, ctx, pid, "s2")

        row = rows_for(log, "s2")[0]
        assert row["id"] == "s2" and row["text"].startswith("[sigh]") and LINES["s2"] in row["text"]
        assert row["duration_scale"] == 1.25 and row["gen"] == {"guidance_scale": 2.0}
        assert "low pitch" in (row["instruct"] or "")

        first = take_rows(ctx, pid, "s2")[0]
        assert first.params["text"] == LINES["s2"]
        ph = first.params["phrases"]
        assert len(ph) == 1
        assert ph[0]["emotion"] == "sad" and ph[0]["tags"] == ["[sigh]"] and ph[0]["tag_position"] == "prefix"
        assert ph[0]["pitch"] == "low pitch" and ph[0]["duration_scale"] == 1.25
        assert ph[0]["generation"] == {"guidance_scale": 2.0}
        assert ph[0]["post"] == {"semitones": -2.0, "gain_db": -3.0, "pause_s": 0.0}
        assert ph[0]["reference"] == "neutral"
        assert active_take(client, pid, "s2")["stale"] is False

        write_mapping(
            tmp_path,
            MAPPING.replace('pitch = "low pitch"\nduration_scale = 1.25', 'pitch = "very low pitch"\nduration_scale = 1.5'),
        )
        # existing takes keep what they recorded, and show as stale
        again = take_rows(ctx, pid, "s2")[0]
        assert again.params["phrases"][0]["duration_scale"] == 1.25
        v = get_voices(client, pid)
        by = {x["scene_id"]: x for x in v["lines"]}
        assert by["s2"]["takes"][0]["stale"] is True
        assert all(t["stale"] is False for t in by["s1"]["takes"])
        assert path.exists()

        gen_lines(client, ctx, pid, "s2")
        second = take_rows(ctx, pid, "s2")[1]
        sp = second.params["phrases"][0]
        assert sp["pitch"] == "very low pitch" and sp["duration_scale"] == 1.5
        assert take_rows(ctx, pid, "s2")[0].params["phrases"][0]["pitch"] == "low pitch"
        assert rows_for(log, "s2")[1]["duration_scale"] == 1.5
        assert active_take(client, pid, "s2")["stale"] is False


def test_mapping_direction_in_packaged_table(tmp_path):
    """AC-13 (direction only): happy sounds higher than sad, fear is shorter than sad."""
    from reelforge.story.markup import EMOTIONS
    from reelforge.voice.mapping import load_mapping
    from rf_helpers import make_settings

    m = load_mapping(make_settings(tmp_path).emotion_mapping_path)
    for e in EMOTIONS:
        assert m.rule(e) is not None, e
    assert m.rule("happy").post.semitones > m.rule("sad").post.semitones
    assert m.rule("fear").duration_scale < m.rule("sad").duration_scale
    assert isinstance(m.phrase_gap_ms, int)


def test_load_mapping_reads_a_custom_file(tmp_path):
    from reelforge.voice.mapping import load_mapping

    m = load_mapping(write_mapping(tmp_path))
    sad = m.rule("sad")
    assert sad.tags == ["[sigh]"] and sad.tag_position == "prefix" and sad.pitch == "low pitch"
    assert sad.duration_scale == 1.25 and sad.generation == {"guidance_scale": 2.0}
    assert (sad.post.semitones, sad.post.gain_db, sad.post.pause_s, sad.post.tempo) == (-2.0, -3.0, 0.0, 1.0)
    assert m.rule("anger").tags == [] and m.phrase_gap_ms == 150


# AC-4 ---------------------------------------------------------------------------


def test_two_phrases_two_model_calls_one_joined_take_with_gap(tmp_path, monkeypatch):
    ctx, client, _ = emo_world(tmp_path)
    log = wrap_worker(tmp_path, monkeypatch)
    with client:
        pid = project_with_presets(client, ctx)
        r = action(client, pid, "s2", "edit-text", text=TWO)
        assert r.status_code == 200, r.text
        gen_lines(client, ctx, pid, "s2")

        rows = rows_for(log, "s2")
        assert [x["id"] for x in rows] == ["s2#1", "s2#2"]
        assert "<" not in rows[0]["text"] + rows[1]["text"]
        assert rows[0]["text"].startswith("[laughter]") and "Wah kya baat hai yaar" in rows[0]["text"]
        assert rows[1]["text"].startswith("[surprise-ah]") and "Arre yeh kaun hai wahan" in rows[1]["text"]
        assert (rows[0]["duration_scale"], rows[1]["duration_scale"]) == (0.9, 0.8)

        ln = line_of(client, pid, "s2")
        assert len(ln["takes"]) == 1
        audio = client.get(active_take(client, pid, "s2")["audio_url"]).content
        assert abs(longest_gap_s(audio) - 0.150) <= 0.020

        t = take_rows(ctx, pid, "s2")[0]
        assert t.params["gap_ms"] == 150
        assert [p["emotion"] for p in t.params["phrases"]] == ["happy", "fear"]
        assert ln["effective"]["gap_ms"] == 150 and len(ln["effective"]["phrases"]) == 2


def test_phrase_gap_setting_is_per_project_and_stales_only_multi_phrase_takes(tmp_path, monkeypatch):
    ctx, client, _ = emo_world(tmp_path)
    wrap_worker(tmp_path, monkeypatch)
    with client:
        pid = project_with_presets(client, ctx)
        url = f"{base(pid)}/voices/settings"
        assert client.get(url).json() == {"phrase_gap_ms": 150, "default_phrase_gap_ms": 150}
        for bad in (-1, 1001):
            r = client.put(url, json={"phrase_gap_ms": bad})
            assert r.status_code == 422 and r.json() == {"detail": "phrase_gap_ms must be between 0 and 1000."}
        assert client.get(url).json()["phrase_gap_ms"] == 150

        assert action(client, pid, "s2", "edit-text", text=TWO).status_code == 200
        gen_lines(client, ctx, pid, "s1", "s2")
        r = client.put(url, json={"phrase_gap_ms": 400})
        assert r.status_code == 200 and r.json() == {"phrase_gap_ms": 400, "default_phrase_gap_ms": 150}
        by = {x["scene_id"]: x for x in get_voices(client, pid)["lines"]}
        assert by["s2"]["takes"][0]["stale"] is True
        assert by["s1"]["takes"][0]["stale"] is False

        gen_lines(client, ctx, pid, "s2")
        assert take_rows(ctx, pid, "s2")[1].params["gap_ms"] == 400
        audio = client.get(active_take(client, pid, "s2")["audio_url"]).content
        assert abs(longest_gap_s(audio) - 0.400) <= 0.020
        assert active_take(client, pid, "s2")["stale"] is False


def test_picker_emotion_overrides_phrase_markup(tmp_path, monkeypatch):
    ctx, client, _ = emo_world(tmp_path)
    log = wrap_worker(tmp_path, monkeypatch)
    with client:
        pid = project_with_presets(client, ctx)
        assert action(client, pid, "s2", "edit-text", text=TWO).status_code == 200
        assert set_emotion(client, pid, "s2", "fear").status_code == 200
        gen_lines(client, ctx, pid, "s2")
        rows = rows_for(log, "s2")
        assert [x["id"] for x in rows] == ["s2"]  # one model call for the whole line
        assert "<" not in rows[0]["text"] and rows[0]["duration_scale"] == 0.8
        assert rows[0]["text"].startswith("[surprise-ah]")
        t = take_rows(ctx, pid, "s2")[0]
        assert [p["emotion"] for p in t.params["phrases"]] == ["fear"]
        assert "gap_ms" not in t.params


def test_typed_tags_reach_the_model(tmp_path, monkeypatch):
    ctx, client, _ = emo_world(tmp_path)
    log = wrap_worker(tmp_path, monkeypatch)
    with client:
        pid = project_with_presets(client, ctx)
        assert action(client, pid, "s3", "edit-text", text="[sigh] Dekho dekho mithai aa gayi").status_code == 200
        gen_lines(client, ctx, pid, "s3")
        assert "[sigh]" in rows_for(log, "s3")[0]["text"]
        assert take_rows(ctx, pid, "s3")[0].params["text"] == "[sigh] Dekho dekho mithai aa gayi"


def test_kokoro_does_not_apply_emotion(tmp_path, monkeypatch):
    ctx, client, _ = emo_world(tmp_path)
    log = wrap_worker(tmp_path, monkeypatch)
    with client:
        pid = project_with_presets(client, ctx)
        client.put("/api/v1/voice-model", json={"voice_model": "kokoro"})
        for key, vid in (("tomato", "hm_omega"), ("potato", "hf_alpha")):
            r = client.post(f"{base(pid)}/voices/characters/{key}:set", json={"mode": "preset", "voice_id": vid})
            assert r.status_code == 200, r.text
        assert set_emotion(client, pid, "s2", "sad").status_code == 200
        gen_lines(client, ctx, pid, "s2")
        row = rows_for(log, "s2")[0]
        assert row["text"] == LINES["s2"] and row["duration_scale"] == 1.0 and row["target_speed"] == 1.0
        assert not row.get("instruct")
        assert line_of(client, pid, "s2")["effective"]["emotion_applied"] is False


# AC-8 ---------------------------------------------------------------------------


def test_preset_voice_gets_age_band_and_pitch_in_instruct(tmp_path, monkeypatch):
    ctx, client, _ = emo_world(tmp_path)
    log = wrap_worker(tmp_path, monkeypatch)
    with client:
        pid = project_with_presets(client, ctx)
        assert set_age(client, pid, "tomato", 67).status_code == 200
        assert set_emotion(client, pid, "s1", "sad").status_code == 200
        gen_lines(client, ctx, pid, "s1", "s2", "s3")
        sad_age = _parts(rows_for(log, "s1")[0]["instruct"])
        assert sad_age.count("elderly") == 1 and sad_age.count("low pitch") == 1
        bands = {"child", "teenager", "young adult", "middle-aged"}
        assert not bands & set(sad_age)
        assert _parts(rows_for(log, "s3")[0]["instruct"]).count("elderly") == 1
        assert not rows_for(log, "s2")[0].get("instruct")  # no age, no emotion for the other speaker
        assert take_rows(ctx, pid, "s1")[0].params["age_band"] == "elderly"
        assert "age_band" not in take_rows(ctx, pid, "s2")[0].params
        assert line_of(client, pid, "s1")["effective"]["age_band"] == "elderly"


def test_cloned_voice_always_gets_the_age_band(tmp_path, monkeypatch):
    ctx, client, _ = emo_world(tmp_path)
    log = wrap_worker(tmp_path, monkeypatch)
    with client:
        pid = project_with_presets(client, ctx)
        files = {"file": ("c.wav", wav_bytes(6.0), "audio/wav")}
        r = client.post(f"{base(pid)}/voices/characters/tomato:upload-reference", files=files,
                        data={"reference_text": "ye clip ka text hai"})
        assert r.status_code == 201, r.text
        r = client.post(f"{base(pid)}/voices/characters/tomato:set",
                        json={"mode": "cloned", "reference_text": "ye clip ka text hai"})
        assert r.status_code == 200, r.text
        assert set_age(client, pid, "tomato", 15).status_code == 200
        gen_lines(client, ctx, pid, "s1")
        row = rows_for(log, "s1")[0]
        assert row["ref_audio"] and row["instruct"] == "teenager"
        assert set_emotion(client, pid, "s3", "sad").status_code == 200
        gen_lines(client, ctx, pid, "s3")
        assert _parts(rows_for(log, "s3")[0]["instruct"]) == ["low pitch", "teenager"]


# AC-11 --------------------------------------------------------------------------


def test_full_voice_path_with_emotion_and_age_on_the_mock_backend(tmp_path):
    ctx, client, _ = emo_world(tmp_path)  # the suite-wide guard fails any outbound connection
    with client:
        pid = project_with_presets(client, ctx)
        assert set_age(client, pid, "tomato", 67).status_code == 200
        assert set_age(client, pid, "potato", 8).status_code == 200
        assert set_emotion(client, pid, "s1", "happy").status_code == 200
        assert set_emotion(client, pid, "s2", "sad").status_code == 200
        assert set_emotion(client, pid, "s3", "anger").status_code == 200
        assert action(client, pid, "s4", "edit-text", text=TWO).status_code == 200
        _, job = generate(client, ctx, pid)
        assert job.status == "succeeded", job.error
        for ln in get_voices(client, pid)["lines"]:
            assert ln["state"] == "ready" and len(ln["takes"]) == 1
            audio = client.get(active_take(client, pid, ln["scene_id"])["audio_url"])
            assert audio.status_code == 200 and audio.content[:4] == b"RIFF"
        last = approve_all(client, pid)
        assert last["project_stage"] == "VOICES_APPROVED"
        gen_lines(client, ctx, pid, "s2")  # re-take
        assert len(line_of(client, pid, "s2")["takes"]) == 2
        assert action(client, pid, "s2", "approve").json()["project_stage"] == "VOICES_APPROVED"
