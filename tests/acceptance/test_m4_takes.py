"""m4 AC-1, AC-2, AC-9, AC-10, AC-11, AC-12 and R10-R14: takes, approval, frames, staleness, memory."""

from __future__ import annotations

import math
import time

import pytest
from m4_helpers import (
    LINES,
    action,
    approve_all,
    base,
    cast_approved,
    generate,
    get_voices,
    line_of,
    read_wav,
    rendered_project,
    set_presets,
    story_text,
    voice_world,
    wav_seconds,
)
from rf_helpers import create_project, wait_job
from sqlalchemy import select
from story_helpers import put

IDS = list(LINES)


def _active(line):
    act = [t for t in line["takes"] if t["active"]]
    assert len(act) == 1, line["takes"]
    return act[0]


def _scene_row(ctx, pid, sid):
    from reelforge.db.models import Scene

    with ctx.session_factory() as s:
        return s.scalars(select(Scene).where(Scene.project_id == pid, Scene.story_key == sid)).one()


# generation job ----------------------------------------------------------------

def test_generate_missing_job_shape_and_story_order(tmp_path):
    ctx, client = voice_world(tmp_path, voice_mem_gb=3.5)
    with client:
        pid = cast_approved(client, ctx)
        set_presets(client, pid)
        job, done = generate(client, ctx, pid)
        assert job["type"] == "gen_voice_take" and job["heavy"] is True
        assert job["payload"]["stage"] == "voices" and job["mem_need_gb"] == 3.5
        assert done.status == "succeeded", done.error
        res = ctx.queue.get(job["id"]).result
        assert res["scene_ids"] == IDS and res["completed"] == 5 and res["total"] == 5
        assert res["elapsed_s"] >= 0 and res["skipped"] == []
        assert {k: v["status"] for k, v in res["lines"].items()} == dict.fromkeys(IDS, "done")
        v = get_voices(client, pid)
        assert v["total"] == 5 and v["approved_count"] == 0 and v["stale_count"] == 0
        assert v["job"]["id"] == job["id"]
        for ln in v["lines"]:
            assert ln["state"] == "ready" and len(ln["takes"]) == 1 and ln["language"] == "hi"
            t = _active(ln)
            assert t["duration_s"] > 0 and t["take_no"] == 1
            audio = client.get(t["audio_url"])
            assert audio.status_code == 200
            assert wav_seconds(audio.content) == pytest.approx(t["duration_s"], abs=0.1)
            assert read_wav(audio.content)[1] == 48000
        again = client.post(f"{base(pid)}/voices:generate", json={})
        assert again.status_code == 409 and again.json() == {"detail": "Nothing to generate."}


def test_generate_needs_cast_and_known_lines(tmp_path):
    ctx, client = voice_world(tmp_path)
    with client:
        early = create_project(client, "early")["id"]
        put(client, early, story_text())
        assert client.post(f"{base(early)}/voices:generate", json={}).status_code == 409
        pid = cast_approved(client, ctx)
        set_presets(client, pid)
        r = client.post(f"{base(pid)}/voices:generate", json={"mode": "lines", "lines": ["s99"]})
        assert r.status_code == 404 and r.json() == {"detail": "line not found"}


def test_line_without_voice_is_skipped_with_message(tmp_path):
    ctx, client = voice_world(tmp_path)
    with client:
        pid = cast_approved(client, ctx)
        client.post(f"{base(pid)}/voices/characters/tomato:set", json={"mode": "preset", "voice_id": "ravi"})
        _, job = generate(client, ctx, pid)
        assert job.status == "succeeded", job.error
        by = {x["scene_id"]: x for x in get_voices(client, pid)["lines"]}
        assert by["s1"]["state"] == "ready" and by["s3"]["state"] == "ready"
        assert by["s2"]["state"] == "no_voice" and by["s2"]["message"] == "Pick a voice for Aloo"
        assert by["s2"]["takes"] == []


