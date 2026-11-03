"""m4 AC-8: character voices, clone uploads checked by content, library persistence."""

from __future__ import annotations

import hashlib

from m3_helpers import cast_item, cast_url, gen_and_approve, png_bytes
from m4_helpers import base, cast_approved, get_voices, story_text, voice_world, wav_bytes
from rf_helpers import artifacts_of
from story_helpers import put


def _upload(client, pid, key, data: bytes, name="my_secret_name.wav", text: str | None = None):
    files = {"file": (name, data, "audio/wav")}
    form = {"reference_text": text} if text is not None else None
    return client.post(f"{base(pid)}/voices/characters/{key}:upload-reference", files=files, data=form)


def _voice_of(client, pid, key):
    return next(c for c in get_voices(client, pid)["characters"] if c["key"] == key)["voice"]


def test_voices_locked_before_cast_approved(tmp_path):
    ctx, client = voice_world(tmp_path)
    with client:
        from rf_helpers import create_project

        pid = create_project(client, "x")["id"]
        assert put(client, pid, story_text()).status_code == 200
        r = client.get(f"{base(pid)}/voices")
        assert r.status_code == 409 and r.json() == {"detail": "Approve the cast first."}
        assert client.get(f"{base('nope')}/voices").status_code == 404


def test_preset_set_validate_and_clear(tmp_path):
    ctx, client = voice_world(tmp_path)
    with client:
        pid = cast_approved(client, ctx)
        v = get_voices(client, pid)
        assert [p["id"] for p in v["presets"]] == ["asha", "ravi"]
        assert v["voice_model"]["key"] == "omnivoice"
        assert all(c["voice"] is None for c in v["characters"])
        url = f"{base(pid)}/voices/characters/tomato"
        r = client.post(url + ":set", json={"mode": "preset", "voice_id": "ravi", "speed": 1.1})
        assert r.status_code == 200, r.text
        body = r.json()
        assert (body["mode"], body["voice_id"], body["model"], body["language"]) == ("preset", "ravi", "omnivoice", "hi")
        assert body["speed"] == 1.1 and body["model_mismatch"] is False
        assert client.post(url + ":set", json={"mode": "preset", "voice_id": "hf_alpha"}).status_code == 422
        bad = client.post(url + ":set", json={"mode": "preset", "voice_id": "ravi", "speed": 1.4})
        assert bad.status_code == 422 and bad.json() == {"detail": "speed must be between 0.8 and 1.25"}
        assert _voice_of(client, pid, "tomato")["speed"] == 1.1
        assert client.post(f"{base(pid)}/voices/characters/ghost:set",
                           json={"mode": "preset", "voice_id": "ravi"}).status_code == 404
        r = client.post(url + ":clear")
        assert r.status_code == 200 and r.json() == {"voice": None}
        assert _voice_of(client, pid, "tomato") is None


def test_cloned_needs_clip_and_transcript(tmp_path):
    ctx, client = voice_world(tmp_path)
    with client:
        pid = cast_approved(client, ctx)
        url = f"{base(pid)}/voices/characters/tomato:set"
        r = client.post(url, json={"mode": "cloned", "reference_text": "kuch bola"})
        assert r.status_code == 422 and r.json() == {"detail": "Cloned voices need a clip and a transcript."}
        assert _upload(client, pid, "tomato", wav_bytes(6.0)).status_code == 201
        r = client.post(url, json={"mode": "cloned", "reference_text": ""})
        assert r.status_code == 422
        r = client.post(url, json={"mode": "cloned", "reference_text": "kuch bola"})
        assert r.status_code == 200 and r.json()["mode"] == "cloned"
        assert r.json()["reference_text"] == "kuch bola"


def test_upload_reference_accepted_stored_under_generated_name(tmp_path):
    ctx, client = voice_world(tmp_path)
    with client:
        pid = cast_approved(client, ctx)
        data = wav_bytes(6.0)
        r = _upload(client, pid, "tomato", data, text="ye clip ka text hai")
        assert r.status_code == 201, r.text
        v = r.json()
        assert v["mode"] == "cloned" and v["reference_text"] == "ye clip ka text hai"
        assert abs(v["clip_seconds"] - 6.0) < 0.2
        served = client.get(v["reference_url"])
        assert served.status_code == 200
        assert hashlib.sha256(served.content).hexdigest() == hashlib.sha256(data).hexdigest()
        arts = [a for a in artifacts_of(ctx, pid) if a.kind == "voice_reference"]
        assert len(arts) == 1 and arts[0].owner_type == "character"
        path = ctx.store.absolute_path(arts[0])
        assert path.exists() and "my_secret_name" not in str(path)
        assert str(path).startswith(str(ctx.settings.data_root)) and "voices/tomato" in str(path)


def test_upload_reference_rejects_non_audio_by_content(tmp_path):
    ctx, client = voice_world(tmp_path)
    with client:
        pid = cast_approved(client, ctx)
        before = get_voices(client, pid)
        for data in (b"just some text pretending to be a clip", png_bytes(), b"RIFF\x00\x00\x00\x00WAVEjunk"):
            r = _upload(client, pid, "tomato", data, name="clip.wav")
            assert r.status_code == 415, r.text
            assert r.json() == {"detail": "That file isn't an audio clip."}
        assert [a for a in artifacts_of(ctx, pid) if a.kind == "voice_reference"] == []
        assert get_voices(client, pid)["characters"] == before["characters"]


