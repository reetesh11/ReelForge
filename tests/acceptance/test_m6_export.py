"""m6 R10-R13, R16, AC-6, AC-8, AC-9, AC-10, AC-13: jobs, export, versions, licences, media."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path

import pytest
from m5_helpers import art_path, artifact, base, shot
from m6_helpers import (
    FINAL_STEPS,
    PREVIEW_STEPS,
    asm_dir,
    build,
    edit_ok,
    export,
    export_ok,
    get_asm,
    get_edl,
    jobs_of,
    probe,
    reel_world,
    wait_preview,
)
from rf_helpers import artifacts_of, wait_job

TERMINAL = {"succeeded", "failed", "cancelled"}


def _tree_hashes(folder: Path) -> dict[str, str]:
    return {
        str(p.relative_to(folder)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(folder.rglob("*"))
        if p.is_file()
    }


def _models_with_licence(tmp_path: Path, image_licence: str) -> Path:
    from reelforge.config import PACKAGED_MODELS

    text = PACKAGED_MODELS.read_text()
    new = re.sub(
        r'(\[models\.image\].*?\nlicense = )"[^"]*"', lambda m: f'{m.group(1)}"{image_licence}"', text, count=1, flags=re.S
    )
    assert new != text or image_licence in text
    p = tmp_path / "models.toml"
    p.write_text(new)
    return p


# job types ---------------------------------------------------------------------------


def test_assembly_jobs_are_registered_light_jobs():
    from reelforge.assembly.jobs import FINAL_JOB, PREVIEW_JOB
    from reelforge.jobs.worker import HANDLERS

    assert (PREVIEW_JOB, FINAL_JOB) == ("assemble_preview", "assemble_final")
    assert PREVIEW_JOB in HANDLERS and FINAL_JOB in HANDLERS


def test_preview_job_reports_steps_and_takes_no_gpu_lease(tmp_path):
    from reelforge.assembly.ffmpeg import has_filter

    with reel_world(tmp_path) as (w, pid):
        build(w, pid)
        wait_preview(w, pid)
        r = w.client.post(f"{base(pid)}/assembly:preview")
        assert r.status_code == 202, r.text
        out = r.json()
        assert out["type"] == "assemble_preview" and out["heavy"] is False and out["mem_need_gb"] == 0
        assert out["payload"]["stage"] == "assembly" and out["payload"]["kind"] == "preview"
        job = wait_job(w.ctx, out["id"], TERMINAL, timeout=90)
        assert job.status == "succeeded", job.error
        res = job.result
        assert set(res) == {"edl_hash", "artifact_id", "filtergraph_artifact_id", "captions_burned", "step_runs"}
        assert res["captions_burned"] is has_filter("subtitles")
        assert res["step_runs"] == {n: 1 for n in PREVIEW_STEPS}
        a = artifact(w, res["artifact_id"])
        assert a.kind == "preview" and probe(art_path(w, a.id))["video"]["width"] == 540
        assert artifact(w, res["filtergraph_artifact_id"]).kind == "filtergraph"
        assert job.progress == 100 and job.message == "Encoding (8 of 8)"
        assert get_asm(w, pid)["preview"]["url"] == f"/media/{res['artifact_id']}"


def test_scheduler_enqueues_a_snapshotted_preview(tmp_path):
    from reelforge.assembly.edl import edl_hash, load_edl

    with reel_world(tmp_path) as (w, pid):
        build(w, pid)
        wait_preview(w, pid)
        job = w.ctx.previews.enqueue_now(pid)
        assert job.type == "assemble_preview" and job.heavy is False
        h = job.payload["edl_hash"]
        assert job.payload == {"stage": "assembly", "kind": "preview", "edl_hash": h}
        assert edl_hash(load_edl(asm_dir(w, pid) / "edl.json")) == h
        assert (asm_dir(w, pid) / "edls" / f"{h}.json").is_file()
        assert wait_job(w.ctx, job.id, TERMINAL, timeout=90).status == "succeeded"


# licences ------------------------------------------------------------------------------


def test_credits_cover_every_model_used(tmp_path):
    from reelforge.assembly.build import build_edl
    from reelforge.assembly.publish import collect_credits, licence_warnings

    with reel_world(tmp_path) as (w, pid):
        credits = collect_credits(w.ctx, pid, build_edl(w.ctx, pid))
        assert all(set(c) == {"model", "version", "licence"} for c in credits)
        models = [c["model"] for c in credits]
        assert len(models) == len(set(models))
        assert {"dgrauet/ltx-2.3-mlx-q4", "mlx-community/OmniVoice-bfloat16"} <= set(models)
        warn = licence_warnings(credits)
        assert warn and all(c in credits for c in warn)
        assert all("non-commercial" in c["licence"].lower() or not c["licence"].strip() for c in warn)
        assert "LTX-2 Community License" not in [c["licence"] for c in warn]


def test_licence_check_blocks_export_until_accepted(tmp_path):
    """AC-6 / R11: a non-commercial model makes export answer 409 with the warnings."""
    with reel_world(tmp_path) as (w, pid):
        build(w, pid)
        wait_preview(w, pid)
        asm = get_asm(w, pid)
        assert asm["licence_warnings"], "the default image model is non-commercial"
        r = export(w, pid, accept=False)
        assert r.status_code == 409
        body = r.json()
        assert body["detail"] == "Licence check before export"
        assert body["licence_warnings"] == asm["licence_warnings"]
        assert all(set(x) == {"model", "version", "licence"} for x in body["licence_warnings"])
        assert any("non-commercial" in x["licence"].lower() for x in body["licence_warnings"])
        assert jobs_of(w, pid, "assemble_final") == []
        r = export(w, pid, accept=True)
        assert r.status_code == 202 and r.json()["type"] == "assemble_final"
        assert r.json()["heavy"] is False and r.json()["mem_need_gb"] == 0
        assert wait_job(w.ctx, r.json()["id"], TERMINAL, timeout=120).status == "succeeded"


@pytest.mark.parametrize("licence, warns", [("MIT", False), ("", True)])
def test_export_warning_follows_the_licence_text(tmp_path, licence, warns):
    models = _models_with_licence(tmp_path, licence)
    with reel_world(tmp_path, models_path=models) as (w, pid):
        build(w, pid)
        wait_preview(w, pid)
        assert bool(get_asm(w, pid)["licence_warnings"]) is warns
        r = export(w, pid, accept=False)
        assert (r.status_code == 409) is warns, r.text
        if not warns:
            assert r.status_code == 202
            assert wait_job(w.ctx, r.json()["id"], TERMINAL, timeout=120).status == "succeeded"
        else:
            assert any(x["licence"] == "" for x in r.json()["licence_warnings"])


# export and versions ---------------------------------------------------------------------


def test_export_writes_a_versioned_reel_with_credits(tmp_path):
    """AC-1, AC-6, AC-10, R10, R15: the whole mock pipeline, with the network guard active."""
    from reelforge.assembly.edl import load_edl
    from reelforge.db.models import ReelVersion
    from sqlalchemy import select

    with reel_world(tmp_path) as (w, pid):
        build(w, pid)
        wait_preview(w, pid)
        job = export_ok(w, pid)
        res = job.result
        assert set(res) == {"edl_hash", "version", "reel_artifact_id", "step_runs"}
        assert res["version"] == 1 and res["step_runs"] == {n: 1 for n in FINAL_STEPS}
        v1 = asm_dir(w, pid) / "v001"
        for name in ("final.mp4", "final.filtergraph.txt", "cover.jpg", "credits.json", "edl.json", "captions.ass"):
            assert (v1 / name).is_file(), name
        p = probe(v1 / "final.mp4")
        assert (p["video"]["width"], p["video"]["height"]) == (1080, 1920) and p["video"]["profile"] == "High"
        edl = load_edl(v1 / "edl.json")
        assert float(p["format"]["duration"]) == pytest.approx(edl.total_duration_s, abs=0.05)
        assert (v1 / "cover.jpg").read_bytes()[:2] == b"\xff\xd8"
        cover = probe(v1 / "cover.jpg")["video"]
        assert cover["width"] * 16 == cover["height"] * 9
        credits = json.loads((v1 / "credits.json").read_text())
        assert isinstance(credits, list) and credits
        assert all(set(c) == {"model", "version", "licence"} for c in credits)
        assert {"dgrauet/ltx-2.3-mlx-q4", "mlx-community/OmniVoice-bfloat16"} <= {c["model"] for c in credits}
        with w.ctx.session_factory() as s:
            row = s.scalars(select(ReelVersion).where(ReelVersion.project_id == pid)).one()
            assert row.version == 1 and row.credits == credits
            assert row.final_artifact_id == res["reel_artifact_id"] and row.edl_artifact_id
            edl_art = row.edl_artifact_id
        assert artifact(w, res["reel_artifact_id"]).kind == "final"
        assert artifact(w, edl_art).kind == "edl"
        assert {"cover", "credits", "filtergraph"} <= {a.kind for a in artifacts_of(w.ctx, pid)}
        assert w.client.get(base(pid)).json()["stage"] == "REEL_EXPORTED"
        stages = w.client.get(f"{base(pid)}/stages").json()["stages"]
        assert stages[-1]["key"] == "assembly" and stages[-1]["state"] == "approved"
        a = get_asm(w, pid)
        assert a["stage"] == "REEL_EXPORTED" and a["export"]["state"] == "idle"
        (ver,) = a["versions"]
        assert ver["version"] == 1 and ver["label"] == "Reel v1" and ver["missing"] is False
        assert ver["reel_url"] == f"/media/{res['reel_artifact_id']}" and ver["cover_url"].startswith("/media/")


def test_player_can_range_request_the_exported_file(tmp_path):
    """AC-8: 206 with Content-Range, 416 past the end, whole file on a malformed range."""
    with reel_world(tmp_path) as (w, pid):
        build(w, pid)
        job = export_ok(w, pid)
        mid = job.result["reel_artifact_id"]
        size = art_path(w, mid).stat().st_size
        r = w.client.get(f"/media/{mid}", headers={"Range": "bytes=0-99"})
        assert r.status_code == 206 and len(r.content) == 100
        assert r.headers["content-range"] == f"bytes 0-99/{size}" and r.headers["accept-ranges"] == "bytes"
        r = w.client.get(f"/media/{mid}", headers={"Range": f"bytes={size - 10}-"})
        assert r.status_code == 206 and len(r.content) == 10
        assert w.client.get(f"/media/{mid}", headers={"Range": f"bytes={size + 5}-"}).status_code == 416
        r = w.client.get(f"/media/{mid}", headers={"Range": "bytes=oops"})
        assert r.status_code == 200 and len(r.content) == size
        for kind_url in (get_asm(w, pid)["versions"][0]["cover_url"],):
            assert w.client.get(kind_url).status_code == 200


def test_second_export_makes_v2_and_leaves_v1_alone(tmp_path):
    """AC-9 / R12."""
    from reelforge.assembly.edl import load_edl

    with reel_world(tmp_path) as (w, pid):
        build(w, pid)
        export_ok(w, pid)
        asm = asm_dir(w, pid)
        before = _tree_hashes(asm / "v001")
        edl1 = get_edl(w, pid)
        edit_ok(w, pid, op="trim", scene_id="s5", in_s=0.0, out_s=1.5)
        job2 = export_ok(w, pid)
        assert job2.result["version"] == 2
        assert (asm / "v002" / "final.mp4").is_file() and (asm / "v002" / "edl.json").is_file()
        assert _tree_hashes(asm / "v001") == before
        assert load_edl(asm / "v002" / "edl.json").video[4].out_s == 1.5
        assert json.loads((asm / "v001" / "edl.json").read_text()) == edl1
        vs = get_asm(w, pid)["versions"]
        assert [(v["version"], v["label"]) for v in vs] == [(1, "Reel v1"), (2, "Reel v2")]
        # reopening v1 puts its EDL back as the working copy
        a = w.client.post(f"{base(pid)}/assembly:open-version", json={"version": 1})
        assert a.status_code == 200 and a.json()["edl"] == edl1
        assert get_edl(w, pid) == edl1 and json.loads((asm / "edl.json").read_text()) == edl1
        assert _tree_hashes(asm / "v001") == before
        a = w.client.post(f"{base(pid)}/assembly:open-version", json={"version": 2})
        assert a.status_code == 200 and a.json()["edl"]["video"][4]["out_s"] == 1.5


def test_open_version_errors(tmp_path):
    with reel_world(tmp_path) as (w, pid):
        build(w, pid)
        export_ok(w, pid)
        r = w.client.post(f"{base(pid)}/assembly:open-version", json={"version": 7})
        assert r.status_code == 404 and r.json() == {"detail": "version not found"}
        shutil.rmtree(asm_dir(w, pid) / "v001")
        assert get_asm(w, pid)["versions"][0]["missing"] is True
        r = w.client.post(f"{base(pid)}/assembly:open-version", json={"version": 1})
        assert r.status_code == 404 and r.json() == {"detail": "This version's files are missing."}


def test_export_while_one_is_running_returns_the_same_job(tmp_path):
    with reel_world(tmp_path) as (w, pid):
        build(w, pid)
        a = export(w, pid)
        b = export(w, pid)
        assert a.status_code == 202 and b.status_code == 202 and a.json()["id"] == b.json()["id"]
        assert wait_job(w.ctx, a.json()["id"], TERMINAL, timeout=120).status == "succeeded"
        assert len(jobs_of(w, pid, "assemble_final")) == 1
        assert [v["version"] for v in get_asm(w, pid)["versions"]] == [1]


def test_export_renders_the_edl_as_it_was_requested(tmp_path):
    with reel_world(tmp_path) as (w, pid):
        build(w, pid)
        requested = get_edl(w, pid)
        r = export(w, pid)
        assert r.status_code == 202
        edit_ok(w, pid, op="trim", scene_id="s1", in_s=0.0, out_s=1.0)
        assert wait_job(w.ctx, r.json()["id"], TERMINAL, timeout=120).status == "succeeded"
        assert json.loads((asm_dir(w, pid) / "v001" / "edl.json").read_text()) == requested
        assert get_edl(w, pid)["video"][0]["out_s"] == 1.0


def test_failed_export_names_the_step_and_changes_nothing(tmp_path):
    from reelforge.db.models import ReelVersion
    from sqlalchemy import select

    with reel_world(tmp_path) as (w, pid):
        build(w, pid)
        wait_preview(w, pid)
        art_path(w, shot(w, pid, "s2")["takes"][0]["id"]).unlink()
        r = export(w, pid)
        assert r.status_code == 202
        job = wait_job(w.ctx, r.json()["id"], TERMINAL, timeout=120)
        assert job.status == "failed"
        assert job.result == {"failed_step": "Preparing shots"}
        assert job.error == "A shot file is missing: s2"
        a = get_asm(w, pid)
        assert a["export"]["state"] == "failed" and a["export"]["failed_step"] == "Preparing shots"
        assert a["export"]["error"] == "A shot file is missing: s2" and a["versions"] == []
        assert w.client.get(base(pid)).json()["stage"] == "SHOTS_APPROVED"
        with w.ctx.session_factory() as s:
            assert list(s.scalars(select(ReelVersion))) == []