# AC-1 ------------------------------------------------------------------------

def test_retake_new_active_and_shot_length_uses_active_take(tmp_path):
    from reelforge.voice.frames import frames_for

    ctx, client = voice_world(tmp_path)
    with client:
        pid = rendered_project(client, ctx)
        first = _active(line_of(client, pid, "s2"))
        r = action(client, pid, "s2", "set-timing", speed=1.25)
        assert r.status_code == 200, r.text
        _, job = generate(client, ctx, pid, mode="lines", lines=["s2"])
        assert job.status == "succeeded", job.error
        ln = line_of(client, pid, "s2")
        assert len(ln["takes"]) == 2
        second = _active(ln)  # the new take is the active one
        assert second["id"] != first["id"] and second["take_no"] == 2 and second["seed"] != first["seed"]
        assert second["duration_s"] < first["duration_s"] - 0.1
        assert all(len(line_of(client, pid, s)["takes"]) == 1 for s in IDS if s != "s2")

        r = action(client, pid, "s2", "approve")
        assert r.status_code == 200, r.text
        line = r.json()["line"]
        assert line["duration_s"] == pytest.approx(second["duration_s"], abs=1e-6)
        assert line["frames"] == frames_for(second["duration_s"])
        assert line["frames"] != frames_for(first["duration_s"])
        row = _scene_row(ctx, pid, "s2")
        assert row.frames == line["frames"]
        assert row.duration_s == pytest.approx(second["duration_s"], abs=1e-6)

        r = action(client, pid, "s2", "select-take", take_id=first["id"])
        assert r.status_code == 200 and r.json()["line"]["state"] == "ready"
        assert _active(r.json()["line"])["id"] == first["id"]
        r = action(client, pid, "s2", "approve")
        assert r.json()["line"]["frames"] == frames_for(first["duration_s"])
        assert action(client, pid, "s2", "select-take", take_id="nope").status_code == 404


# AC-9 ------------------------------------------------------------------------

@pytest.mark.parametrize(
    "body,msg",
    [
        ({"speed": 0.79}, "speed must be between 0.8 and 1.25"),
        ({"speed": 1.26}, "speed must be between 0.8 and 1.25"),
        ({"pause_before": -0.1}, "pause_before must be between 0 and 1 seconds"),
        ({"pause_before": 1.1}, "pause_before must be between 0 and 1 seconds"),
        ({"pause_after": -0.5}, "pause_after must be between 0 and 1 seconds"),
        ({"pause_after": 1.01}, "pause_after must be between 0 and 1 seconds"),
    ],
)
def test_set_timing_rejects_out_of_range(tmp_path, body, msg):
    ctx, client = voice_world(tmp_path)
    with client:
        pid = rendered_project(client, ctx)
        before = line_of(client, pid, "s1")
        r = action(client, pid, "s1", "set-timing", **body)
        assert r.status_code == 422 and r.json() == {"detail": msg}
        after = line_of(client, pid, "s1")
        assert (after["speed"], after["pause_before"], after["pause_after"]) == (
            before["speed"], before["pause_before"], before["pause_after"])


def test_set_timing_boundaries_and_pauses_in_duration(tmp_path):
    from reelforge.voice.frames import frames_for

    ctx, client = voice_world(tmp_path)
    with client:
        pid = rendered_project(client, ctx)
        for body in ({"speed": 0.8}, {"speed": 1.25}, {"pause_before": 0, "pause_after": 1}, {"pause_before": 1}):
            assert action(client, pid, "s1", "set-timing", **body).status_code == 200, body
        r = action(client, pid, "s3", "set-timing", speed=1.0, pause_before=0.5, pause_after=0.25)
        assert r.status_code == 200
        t = _active(line_of(client, pid, "s3"))
        line = action(client, pid, "s3", "approve").json()["line"]
        assert line["duration_s"] == pytest.approx(t["duration_s"] + 0.75, abs=1e-6)
        assert line["frames"] == frames_for(t["duration_s"] + 0.75)
        assert _scene_row(ctx, pid, "s3").duration_s == pytest.approx(t["duration_s"] + 0.75, abs=1e-6)


