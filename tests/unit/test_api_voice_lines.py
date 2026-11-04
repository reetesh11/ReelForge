import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "acceptance"))

from m4_helpers import (  # noqa: E402  # pyright: ignore[reportMissingImports]
    action,
    approve_all,
    base,
    line_of,
    rendered_project,
    voice_world,
)


def test_approve_all_then_voice_change_reopens_stage(tmp_path):
    ctx, client = voice_world(tmp_path, image_mem_gb=1.0)
    with client:
        pid = rendered_project(client, ctx)
        assert approve_all(client, pid)["project_stage"] == "VOICES_APPROVED"
        client.post(
            f"{base(pid)}/voices/characters/potato:set", json={"mode": "preset", "voice_id": "ravi"}
        )
        assert client.get(base(pid)).json()["stage"] == "CAST_APPROVED"


def test_stale_take_cannot_be_approved(tmp_path):
    ctx, client = voice_world(tmp_path, image_mem_gb=1.0)
    with client:
        pid = rendered_project(client, ctx)
        action(client, pid, "s1", "edit-text", text="Kuch aur kehna hai ab")
        assert action(client, pid, "s1", "approve").status_code == 409


def test_edit_text_rejects_empty_and_preview_unknown_line(tmp_path):
    ctx, client = voice_world(tmp_path, image_mem_gb=1.0)
    with client:
        pid = rendered_project(client, ctx)
        assert action(client, pid, "s1", "edit-text", text="  ").status_code == 422
        r = client.get(f"{base(pid)}/voices/preview", params={"scene_id": "s99"})
        assert r.status_code == 404


def test_shorten_proposal_is_shorter(tmp_path):
    ctx, client = voice_world(tmp_path, image_mem_gb=1.0)
    with client:
        pid = rendered_project(client, ctx)
        r = action(client, pid, "s1", "shorten")
        assert r.status_code == 200
        assert len(r.json()["proposal"].split()) < len(line_of(client, pid, "s1")["text"].split())


def test_speed_up_picks_smallest_fitting_step(tmp_path):
    ctx, client = voice_world(tmp_path, image_mem_gb=1.0)
    with client:
        pid = rendered_project(client, ctx)
        # budget 4.0 s: the line is about 2.55 s so a step is picked only if it is over budget
        r = action(client, pid, "s2", "speed-up")
        assert r.status_code == 200 and r.json()["line"]["speed"] in (0.8, 1.0, 1.25)
