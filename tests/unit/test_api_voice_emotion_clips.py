"""Emotion clips beyond the acceptance cases: a missing file and a replaced clip."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "acceptance"))

from m6b_helpers import (  # noqa: E402  # pyright: ignore[reportMissingImports]
    base,
    emo_world,
    generate,
    get_voices,
    project_with_presets,
    set_emotion,
    wav_bytes,
)
from rf_helpers import artifacts_of  # noqa: E402  # pyright: ignore[reportMissingImports]


def _clone(client, pid):
    files = {"file": ("n.wav", wav_bytes(6.0), "audio/wav")}
    client.post(
        f"{base(pid)}/voices/characters/tomato:upload-reference",
        files=files,
        data={"reference_text": "neutral text"},
    )
    client.post(
        f"{base(pid)}/voices/characters/tomato:set",
        json={"mode": "cloned", "reference_text": "neutral text"},
    )


def test_a_missing_clip_file_fails_the_line_without_a_silent_fallback(tmp_path):
    ctx, client, _ = emo_world(tmp_path)
    with client:
        pid = project_with_presets(client, ctx)
        _clone(client, pid)
        url = f"{base(pid)}/voices/characters/tomato/emotion-clips/sad:upload"
        r = client.post(
            url,
            files={"file": ("c.wav", wav_bytes(6.0), "audio/wav")},
            data={"transcript": "udaas"},
        )
        assert r.status_code == 201
        clip = next(a for a in artifacts_of(ctx, pid) if a.kind == "voice_emotion_reference")
        ctx.store.absolute_path(clip).unlink()
        assert set_emotion(client, pid, "s1", "sad").status_code == 200
        _, job = generate(client, ctx, pid, mode="lines", lines=["s1"])
        assert job.status == "failed"
        assert (
            job.error
            == "The sad reference clip for Tamatar is missing. Upload it again or remove it."
        )
        assert get_voices(client, pid)["lines"][0]["takes"] == []


def test_removing_a_clip_that_does_not_exist_is_a_no_op(tmp_path):
    ctx, client, _ = emo_world(tmp_path)
    with client:
        pid = project_with_presets(client, ctx)
        _clone(client, pid)
        r = client.post(f"{base(pid)}/voices/characters/tomato/emotion-clips/fear:remove")
        assert r.status_code == 200 and "emotion_clips" not in r.json()
