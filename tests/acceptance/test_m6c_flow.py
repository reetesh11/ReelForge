"""m6c R6, R9, R14, AC-4 (EDL times), AC-7, AC-11, AC-16: cues through the EDL, preview and export."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from m5_helpers import base
from m6_helpers import asm_dir, export_ok, get_asm, get_edl, jobs_of, loudness, wait_preview
from m6c_helpers import (
    TERMINAL,
    at,
    audio_reel_world,
    audio_url,
    cue,
    cue_out,
    generated,
    get_audio,
    jobs_of_type,
    light_world,
    put_cue,
    stale_audio,
    take_artifacts,
)
from rf_helpers import wait_job

FLOW = [
    cue("m1", "music", at("s1"), end=at("s5", at_="scene_end"), prompt="festive", duck=True),
    cue("fx1", "sfx", at("s2", 1.0), duration=1.5, prompt="gong slam"),
    cue("amb1", "ambience", at("s1"), duration=6.0, prompt="crowd"),
    cue("hush", "silence", at("s4"), end=at("s4", at_="scene_end")),
    cue("f1", "music", at("s3"), duration=2.0, source="file"),
]
DEFAULT_MIX = {"duck_db": 9.0, "attack_s": 0.15, "release_s": 0.4, "silence_fade_s": 0.08}


def _generate_three(w, pid):
    for cid in ("m1", "fx1", "amb1"):
        generated(w.client, w.ctx, pid, cid)


def _preview_mix(w, pid):
    r = w.client.post(audio_url(pid, ":preview-mix"))
    assert r.status_code == 202, r.text
    assert r.json()["type"] == "assemble_preview"
    assert wait_job(w.ctx, r.json()["id"], TERMINAL, timeout=120).status == "succeeded"
    return wait_preview(w, pid)


def test_preview_mix_needs_the_shots_approved(tmp_path):
    with light_world(tmp_path, FLOW) as (ctx, client, pid):
        r = client.post(audio_url(pid, ":preview-mix"))
        assert r.status_code == 409 and r.json()["detail"] == "Approve the shots first."
        assert jobs_of_type(ctx, pid, "assemble_preview") == []


def test_cues_reach_the_edl_with_absolute_times_and_the_preview_mix_renders_them(tmp_path):
    from reelforge.assembly.edl import Edl

    with audio_reel_world(tmp_path, FLOW) as (w, pid):
        _generate_three(w, pid)
        before = len(jobs_of(w, pid, "assemble_final"))
        _preview_mix(w, pid)
        raw = get_edl(w, pid)
        edl = Edl.model_validate(raw)
        assert [a.cue_id for a in edl.audio] == ["m1", "fx1", "amb1", "hush"]  # f1 has no take
        assert edl.mix.model_dump() == DEFAULT_MIX
        starts = {s.scene_id: edl.shot_start_s(i) for i, s in enumerate(edl.video)}
        lens = {s.scene_id: s.out_s - s.in_s for s in edl.video}
        a = {x.cue_id: x for x in edl.audio}
        assert a["m1"].start_s == pytest.approx(starts["s1"], abs=0.01)
        assert a["m1"].end_s == pytest.approx(starts["s5"] + lens["s5"], abs=0.01)
        assert a["fx1"].start_s == pytest.approx(starts["s2"] + 1.0, abs=0.01)
        assert a["fx1"].end_s == pytest.approx(starts["s2"] + 2.5, abs=0.01)
        assert a["amb1"].end_s - a["amb1"].start_s == pytest.approx(6.0, abs=0.01)
        assert a["hush"].start_s == pytest.approx(starts["s4"], abs=0.01)
        assert a["hush"].end_s == pytest.approx(starts["s4"] + lens["s4"], abs=0.01)
        assert a["hush"].artifact is None and a["hush"].kind == "silence"
        assert a["m1"].duck is True and a["fx1"].duck is False
        assert (a["m1"].gain_db, a["fx1"].gain_db, a["amb1"].gain_db) == (-12.0, -6.0, -18.0)
        asm = get_asm(w, pid)
        assert asm["audio_skipped"] == 1 and "audio_stale" not in asm
        assert len(jobs_of(w, pid, "assemble_final")) == before
        # no export folder is made by a preview
        assert not list(asm_dir(w, pid).glob("v[0-9][0-9][0-9]"))


def test_a_cue_with_no_picked_take_is_left_out_and_counted(tmp_path):
    with audio_reel_world(tmp_path, FLOW) as (w, pid):
        generated(w.client, w.ctx, pid, "fx1")
        _preview_mix(w, pid)
        from reelforge.assembly.edl import Edl

        edl = Edl.model_validate(get_edl(w, pid))
        assert [x.cue_id for x in edl.audio] == ["fx1", "hush"]
        assert get_asm(w, pid)["audio_skipped"] == 3


def test_changing_the_mix_marks_the_assembly_audio_stale_until_it_is_refreshed(tmp_path):
    from reelforge.audio.build import build_audio_section, refresh_audio

    with audio_reel_world(tmp_path, FLOW) as (w, pid):
        _generate_three(w, pid)
        _preview_mix(w, pid)
        assert "audio_stale" not in get_asm(w, pid)
        body = next(c for c in json.loads(json.dumps(FLOW)) if c["id"] == "fx1")
        assert put_cue(w.client, pid, {**body, "gain_db": -2.0}).status_code == 200
        assert get_asm(w, pid)["audio_stale"] is True
        assert stale_audio(w.client, pid) == set()
        refreshed = refresh_audio(w.ctx, pid)
        assert refreshed is not None
        cues, mix, skipped = build_audio_section(w.ctx, pid, refreshed)
        assert refreshed.audio == cues and refreshed.mix == mix and skipped == 1
        assert next(c for c in cues if c.cue_id == "fx1").gain_db == -2.0
        assert "audio_stale" not in get_asm(w, pid)
        assert w.client.put(audio_url(pid, "/settings"), json={"duck_db": 12.0}).status_code == 200
        assert get_asm(w, pid)["audio_stale"] is True


def test_refresh_audio_does_nothing_without_a_working_edl(tmp_path):
    from reelforge.audio.build import refresh_audio

    with light_world(tmp_path, FLOW) as (ctx, client, pid):
        assert refresh_audio(ctx, pid) is None


def _export(w, pid):
    r = w.client.post(f"{base(pid)}/assembly:export", json={"accept_licence_warning": True})
    assert r.status_code == 202, r.text
    job = wait_job(w.ctx, r.json()["id"], TERMINAL, timeout=180)
    assert job.status == "succeeded", job.error
    return asm_dir(w, pid) / "v001"


def test_the_full_path_exports_with_cues_and_credits(tmp_path):
    """AC-11: cues, generation, mix and export on the mock backend. The autouse network guard
    in conftest.py fails the test on any outbound connection."""
    with audio_reel_world(tmp_path, FLOW) as (w, pid):
        _generate_three(w, pid)
        v1 = _export(w, pid)
        credits = json.loads((v1 / "credits.json").read_text())
        ids = sorted(c["cue_id"] for c in credits if "cue_id" in c)
        assert ids == ["amb1", "fx1", "m1"]
        for c in credits:
            if "cue_id" in c:
                assert set(c) == {"cue_id", "kind", "model", "version", "licence"} and c["licence"]
        edl = json.loads((v1 / "edl.json").read_text())
        assert [x["cue_id"] for x in edl["audio"]] == ["m1", "fx1", "amb1", "hush"]
        assert (v1 / "final.filtergraph.txt").read_text().strip()


def test_a_reel_with_cues_is_normalised_to_about_minus_14_lufs(tmp_path):
    """AC-16: the existing two-pass loudnorm still holds for a reel with cues."""
    with audio_reel_world(tmp_path, FLOW) as (w, pid):
        _generate_three(w, pid)
        v1 = _export(w, pid)
        lufs, peak = loudness(v1 / "final.mp4")
        assert lufs == pytest.approx(-14.0, abs=1.5) and peak <= -0.9


def _tree(folder: Path) -> dict[str, str]:
    return {
        str(p.relative_to(folder)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(folder.rglob("*"))
        if p.is_file()
    }


def test_editing_a_cue_after_an_export_starts_no_job_and_keeps_the_earlier_version(tmp_path):
    with audio_reel_world(tmp_path, FLOW) as (w, pid):
        _generate_three(w, pid)
        v1 = _export(w, pid)
        before = _tree(v1)
        jobs_before = {t: len(jobs_of_type(w.ctx, pid, t)) for t in ("gen_audio_cue", "assemble_preview", "assemble_final")}
        import time

        time.sleep(1.1)
        body = next(c for c in json.loads(json.dumps(FLOW)) if c["id"] == "fx1")
        assert put_cue(w.client, pid, {**body, "prompt": "a gong, but bigger"}).status_code == 200
        assert stale_audio(w.client, pid) == {("fx1", "audio_take")}
        assert cue_out(w.client, pid, "m1")["state"] == "ready"
        assert cue_out(w.client, pid, "amb1")["state"] == "ready"
        assert {t: len(jobs_of_type(w.ctx, pid, t)) for t in jobs_before} == jobs_before
        assert v1.is_dir() and _tree(v1) == before
        assert len(take_artifacts(w.ctx, pid, "fx1")) == 1


def test_a_failed_generation_leaves_the_earlier_take_picked(tmp_path):
    from rf_helpers import CountingAdapter

    class Flaky(CountingAdapter):
        fail = False

        async def run(self, task, out_dir, progress, cancel, *, ctx_job_id=None):
            if self.fail and task.kind == "audio":
                from reelforge.adapters.base import AdapterError

                raise AdapterError("model exploded")
            return await super().run(task, out_dir, progress, cancel, ctx_job_id=ctx_job_id)

    holder: dict[str, Flaky] = {}

    def factory(settings):
        holder["a"] = Flaky(settings)
        return holder["a"]

    with light_world(tmp_path, FLOW, adapter=factory) as (ctx, client, pid):
        generated(client, ctx, pid, "fx1")
        first = take_artifacts(ctx, pid, "fx1")[0]
        holder["a"].fail = True
        r = client.post(audio_url(pid, "/cues/fx1:generate"))
        assert r.status_code == 202
        assert wait_job(ctx, r.json()["id"], TERMINAL, timeout=60).status == "failed"
        out = cue_out(client, pid, "fx1")
        assert out["picked_take_id"] == first.id and len(out["takes"]) == 1
        assert out["job"]["status"] == "failed" and out["job"]["error"]