def test_set_timing_reopens_approved_line(tmp_path):
    ctx, client = voice_world(tmp_path)
    with client:
        pid = rendered_project(client, ctx)
        action(client, pid, "s1", "approve")
        r = action(client, pid, "s1", "set-timing", pause_after=0.4)
        assert r.json()["line"]["state"] != "approved" and r.json()["approved_count"] == 0


# AC-11 -----------------------------------------------------------------------

def test_voices_approved_only_when_every_line_approved(tmp_path):
    ctx, client = voice_world(tmp_path)
    with client:
        pid = rendered_project(client, ctx)
        for i, sid in enumerate(IDS[:-1], start=1):
            r = action(client, pid, sid, "approve")
            assert r.status_code == 200, r.text
            assert r.json()["project_stage"] == "CAST_APPROVED"
            assert (r.json()["approved_count"], r.json()["total"]) == (i, 5)
        r = action(client, pid, "s5", "approve")
        assert r.json()["project_stage"] == "VOICES_APPROVED" and r.json()["approved_count"] == 5
        assert client.get(f"/api/v1/projects/{pid}").json()["stage"] == "VOICES_APPROVED"
        assert action(client, pid, "s5", "approve").json()["approved_count"] == 5  # idempotent
        stages = {s["key"]: s for s in client.get(f"/api/v1/projects/{pid}/stages").json()["stages"]}
        assert stages["voices"]["state"] == "approved"


def test_approve_without_take_is_409_and_unknown_line_404(tmp_path):
    ctx, client = voice_world(tmp_path)
    with client:
        pid = cast_approved(client, ctx)
        set_presets(client, pid)
        r = action(client, pid, "s1", "approve")
        assert r.status_code == 409 and r.json() == {"detail": "This line has no take yet."}
        r = action(client, pid, "s99", "approve")
        assert r.status_code == 404 and r.json() == {"detail": "line not found"}


def test_edit_text_reopens_only_that_line_and_leaves_stage(tmp_path):
    ctx, client = voice_world(tmp_path)
    with client:
        pid = rendered_project(client, ctx)
        approve_all(client, pid)
        assert client.get(f"/api/v1/projects/{pid}").json()["stage"] == "VOICES_APPROVED"
        jobs_before = len(client.get("/api/v1/jobs").json())
        r = action(client, pid, "s3", "edit-text", text="Bilkul naya vakya hai yeh ab")
        assert r.status_code == 200, r.text
        assert r.json()["project_stage"] == "CAST_APPROVED" and r.json()["approved_count"] == 4
        assert r.json()["line"]["text"] == "Bilkul naya vakya hai yeh ab"
        assert len(client.get("/api/v1/jobs").json()) == jobs_before  # nothing regenerates
        v = get_voices(client, pid)
        by = {x["scene_id"]: x for x in v["lines"]}
        assert by["s3"]["state"] == "stale"
        assert all(by[s]["state"] == "approved" for s in IDS if s != "s3")
        assert v["approved_count"] == 4


# AC-2 / R13 -------------------------------------------------------------------