def test_upload_reference_rejects_oversized(tmp_path):
    ctx, client = voice_world(tmp_path, max_upload_mb=1)
    with client:
        pid = cast_approved(client, ctx)
        big = wav_bytes(25.0)  # about 1.2 MB of PCM
        assert len(big) > 1024 * 1024
        r = _upload(client, pid, "tomato", big)
        assert r.status_code == 413 and r.json() == {"detail": "That clip is larger than 1 MB."}
        assert [a for a in artifacts_of(ctx, pid) if a.kind == "voice_reference"] == []
        assert _voice_of(client, pid, "tomato") is None


def test_sniff_audio_and_probe():
    import pytest
    from reelforge.voice.uploads import NotAnAudioClip, probe_seconds, sniff_audio
    from rf_helpers import run_async

    assert sniff_audio(wav_bytes(1.0)) == "wav"
    for bad in (b"hello", png_bytes(), b""):
        with pytest.raises(NotAnAudioClip):
            sniff_audio(bad)
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "a.wav"
        p.write_bytes(wav_bytes(2.0))
        assert abs(run_async(probe_seconds(p)) - 2.0) < 0.1
        q = Path(d) / "b.wav"
        q.write_bytes(b"RIFF....WAVEjunk")
        with pytest.raises(NotAnAudioClip):
            run_async(probe_seconds(q))


def test_voice_saved_with_character_in_library_and_reused(tmp_path):
    ctx, client = voice_world(tmp_path)
    with client:
        a = cast_approved(client, ctx, "Project A")
        clip = wav_bytes(7.0)
        r = _upload(client, a, "tomato", clip, text="ye mera clip hai")
        assert r.status_code == 201
        r = client.post(f"{base(a)}/voices/characters/tomato:set",
                        json={"mode": "cloned", "reference_text": "ye mera clip hai", "speed": 1.05})
        assert r.status_code == 200, r.text
        r = client.post(f"{base(a)}/voices/characters/potato:set", json={"mode": "preset", "voice_id": "asha"})
        assert r.status_code == 200

        lib_id = cast_item(client, a, "tomato")["library_character_id"]
        lib = client.get(f"/api/v1/library/characters/{lib_id}").json()
        assert lib["voice"]["mode"] == "cloned" and lib["voice"]["reference_text"] == "ye mera clip hai"
        assert lib["voice"]["speed"] == 1.05 and lib["voice"]["language"] == "hi"
        from reelforge.library.service import get_voice

        stored = get_voice(ctx, lib_id)
        assert stored["mode"] == "cloned" and stored["reference_sha256"] == hashlib.sha256(clip).hexdigest()
        ref = ctx.settings.data_root / "library" / "characters" / lib_id
        assert any(p.name.startswith("voice_reference.") for p in ref.iterdir())

        plib = client.get(f"/api/v1/library/characters/{cast_item(client, a, 'potato')['library_character_id']}").json()
        assert plib["voice"]["mode"] == "preset" and plib["voice"]["voice_id"] == "asha"

        # a second project reuses the library character: same settings, same clip
        b = _new_project_with_library_tomato(client, ctx, lib_id)
        v = _voice_of(client, b, "tomato")
        assert (v["mode"], v["reference_text"], v["speed"], v["language"]) == ("cloned", "ye mera clip hai", 1.05, "hi")
        assert hashlib.sha256(client.get(v["reference_url"]).content).hexdigest() == hashlib.sha256(clip).hexdigest()


def _new_project_with_library_tomato(client, ctx, lib_id):
    from rf_helpers import create_project
    from story_helpers import STORY_YAML

    b = create_project(client, "Project B")["id"]
    assert put(client, b, STORY_YAML).status_code == 200
    assert client.post(f"{base(b)}/story:approve").status_code == 200
    r = client.post(cast_url(b, "tomato", "use-library"), json={"character_id": lib_id})
    assert r.status_code == 200, r.text
    gen_and_approve(client, ctx, b, "potato", seed=3)
    assert client.get(f"{base(b)}").json()["stage"] == "CAST_APPROVED"
    return b


def test_changing_voice_later_updates_library(tmp_path):
    ctx, client = voice_world(tmp_path)
    with client:
        pid = cast_approved(client, ctx)
        lib_id = cast_item(client, pid, "tomato")["library_character_id"]
        assert "voice" not in client.get(f"/api/v1/library/characters/{lib_id}").json()
        client.post(f"{base(pid)}/voices/characters/tomato:set", json={"mode": "preset", "voice_id": "ravi"})
        assert client.get(f"/api/v1/library/characters/{lib_id}").json()["voice"]["voice_id"] == "ravi"
        client.post(f"{base(pid)}/voices/characters/tomato:set", json={"mode": "preset", "voice_id": "asha"})
        assert client.get(f"/api/v1/library/characters/{lib_id}").json()["voice"]["voice_id"] == "asha"
        listed = client.get("/api/v1/library/characters").json()
        assert next(c for c in listed if c["id"] == lib_id)["voice"]["voice_id"] == "asha"


def test_library_set_voice_python_api(tmp_path):
    from reelforge.library.service import get_voice, set_voice

    ctx, client = voice_world(tmp_path)
    with client:
        pid = cast_approved(client, ctx)
        lib_id = cast_item(client, pid, "tomato")["library_character_id"]
        assert get_voice(ctx, lib_id) is None
        v = {"mode": "preset", "model": "omnivoice", "voice_id": "ravi", "reference_path": None,
             "reference_sha256": None, "reference_text": "", "speed": 1.0, "language": "hi"}
        set_voice(ctx, lib_id, v)
        assert get_voice(ctx, lib_id) == v
        set_voice(ctx, lib_id, None)
        assert get_voice(ctx, lib_id) is None
