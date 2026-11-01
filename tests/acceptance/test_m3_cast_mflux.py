"""AC-12 end to end: Draw Things unreachable, mflux selected, fake command, no shell."""

from __future__ import annotations

import asyncio
import json
import subprocess

from m3_helpers import approved_project, cast_item, fake_mflux, generate
from rf_helpers import free_port, make_client, make_ctx, make_settings


def test_generation_runs_through_mflux_when_draw_things_is_down(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise AssertionError("shell execution is forbidden")

    monkeypatch.setattr(asyncio, "create_subprocess_shell", boom)
    real_popen = subprocess.Popen

    def popen(*a, **k):
        assert not k.get("shell"), "shell=True is forbidden"
        return real_popen(*a, **k)

    monkeypatch.setattr(subprocess, "Popen", popen)

    cmd, log = fake_mflux(tmp_path)
    settings = make_settings(
        tmp_path,
        backend="real",
        image_fallback="mflux",
        mflux_command=cmd,
        drawthings_url=f"http://127.0.0.1:{free_port()}",
    )
    ctx = make_ctx(settings)
    client = make_client(ctx)
    with client:
        pid = approved_project(client)
        c = cast_item(client, pid, "tomato")
        assert c["state"] == "empty"
        body = client.get(f"/api/v1/projects/{pid}/cast").json()
        assert body["image_backend"]["mflux_available"] is True
        _, job = generate(client, ctx, pid, "tomato", seed=50, backend="mflux")
        assert job.status == "succeeded", job.error
        item = cast_item(client, pid, "tomato")
        assert [x["seed"] for x in item["candidates"]] == [50, 51, 52, 53]
        calls = [json.loads(ln) for ln in log.read_text().splitlines()]
        assert len(calls) == 4
        assert [a[a.index("--seed") + 1] for a in calls] == ["50", "51", "52", "53"]
        assert all(isinstance(a, list) and a[0] == "--model" for a in calls)
        assert all(a[a.index("--model") + 1] == item["candidates"][0]["model"] for a in calls)