def test_text_change_stales_only_that_line_then_regenerate_stale(tmp_path):
    ctx, client = voice_world(tmp_path)
    with client:
        pid = rendered_project(client, ctx)
        approve_all(client, pid)
        old_take = _active(line_of(client, pid, "s2"))
        new_text = "Ek alag baat kehni hai mujhe"
        assert action(client, pid, "s2", "edit-text", text=new_text).status_code == 200
        v = get_voices(client, pid)
        assert v["stale_count"] == 1
        by = {x["scene_id"]: x for x in v["lines"]}
        assert by["s2"]["shot_length_stale"] is True
        assert by["s2"]["takes"][0]["stale"] is True
        for s in IDS:
            if s != "s2":
                assert by[s]["shot_length_stale"] is False, s
                assert all(t["stale"] is False for t in by[s]["takes"]), s
        assert new_text in client.get(f"{base(pid)}/story").json()["yaml_text"]

        job, done = generate(client, ctx, pid, mode="stale")
        assert done.status == "succeeded", done.error
        assert ctx.queue.get(job["id"]).result["scene_ids"] == ["s2"]
        v = get_voices(client, pid)
        by = {x["scene_id"]: x for x in v["lines"]}
        assert v["stale_count"] == 0 and by["s2"]["shot_length_stale"] is False
        assert len(by["s2"]["takes"]) == 2 and _active(by["s2"])["id"] != old_take["id"]
        assert _active(by["s2"])["stale"] is False
        assert v["approved_count"] == 4
        assert action(client, pid, "s2", "approve").json()["project_stage"] == "VOICES_APPROVED"
        assert client.post(f"{base(pid)}/voices:generate", json={"mode": "stale"}).status_code == 409


def test_changing_character_voice_stales_their_lines_only(tmp_path):
    ctx, client = voice_world(tmp_path)
    with client:
        pid = rendered_project(client, ctx)
        approve_all(client, pid)
        r = client.post(f"{base(pid)}/voices/characters/tomato:set", json={"mode": "preset", "voice_id": "asha"})
        assert r.status_code == 200
        by = {x["scene_id"]: x for x in get_voices(client, pid)["lines"]}
        for s in ("s1", "s3", "s5"):  # tomato speaks the odd scenes
            assert by[s]["state"] != "approved", s
        for s in ("s2", "s4"):
            assert by[s]["state"] == "approved", s


# line fitting -----------------------------------------------------------------

def test_over_budget_flag_speed_up_and_extend_scene(tmp_path):
    ctx, client = voice_world(tmp_path)
    with client:
        pid = rendered_project(client, ctx, text=story_text(duration=1.0))
        ln = line_of(client, pid, "s1")
        assert ln["over_budget"]["budget_s"] == 1.0 and ln["over_budget"]["line_s"] > 1.0

        r = action(client, pid, "s1", "speed-up")
        assert r.status_code == 200, r.text
        assert r.json()["line"]["speed"] == 1.25
        assert r.json()["message"] == "Even at 1.25x this is too long."

        line_s = line_of(client, pid, "s2")["duration_s"]
        stage = client.get(f"/api/v1/projects/{pid}").json()["stage"]
        r = action(client, pid, "s2", "extend-scene")
        assert r.status_code == 200, r.text
        assert not line_of(client, pid, "s2").get("over_budget")
        expected = math.ceil(line_s * 2) / 2
        assert f"duration: {expected}" in client.get(f"{base(pid)}/story").json()["yaml_text"]
        assert get_voices(client, pid)["stale_count"] == 0
        assert client.get(f"/api/v1/projects/{pid}").json()["stage"] == stage


def test_shorten_changes_nothing(tmp_path):
    ctx, client = voice_world(tmp_path)
    with client:
        pid = rendered_project(client, ctx)
        before = line_of(client, pid, "s1")
        r = action(client, pid, "s1", "shorten")
        assert r.status_code in (200, 503)
        if r.status_code == 200:
            assert isinstance(r.json()["proposal"], str) and r.json()["proposal"]
        else:
            assert r.json() == {"detail": "The language model isn't available. Edit the text yourself."}
        assert line_of(client, pid, "s1")["text"] == before["text"]


# recorded upload -----------------------------------------------------------------

