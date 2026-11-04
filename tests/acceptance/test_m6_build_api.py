"""m6 R1, R7, R9, R15, AC-3 (edit side), AC-14, AC-15: building the EDL, the assembly API, edits."""

from __future__ import annotations

import pytest
from m4_helpers import LINES
from m5_helpers import base, render_shot, shot
from m6_helpers import (
    asm_dir,
    build,
    edit,
    edit_ok,
    get_asm,
    get_edl,
    jobs_of,
    kinds,
    reel_world,
    take_id,
    until,
    voice_take_id,
    voiced_world,
    wait_preview,
)

BELOW = {"detail": "Approve the shots first."}


def _source_artifacts(w, pid):
    from rf_helpers import artifacts_of

    derived = {"preview", "final", "cover", "credits", "edl", "filtergraph"}
    return sorted(a.id for a in artifacts_of(w.ctx, pid) if a.kind not in derived)


def _non_preview_jobs(w, pid):
    from reelforge.db.models import Job
    from sqlalchemy import select

    with w.ctx.session_factory() as s:
        return sorted(
            j.id for j in s.scalars(select(Job).where(Job.project_id == pid)) if j.type != "assemble_preview"
        )


# build_edl ----------------------------------------------------------------------------


def test_build_edl_from_approved_takes_and_voice(tmp_path):
    from reelforge.assembly.build import build_edl, working_edl_path
    from m6_helpers import probe
    from m5_helpers import art_path

    with reel_world(tmp_path) as (w, pid):
        edl = build_edl(w.ctx, pid)
        assert [s.scene_id for s in edl.video] == ["s1", "s2", "s3", "s4", "s5"]
        assert edl.project_id == pid
        t = 0.0
        for i, s in enumerate(edl.video):
            assert s.artifact == take_id(w, pid, s.scene_id)
            assert s.in_s == 0 and s.transition_in_s == 0
            dur = float(probe(art_path(w, s.artifact))["video"]["duration"])
            assert s.out_s == pytest.approx(dur, abs=0.05) and s.source_duration_s == pytest.approx(dur, abs=0.05)
            assert edl.shot_start_s(i) == pytest.approx(t)
            t += s.out_s
        assert [d.scene_id for d in edl.dialogue] == ["s1", "s2", "s5"]
        for d in edl.dialogue:
            i = [s.scene_id for s in edl.video].index(d.scene_id)
            assert d.artifact == voice_take_id(w, pid, d.scene_id)
            assert d.offset_s == pytest.approx(edl.shot_start_s(i))
            assert 0 < d.duration_s and d.offset_s + d.duration_s <= edl.total_duration_s + 1e-6
            assert d.gain_db == 0.0
        assert [c.line_no for c in edl.captions] == [1, 2, 3]
        assert [c.scene_id for c in edl.captions] == ["s1", "s2", "s5"]
        for c, d in zip(edl.captions, edl.dialogue):
            assert c.text == LINES[c.scene_id] and c.style is None
            assert (c.start_s, c.end_s) == pytest.approx((d.offset_s, d.offset_s + d.duration_s))
        assert edl.captions[0].speaker == "Tamatar"
        assert edl.music.tracks == [] and edl.end_card.enabled is False and edl.caption_style == "auto"
        assert 10.0 <= edl.total_duration_s <= 16.0
        assert working_edl_path(w.ctx, pid) == asm_dir(w, pid) / "edl.json"


def test_build_edl_blocked_until_every_shot_is_approved(tmp_path):
    from reelforge.assembly.build import build_edl
    from reelforge.assembly.state import AssemblyError

    with voiced_world(tmp_path) as (w, pid):
        with pytest.raises(AssemblyError) as exc:
            build_edl(w.ctx, pid)
        assert exc.value.status == 409 and exc.value.message == "Approve all shots before exporting."


# gating -------------------------------------------------------------------------------


def test_assembly_endpoints_need_shots_approved(tmp_path):
    with voiced_world(tmp_path) as (w, pid):
        b = base(pid)
        calls = [
            w.client.get(f"{b}/assembly"),
            w.client.get(f"{b}/assembly/edl"),
            w.client.post(f"{b}/assembly:build", json={}),
            w.client.post(f"{b}/assembly:edit", json={"op": "set_caption_style", "style": "bold_pop"}),
            w.client.post(f"{b}/assembly:preview"),
            w.client.post(f"{b}/assembly:export", json={}),
            w.client.post(f"{b}/assembly:open-version", json={"version": 1}),
        ]
        for r in calls:
            assert r.status_code == 409 and r.json() == BELOW, r.request.url
        assert jobs_of(w, pid, "assemble_preview") == [] and jobs_of(w, pid, "assemble_final") == []


