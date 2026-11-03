import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "acceptance"))

from m4_helpers import (  # noqa: E402  # pyright: ignore[reportMissingImports]
    base,
    cast_approved,
    generate,
    get_voices,
    set_presets,
    story_text,
    voice_world,
    wav_bytes,
)
from rf_helpers import wait_job  # noqa: E402  # pyright: ignore[reportMissingImports]

from reelforge.db.models import Artifact  # noqa: E402


def test_five_lines_in_one_job_and_progress_message(tmp_path):
    ctx, client = voice_world(tmp_path, image_mem_gb=1.0)
    with client:
        pid = cast_approved(client, ctx)
        set_presets(client, pid)
        job, done = generate(client, ctx, pid)
        assert done.status == "succeeded", done.error
        assert done.progress == 100
        res = ctx.queue.get(job["id"]).result
        assert res["completed"] == 5 and len(res["lines"]) == 5


def test_failing_line_does_not_stop_others(tmp_path):
    text = json.loads(story_text())
    text["scenes"][2]["line"] = "yeh [[fail]] hai"
    ctx, client = voice_world(tmp_path, image_mem_gb=1.0)
    with client:
        pid = cast_approved(client, ctx, text=json.dumps(text, ensure_ascii=False))
        set_presets(client, pid)
        job, done = generate(client, ctx, pid)
        assert done.status == "succeeded"
        res = ctx.queue.get(job["id"]).result
        assert res["lines"]["s3"]["status"] == "failed"
        by = {x["scene_id"]: x for x in get_voices(client, pid)["lines"]}
        assert by["s3"]["state"] == "failed" and by["s3"]["message"]
        assert by["s1"]["state"] == "ready"


def test_missing_reference_clip_fails_that_line(tmp_path):
    ctx, client = voice_world(tmp_path, image_mem_gb=1.0)
    with client:
        pid = cast_approved(client, ctx)
        client.post(
            f"{base(pid)}/voices/characters/potato:set", json={"mode": "preset", "voice_id": "asha"}
        )
        r = client.post(
            f"{base(pid)}/voices/characters/tomato:upload-reference",
            files={"file": ("c.wav", wav_bytes(6.0), "audio/wav")},
            data={"reference_text": "ek do teen"},
        )
        assert r.status_code == 201
        with ctx.session_factory() as s:
            ref = s.get(Artifact, r.json()["reference_url"].rsplit("/", 1)[1])
            assert ref is not None
        ctx.store.absolute_path(ref).unlink()
        job, done = generate(client, ctx, pid)
        assert done.status == "succeeded"
        res = ctx.queue.get(job["id"]).result
        assert (
            res["lines"]["s1"]["error"] == "Reference clip for Tamatar is missing. Upload it again."
        )
        assert res["lines"]["s2"]["status"] == "done"


def test_cancel_keeps_written_takes_and_lease_released(tmp_path):
    ctx, client = voice_world(tmp_path, image_mem_gb=1.0)
    with client:
        pid = cast_approved(client, ctx)
        set_presets(client, pid)
        r = client.post(f"{base(pid)}/voices:generate", json={})
        jid = r.json()["id"]
        client.post(f"/api/v1/jobs/{jid}/cancel")
        done = wait_job(ctx, jid, {"succeeded", "failed", "cancelled"}, timeout=60)
        assert done.status in ("cancelled", "succeeded")
        assert ctx.lease.holder() is None


def test_memory_shortfall_names_voice_mem_gb(tmp_path):
    ctx, client = voice_world(tmp_path, image_mem_gb=1.0, available_gb=2.0, voice_mem_gb=4.0)
    with client:
        pid = cast_approved(client, ctx)
        set_presets(client, pid)
        _, done = generate(client, ctx, pid)
        assert done.status == "failed"
        assert done.error == (
            "Not enough free memory for voice: need 4.0 GB, have 2.0 GB. "
            "Lower voice_mem_gb or close other apps."
        )