def test_upload_recording_becomes_active_take(tmp_path):
    from m3_helpers import png_bytes
    from m4_helpers import wav_bytes

    ctx, client = voice_world(tmp_path)
    with client:
        pid = rendered_project(client, ctx)
        url = f"{base(pid)}/voices/lines/s1:upload-recording"
        bad = client.post(url, files={"file": ("x.wav", png_bytes(), "audio/wav")})
        assert bad.status_code == 415 and bad.json() == {"detail": "That file isn't an audio clip."}
        r = client.post(url, files={"file": ("mine.wav", wav_bytes(2.0, amp=0.1), "audio/wav")})
        assert r.status_code == 201, r.text
        ln = r.json()["line"]
        t = _active(ln)
        assert len(ln["takes"]) == 2 and abs(t["duration_s"] - 2.0) < 0.3
        assert read_wav(client.get(t["audio_url"]).content)[1] == 48000


# previews ---------------------------------------------------------------------

def test_preview_stitches_active_takes_with_pauses(tmp_path):
    ctx, client = voice_world(tmp_path)
    with client:
        pid = cast_approved(client, ctx)
        set_presets(client, pid)
        none = client.get(f"{base(pid)}/voices/preview")
        assert none.status_code == 404 and none.json() == {"detail": "No takes to play yet."}
        assert action(client, pid, "s1", "set-timing", pause_before=0.5, pause_after=0.5).status_code == 200
        _, job = generate(client, ctx, pid, mode="lines", lines=["s1", "s2"])
        assert job.status == "succeeded", job.error
        t1, t2 = (_active(line_of(client, pid, s))["duration_s"] for s in ("s1", "s2"))
        r = client.get(f"{base(pid)}/voices/preview")
        assert r.status_code == 200 and r.headers["content-type"].startswith("audio/wav")
        assert r.headers["x-skipped-lines"] == "3"
        assert wav_seconds(r.content) == pytest.approx(t1 + t2 + 1.0, abs=0.2)
        one = client.get(f"{base(pid)}/voices/preview", params={"scene_id": "s2"})
        assert one.status_code == 200 and wav_seconds(one.content) == pytest.approx(t2, abs=0.2)
        assert get_voices(client, pid)["approved_count"] == 0  # changes no state


def test_preset_preview_job(tmp_path):
    ctx, client = voice_world(tmp_path)
    with client:
        pid = cast_approved(client, ctx)
        r = client.post(f"{base(pid)}/voices/presets/asha:preview")
        assert r.status_code == 202, r.text
        assert r.json()["type"] == "gen_voice_take" and r.json()["payload"].get("preview")
        done = wait_job(ctx, r.json()["id"], {"succeeded", "failed", "cancelled"}, timeout=60)
        assert done.status == "succeeded", done.error
        url = done.result["audio_url"]
        assert url.startswith("/media/") and client.get(url).status_code == 200
        assert client.post(f"{base(pid)}/voices/presets/nobody:preview").status_code == 404


# AC-10 ---------------------------------------------------------------------------

def test_memory_shortfall_fails_naming_voice_mem_gb(tmp_path):
    ctx, client = voice_world(tmp_path, available_gb=1.2, voice_mem_gb=4.0)
    with client:
        pid = cast_approved(client, ctx)
        set_presets(client, pid)
        _, job = generate(client, ctx, pid)
        want = ("Not enough free memory for voice: need 4.0 GB, have 1.2 GB. "
                "Lower voice_mem_gb or close other apps.")
        assert job.status == "failed" and job.error == want
        assert get_voices(client, pid)["lines"][0]["takes"] == []


def test_enough_memory_runs_and_unloads_ollama_first(tmp_path):
    unloads: list[float] = []

    async def unload():
        unloads.append(time.monotonic())

    ctx, client = voice_world(tmp_path, available_gb=5.0, voice_mem_gb=4.0, unload=unload)
    with client:
        pid = cast_approved(client, ctx)
        set_presets(client, pid)
        n = len(unloads)
        _, job = generate(client, ctx, pid)
        assert job.status == "succeeded", job.error
        assert len(unloads) > n  # Ollama unloaded for the heavy voice job