def test_unknown_project_is_404(tmp_path):
    with voiced_world(tmp_path) as (w, _):
        for r in (
            w.client.get("/api/v1/projects/nope/assembly"),
            w.client.post("/api/v1/projects/nope/assembly:build", json={}),
        ):
            assert r.status_code == 404 and r.json() == {"detail": "project not found"}


# assembly state and build endpoint ------------------------------------------------------


def test_state_before_build(tmp_path):
    with reel_world(tmp_path) as (w, pid):
        a = get_asm(w, pid)
        assert a["stage"] == "SHOTS_APPROVED" and a["blocked_reason"] is None
        assert a["edl"] is None and a["edl_hash"] is None and a["versions"] == []
        assert a["preview"]["state"] == "none" and a["export"]["state"] == "idle"
        assert [s["scene_id"] for s in a["shots"]] == ["s1", "s2", "s3", "s4", "s5"]
        for s in a["shots"]:
            assert [t["active"] for t in s["takes"]] == [True]
            assert s["takes"][0]["video_url"] == f"/media/{s['takes'][0]['id']}"
        assert {p["id"]: p["label"] for p in a["caption_presets"]}.items() >= {
            "bold_pop": "Bold pop", "clean_subtitle": "Clean subtitle", "hindi_devanagari": "Hindi Devanagari",
        }.items()
        assert a["licence_warnings"] == [] or isinstance(a["licence_warnings"], list)
        r = w.client.get(f"{base(pid)}/assembly/edl")
        assert r.status_code == 404 and r.json() == {"detail": "edl not built"}
        r = edit(w, pid, op="set_caption_style", style="bold_pop")
        assert r.status_code == 404 and r.json() == {"detail": "edl not built"}


def test_build_writes_working_edl_and_schedules_a_preview(tmp_path):
    from reelforge.assembly.build import build_edl
    from reelforge.assembly.edl import edl_hash, load_edl

    with reel_world(tmp_path) as (w, pid):
        a = build(w, pid)
        expected = build_edl(w.ctx, pid)
        assert a["edl"] == expected.model_dump(mode="json")
        assert a["edl_hash"] == edl_hash(expected)
        assert load_edl(asm_dir(w, pid) / "edl.json") == expected
        assert get_edl(w, pid) == a["edl"]
        assert a["preview"]["state"] in ("pending", "rebuilding", "up_to_date")
        done = wait_preview(w, pid)
        assert done["preview"]["url"].startswith("/media/") and done["preview"]["error"] is None
        assert len(jobs_of(w, pid, "assemble_preview")) == 1
        assert jobs_of(w, pid, "assemble_final") == []
        assert (asm_dir(w, pid) / "edls" / f"{a['edl_hash']}.json").is_file()


def test_build_keeps_edits_unless_forced(tmp_path):
    with reel_world(tmp_path) as (w, pid):
        build(w, pid)
        edit_ok(w, pid, op="trim", scene_id="s1", in_s=0.0, out_s=1.5)
        assert build(w, pid)["edl"]["video"][0]["out_s"] == 1.5
        assert build(w, pid, force=True)["edl"]["video"][0]["out_s"] > 1.5


# edits ----------------------------------------------------------------------------------


def test_trim_rounds_and_validates(tmp_path):
    with reel_world(tmp_path) as (w, pid):
        build(w, pid)
        out = edit_ok(w, pid, op="trim", scene_id="s2", in_s=0.123, out_s=1.987)
        v = out["assembly"]["edl"]["video"][1]
        assert (v["in_s"], v["out_s"]) == (0.12, 1.99) and isinstance(out["notes"], list)
        assert get_edl(w, pid)["video"][1]["out_s"] == 1.99
        r = edit(w, pid, op="trim", scene_id="s2", in_s=1.0, out_s=1.3)
        assert r.status_code == 422 and r.json() == {"detail": "A shot must be at least 0.5 s long."}
        src = get_edl(w, pid)["video"][1]["source_duration_s"]
        assert edit(w, pid, op="trim", scene_id="s2", in_s=0.0, out_s=src + 1.0).status_code == 422
        assert edit(w, pid, op="trim", scene_id="s2", in_s=-0.5, out_s=1.0).status_code == 422
        assert get_edl(w, pid)["video"][1]["out_s"] == 1.99


