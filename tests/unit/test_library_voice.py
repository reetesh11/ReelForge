import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "acceptance"))

from m3_helpers import cast_item  # noqa: E402  # pyright: ignore[reportMissingImports]
from m4_helpers import base, cast_approved, voice_world, wav_bytes  # noqa: E402  # pyright: ignore[reportMissingImports]

from reelforge.library import service as library  # noqa: E402


def test_clip_copied_to_library_with_same_hash_and_served(tmp_path):
    ctx, client = voice_world(tmp_path)
    with client:
        pid = cast_approved(client, ctx)
        clip = wav_bytes(6.0)
        url = f"{base(pid)}/voices/characters/tomato"
        client.post(
            url + ":upload-reference",
            files={"file": ("c.wav", clip, "audio/wav")},
            data={"reference_text": "namaste dost"},
        )
        lib_id = cast_item(client, pid, "tomato")["library_character_id"]
        rec = client.get(f"/api/v1/library/characters/{lib_id}").json()
        served = client.get(rec["voice"]["reference_url"])
        assert hashlib.sha256(served.content).hexdigest() == hashlib.sha256(clip).hexdigest()
        assert rec["voice"]["clip_seconds"] > 5
        mirror = ctx.settings.data_root / "library" / "characters" / lib_id / "character.json"
        assert '"voice"' in mirror.read_text()


def test_clear_voice_removes_library_voice_and_variant_keeps_voice(tmp_path):
    ctx, client = voice_world(tmp_path)
    with client:
        pid = cast_approved(client, ctx)
        client.post(
            f"{base(pid)}/voices/characters/tomato:set", json={"mode": "preset", "voice_id": "ravi"}
        )
        lib_id = cast_item(client, pid, "tomato")["library_character_id"]
        variant = library.make_variant(ctx, lib_id)
        copied = library.get_voice(ctx, variant.id)
        assert copied is not None and copied["voice_id"] == "ravi"
        client.post(f"{base(pid)}/voices/characters/tomato:clear")
        assert library.get_voice(ctx, lib_id) is None
        assert "voice" not in client.get(f"/api/v1/library/characters/{lib_id}").json()
