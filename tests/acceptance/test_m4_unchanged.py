"""m4 AC-14: behaviour that must not change (M1 adapter check, doctor registry, job and library shapes)."""

from __future__ import annotations

from m3_helpers import cast_item, gen_and_approve, new_world
from m3_helpers import approved_project

M1_JOB_KEYS = {
    "id", "project_id", "type", "status", "priority", "heavy", "mem_need_gb", "attempts", "progress",
    "message", "error", "pid", "exit_code", "peak_rss_mb", "command", "payload", "created_at",
    "started_at", "finished_at",
}


def test_mlx_audio_check_keeps_m1_details(tmp_path):
    from reelforge.adapters.mlx_audio import MlxAudioAdapter

    assert MlxAudioAdapter(None).check().detail == "mlx-audio path is not configured"
    missing = tmp_path / "none"
    assert MlxAudioAdapter(missing).check().detail == f"mlx-audio project not found at {missing}"
    proj = tmp_path / "p"
    proj.mkdir()
    assert MlxAudioAdapter(proj).check().detail == f"mlx-audio has no virtual environment in {proj}"
    (proj / ".venv").mkdir()
    rep = MlxAudioAdapter(proj).check()
    assert rep.ok and rep.detail == f"mlx-audio at {proj}"


def test_doctor_registry_names_unchanged():
    from reelforge.doctor import CHECKS

    assert list(CHECKS) == ["arm64", "binaries_native", "ffmpeg_filters", "ltx", "mlx_audio",
                            "draw_things", "ollama", "ports", "disk", "memory", "licenses"]


def test_jobs_list_keeps_m1_keys_without_result(tmp_path):
    ctx, client, _ = new_world(tmp_path)
    with client:
        pid = approved_project(client)
        gen_and_approve(client, ctx, pid, "tomato", seed=1)
        jobs = client.get("/api/v1/jobs").json()
        assert jobs
        for j in jobs:
            assert set(j) - {"result"} == M1_JOB_KEYS, set(j) ^ M1_JOB_KEYS
            assert j.get("result", {}) is not None


def test_library_character_without_voice_has_no_voice_key(tmp_path):
    ctx, client, _ = new_world(tmp_path)
    with client:
        pid = approved_project(client)
        gen_and_approve(client, ctx, pid, "tomato", seed=1)
        lib_id = cast_item(client, pid, "tomato")["library_character_id"]
        assert "voice" not in client.get(f"/api/v1/library/characters/{lib_id}").json()
        assert all("voice" not in c for c in client.get("/api/v1/library/characters").json())


def test_models_toml_keeps_other_models():
    from pathlib import Path

    from reelforge.models_registry import load_models

    reg = load_models(Path(__file__).resolve().parents[2] / "src" / "reelforge" / "models.toml")
    assert reg.get("image").id == "flux_1_kontext_dev_q8p.ckpt"
    assert reg.get("video").id == "dgrauet/ltx-2.3-mlx-q4"
    assert reg.get("llm").id == "qwen3:8b"