def test_trim_past_the_end_trims_dialogue_with_a_note(tmp_path):
    with reel_world(tmp_path) as (w, pid):
        build(w, pid)
        out = edit_ok(w, pid, op="trim", scene_id="s5", in_s=0.0, out_s=0.5)
        assert "Dialogue was trimmed to fit." in out["notes"]
        edl = out["assembly"]["edl"]
        total = sum(v["out_s"] - v["in_s"] for v in edl["video"])
        d = next(x for x in edl["dialogue"] if x["scene_id"] == "s5")
        assert d["offset_s"] + d["duration_s"] <= total + 1e-6


def test_reorder_moves_dialogue_with_its_shot(tmp_path):
    with reel_world(tmp_path) as (w, pid):
        before = build(w, pid)["edl"]
        order = ["s2", "s1", "s3", "s4", "s5"]
        after = edit_ok(w, pid, op="reorder", scene_ids=order)["assembly"]["edl"]
        assert [v["scene_id"] for v in after["video"]] == order
        s2_len = before["video"][1]["out_s"] - before["video"][1]["in_s"]
        d = {x["scene_id"]: x for x in after["dialogue"]}
        assert d["s2"]["offset_s"] == pytest.approx(0.0, abs=1e-6)
        assert d["s1"]["offset_s"] == pytest.approx(s2_len, abs=0.02)
        assert 400 <= edit(w, pid, op="reorder", scene_ids=["s1", "s2"]).status_code < 500
        assert [v["scene_id"] for v in get_edl(w, pid)["video"]] == order


def test_swap_take_uses_another_take_of_the_scene(tmp_path):
    with reel_world(tmp_path) as (w, pid):
        original = take_id(w, pid, "s2")
        _, job = render_shot(w, pid, "s2", "reroll")
        assert job.status == "succeeded", job.error
        assert w.client.post(f"{base(pid)}/shots/s2:approve").status_code == 200
        assert w.client.get(base(pid)).json()["stage"] == "SHOTS_APPROVED"
        current = take_id(w, pid, "s2")
        assert current != original
        edl = build(w, pid)["edl"]
        assert edl["video"][1]["artifact"] == current
        out = edit_ok(w, pid, op="swap_take", scene_id="s2", take_id=original)["assembly"]["edl"]
        v = out["video"][1]
        assert v["artifact"] == original and v["in_s"] == 0
        assert v["out_s"] == pytest.approx(v["source_duration_s"])
        r = edit(w, pid, op="swap_take", scene_id="s2", take_id=take_id(w, pid, "s1"))
        assert r.status_code == 404 and r.json() == {"detail": "take not found"}


def test_crossfade_is_capped_with_a_note(tmp_path):
    with reel_world(tmp_path) as (w, pid):
        build(w, pid)
        edit_ok(w, pid, op="trim", scene_id="s1", in_s=0.0, out_s=0.6)
        edit_ok(w, pid, op="trim", scene_id="s2", in_s=0.0, out_s=0.6)
        out = edit_ok(w, pid, op="set_transition", scene_id="s2", seconds=0.5)
        assert "Crossfade shortened to fit" in out["notes"]
        assert out["assembly"]["edl"]["video"][1]["transition_in_s"] == pytest.approx(0.3)
        out = edit_ok(w, pid, op="set_transition", scene_id="s3", seconds=0.2)
        assert out["notes"] == [] and out["assembly"]["edl"]["video"][2]["transition_in_s"] == pytest.approx(0.2)
        assert edit(w, pid, op="set_transition", scene_id="s3", seconds=0.6).status_code == 422


def test_nudge_dialogue_is_absolute_and_bounded(tmp_path):
    with reel_world(tmp_path) as (w, pid):
        build(w, pid)
        out = edit_ok(w, pid, op="nudge_dialogue", scene_id="s1", offset_s=1.0)
        d = next(x for x in out["assembly"]["edl"]["dialogue"] if x["scene_id"] == "s1")
        assert d["offset_s"] == pytest.approx(1.0)
        msg = "Dialogue cannot start before 0 or after the end of the reel."
        for bad in (-0.1, 999.0):
            r = edit(w, pid, op="nudge_dialogue", scene_id="s1", offset_s=bad)
            assert r.status_code == 422 and r.json() == {"detail": msg}
        d = next(x for x in get_edl(w, pid)["dialogue"] if x["scene_id"] == "s1")
        assert d["offset_s"] == pytest.approx(1.0)


