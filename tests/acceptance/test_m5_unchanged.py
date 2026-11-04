"""m5 AC-14: behaviour that must not change (ltx check details, doctor key, memory defaults, LLM)."""

from __future__ import annotations

import asyncio
import json

from m3_helpers import approved_project, gen_and_approve, new_world

M1_JOB_KEYS = {
    "id", "project_id", "type", "status", "priority", "heavy", "mem_need_gb", "attempts", "progress",
    "message", "error", "pid", "exit_code", "peak_rss_mb", "command", "payload", "created_at",
    "started_at", "finished_at",
}


def test_ltx_check_keeps_m1_details(tmp_path):
    from reelforge.adapters.ltx import LtxAdapter

    assert LtxAdapter(None).check().detail == "ltx-2-mlx path is not configured"
    missing = tmp_path / "none"
    assert LtxAdapter(missing).check().detail == f"ltx-2-mlx project not found at {missing}"
    proj = tmp_path / "p"
    proj.mkdir()
    assert LtxAdapter(proj).check().detail == f"ltx-2-mlx has no virtual environment in {proj}"
    assert LtxAdapter(None).check().name == "ltx"


def test_doctor_ltx_key_position_and_severity(tmp_path):
    from reelforge.config import Settings
    from reelforge.doctor import CHECKS, check_ltx

    assert list(CHECKS).index("ltx") == 3
    res = check_ltx(Settings(data_root=tmp_path / "d"))
    assert res.name == "ltx" and res.status == "fail" and res.severity == "blocking"
    assert res.detail == "ltx-2-mlx path is not configured"


def test_memory_defaults_and_existing_llm_schemas_unchanged():
    from reelforge.adapters.mock_llm import MockLlm
    from reelforge.config import Settings

    s = Settings()
    assert (s.image_mem_gb, s.voice_mem_gb) == (6.0, 4.0)
    msgs = [{"role": "user", "content": "Character name: Tamatar\nLook: a red tomato"}]
    out = asyncio.run(MockLlm().chat(msgs, schema={"properties": {"bible_line": {}}}))
    assert json.loads(out) == {"bible_line": "Character: Tamatar. Look: a red tomato."}


def test_jobs_list_keeps_m1_keys_for_cast_jobs(tmp_path):
    ctx, client, _ = new_world(tmp_path)
    with client:
        pid = approved_project(client)
        gen_and_approve(client, ctx, pid, "tomato", seed=1)
        jobs = client.get("/api/v1/jobs").json()
        assert jobs
        for j in jobs:
            assert set(j) - {"result"} == M1_JOB_KEYS
