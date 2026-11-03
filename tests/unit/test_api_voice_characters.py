import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "acceptance"))

from m4_helpers import base, cast_approved, get_voices, voice_world, wav_bytes  # noqa: E402  # pyright: ignore[reportMissingImports]


def test_voice_model_roundtrip_and_validation(tmp_path):
    ctx, client = voice_world(tmp_path)
    with client:
        assert client.get("/api/v1/voice-model").json()["voice_model"] == "omnivoice"
        assert client.put("/api/v1/voice-model", json={"voice_model": "kokoro"}).status_code == 200
        bad = client.put("/api/v1/voice-model", json={"voice_model": "x"})
        assert bad.status_code == 422 and "omnivoice" in bad.text


def test_set_clear_and_upload(tmp_path):
    ctx, client = voice_world(tmp_path)
    with client:
        pid = cast_approved(client, ctx)
        url = f"{base(pid)}/voices/characters/tomato"
        assert client.post(url + ":set", json={"mode": "recorded"}).json()["mode"] == "recorded"
        r = client.post(
            url + ":upload-reference",
            files={"file": ("a.wav", wav_bytes(3.0), "audio/wav")},
            data={"reference_text": "namaste"},
        )
        assert r.status_code == 201 and r.json()["clip_seconds"] > 2.5
        assert client.post(url + ":clear").json() == {"voice": None}
        assert get_voices(client, pid)["characters"][0]["voice"] is None