def test_caption_text_edit_changes_edl_not_audio(tmp_path):
    """AC-14: the EDL and the rendered .ass change, and no voice take or job is created."""
    with reel_world(tmp_path, preview_debounce_s=0.05) as (w, pid):
        build(w, pid)
        wait_preview(w, pid)
        edit_ok(w, pid, op="set_caption_style", style="clean_subtitle")
        wait_preview(w, pid)
        src_before = _source_artifacts(w, pid)
        jobs_before = _non_preview_jobs(w, pid)
        out = edit_ok(w, pid, op="set_caption_text", scene_id="s1", text="Naya caption yahan")
        edl = out["assembly"]["edl"]
        assert next(c for c in edl["captions"] if c["scene_id"] == "s1")["text"] == "Naya caption yahan"
        assert get_edl(w, pid)["captions"][0]["text"] == "Naya caption yahan"
        done = until(
            lambda: (a := get_asm(w, pid))["preview"]["state"] == "up_to_date" and a["edl_hash"] == out["assembly"]["edl_hash"] and a,
            what="preview of the edited EDL",
        )
        assert done["preview"]["state"] == "up_to_date"
        passes = [p for p in asm_dir(w, pid).glob("work/preview-*/captions.ass")]
        assert any("Naya caption yahan" in p.read_text() for p in passes)
        assert _source_artifacts(w, pid) == src_before
        assert _non_preview_jobs(w, pid) == jobs_before
        assert "final" not in kinds(w, pid)


def test_caption_style_is_validated(tmp_path):
    with reel_world(tmp_path) as (w, pid):
        build(w, pid)
        for style in ("auto", "bold_pop", "clean_subtitle", "hindi_devanagari"):
            out = edit_ok(w, pid, op="set_caption_style", style=style)
            assert out["assembly"]["edl"]["caption_style"] == style
        assert edit(w, pid, op="set_caption_style", style="comic_sans").status_code == 422
        assert get_edl(w, pid)["caption_style"] == "hindi_devanagari"


# debounce and preview-only rebuild ---------------------------------------------------------


def test_edits_are_debounced_into_one_preview_and_never_export(tmp_path):
    """R9 / AC-3: a burst of edits makes one preview job after the debounce and no final job."""
    from reelforge.assembly.edl import edl_hash, load_edl

    with reel_world(tmp_path, preview_debounce_s=1.0) as (w, pid):
        build(w, pid)
        wait_preview(w, pid)
        n0 = len(jobs_of(w, pid, "assemble_preview"))
        for i in range(3):
            out = edit_ok(w, pid, op="nudge_dialogue", scene_id="s1", offset_s=0.1 * (i + 1))
        pv = out["assembly"]["preview"]
        assert pv["state"] == "pending" and 0 < pv["rebuild_in_s"] <= 1.0
        assert len(jobs_of(w, pid, "assemble_preview")) == n0
        done = until(
            lambda: (a := get_asm(w, pid))["preview"]["state"] == "up_to_date"
            and a["edl_hash"] == out["assembly"]["edl_hash"]
            and a,
            what="debounced preview",
        )
        assert len(jobs_of(w, pid, "assemble_preview")) == n0 + 1
        assert jobs_of(w, pid, "assemble_final") == []
        job = jobs_of(w, pid, "assemble_preview")[-1]
        assert job.payload == {"stage": "assembly", "kind": "preview", "edl_hash": done["edl_hash"]}
        snap = asm_dir(w, pid) / "edls" / f"{done['edl_hash']}.json"
        assert edl_hash(load_edl(snap)) == done["edl_hash"]


def test_an_edit_replaces_the_preview_with_a_new_one(tmp_path):
    """A finished rebuild after an edit serves a new preview file."""
    with reel_world(tmp_path, preview_debounce_s=0.05) as (w, pid):
        build(w, pid)
        first = wait_preview(w, pid)["preview"]["url"]
        edit_ok(w, pid, op="set_caption_style", style="bold_pop")
        a = wait_preview(w, pid)
        assert a["preview"]["url"] != first and a["preview"]["url"].startswith("/media/")
