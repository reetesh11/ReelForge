"""m5 AC-3, AC-4, AC-6, AC-7, AC-8, AC-9, AC-10, AC-11 (shots), AC-12 (clips), R12 mock video."""

from __future__ import annotations

import math
import time

import pytest
from m3_helpers import png_bytes
from m4_helpers import action
from m5_helpers import (
    SIDS,
    TERMINAL,
    active_take,
    art_path,
    artifact,
    base,
    edit_action,
    ffprobe,
    frame,
    frames_approved,
    get_frames,
    get_shots,
    media_id,
    mp4_bytes,
    noisy_mp4_bytes,
    ready,
    render_all_shots,
    render_shot,
    scene_row,
    shot,
    shots_approved,
    voices_approved,
    wait_all,
    world,
)
from rf_helpers import artifacts_of, wait_job

OOM = "Killed, likely out of memory."


def _until(pred, timeout=20.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        v = pred()
        if v:
            return v
        time.sleep(0.05)
    raise AssertionError("condition not met in time")


# board and gating ---------------------------------------------------------------------

def test_shots_need_key_frames_approved(tmp_path):
    w = world(tmp_path)
    with w.client:
        pid = voices_approved(w)
        r = w.client.get(f"{base(pid)}/shots")
        assert r.status_code == 409 and r.json() == {"detail": "Approve the key frames first."}
        r = w.client.post(f"{base(pid)}/shots:render-all", json={"mode": "missing"})
        assert r.status_code == 409 and r.json() == {"detail": "Approve the key frames first."}
        frames_approved(w, pid)
        assert w.client.get(f"{base(pid)}/shots").status_code == 200


def test_board_types_sizes_frames_and_engine_on_mock(tmp_path):
    from reelforge.voice.frames import frames_for

    w = world(tmp_path)
    with w.client:
        pid = ready(w)
        board = get_shots(w, pid)
        assert board["engine"]["ok"] is True
        assert (board["total"], board["approved_count"], board["stale_count"]) == (5, 0, 0)
        assert board["queue"]["rows"] == [] and board["queue"]["paused"] is False
        types = {s["scene_id"]: s["shot_type"] for s in board["shots"]}
        assert types == {"s1": "talking", "s2": "talking", "s3": "action", "s4": "continue", "s5": "talking"}
        for s in board["shots"]:
            assert s["shot_type_auto"] == s["shot_type"] and s["quality"] == "draft"
            assert (s["width"], s["height"]) == (320, 576) and s["state"] == "no_shot" and s["takes"] == []
            row = scene_row(w, pid, s["scene_id"])
            want = row.frames if row.frames is not None else frames_for(3.0)
            assert s["frames"] == want and (want - 1) % 8 == 0
            assert s["shot_length_s"] == pytest.approx(want / 24, abs=0.01)
        assert shot(w, pid, "s4")["blockers"] == ["waiting_previous"]
        assert shot(w, pid, "s1")["blockers"] == []
        assert shot(w, pid, "s1")["frame_url"].startswith("/media/")


def test_overrides_and_quality_persist_and_stale_a_rendered_shot(tmp_path):
    w = world(tmp_path, shot_final_size="448x768")
    with w.client:
        pid = ready(w)
        r = w.client.post(f"{base(pid)}/shots/s3:set-quality", json={"quality": "final"})
        assert r.status_code == 200 and (r.json()["shot"]["width"], r.json()["shot"]["height"]) == (448, 768)
        r = w.client.post(f"{base(pid)}/shots/s1:set-type", json={"shot_type": "action"})
        assert r.json()["shot"]["shot_type"] == "action" and r.json()["shot"]["shot_type_auto"] == "talking"
        assert shot(w, pid, "s1")["shot_type"] == "action"  # persists
        assert shot(w, pid, "s3")["state"] == "no_shot"  # nothing rendered yet, so nothing is stale
        _, done = render_shot(w, pid, "s3")
        assert done.status == "succeeded", done.error
        assert w.adapter.of_job(done.id).params["width"] == 448 and w.adapter.of_job(done.id).params["height"] == 768
        r = w.client.post(f"{base(pid)}/shots/s3:set-quality", json={"quality": "draft"})
        assert r.json()["shot"]["state"] == "stale"
        r = w.client.post(f"{base(pid)}/shots/s3:set-type", json={"shot_type": "action"})
        assert r.status_code == 200


# AC-3, AC-8, R12 ------------------------------------------------------------------------

def test_talking_shot_inputs_frame_count_and_audio(tmp_path):
    w = world(tmp_path)
    with w.client:
        pid = ready(w)
        card = shot(w, pid, "s1")
        job, done = render_shot(w, pid, "s1")
        assert job["type"] == "gen_shot" and done.status == "succeeded", done.error
        assert done.payload["stage"] == "shots" and done.payload["shot_type"] == "talking"
        assert done.payload["quality"] == "draft" and done.heavy and done.mem_need_gb == w.settings.shot_mem_gb
        task = w.adapter.of_job(job["id"])
        key_frame = media_id(frame(w, pid, "s1")["takes"][0]["image_url"])
        voice = next(ln for ln in w.client.get(f"{base(pid)}/voices").json()["lines"] if ln["scene_id"] == "s1")
        voice_take = media_id(active_take(voice)["audio_url"])
        assert task.kind == "video" and task.params["mode"] == "a2v"
        assert [str(p) for p in task.input_paths] == [str(art_path(w, key_frame)), str(art_path(w, voice_take))]
        row = scene_row(w, pid, "s1")
        assert task.params["frames"] == row.frames == card["frames"] and (row.frames - 1) % 8 == 0
        assert (task.params["fps"], task.params["width"], task.params["height"]) == (24, 320, 576)
        assert task.model.id == w.ctx.registry.get("video").id
        assert done.result["inputs"] == [key_frame, voice_take] and done.result["frames"] == row.frames
        assert (done.result["width"], done.result["height"], done.result["shot_type"]) == (320, 576, "talking")
        assert done.result["render_s"] >= 0
        assert shot(w, pid, "s1")["motion_prompt"].strip() and shot(w, pid, "s1")["motion_prompt"] in task.prompt
        take = active_take(shot(w, pid, "s1"))
        assert take["inputs"] == [key_frame, voice_take] and take["quality"] == "draft"
        art = artifact(w, take["id"])
        assert art.kind == "shot" and art.owner_type == "scene" and art.owner_id == "s1"
        info = ffprobe(art_path(w, take["id"]))["streams"]
        video = next(s for s in info if s["codec_type"] == "video")
        assert (video["width"], video["height"]) == (320, 576) and int(video["nb_frames"]) == row.frames
        assert any(s["codec_type"] == "audio" for s in info)  # the talking take keeps its audio


def test_action_shot_has_no_audio_input_and_is_silent(tmp_path):
    w = world(tmp_path)
    with w.client:
        pid = ready(w)
        job, done = render_shot(w, pid, "s3")
        assert done.status == "succeeded", done.error
        task = w.adapter.of_job(job["id"])
        key_frame = media_id(frame(w, pid, "s3")["takes"][0]["image_url"])
        assert task.params["mode"] == "generate"
        assert [str(p) for p in task.input_paths] == [str(art_path(w, key_frame))]
        assert done.result["inputs"] == [key_frame]
        take = active_take(shot(w, pid, "s3"))
        streams = ffprobe(art_path(w, take["id"]))["streams"]
        assert [s["codec_type"] for s in streams] == ["video"]
        assert int(streams[0]["nb_frames"]) == 73  # 3.0 s scene, never written back: frames_for(3.0)


def test_last_frame_is_extracted_and_continue_shot_starts_from_it(tmp_path):
    w = world(tmp_path)
    with w.client:
        pid = ready(w)
        r = w.client.post(f"{base(pid)}/shots/s4:render")
        assert r.status_code == 409 and r.json() == {"detail": "Waiting for the previous shot."}
        _, done3 = render_shot(w, pid, "s3")
        assert done3.status == "succeeded"
        take3 = active_take(shot(w, pid, "s3"))
        lf = take3["last_frame_id"]
        assert lf and done3.result["last_frame_id"] == lf
        art = artifact(w, lf)
        assert art.kind == "last_frame" and art.owner_type == "scene" and art.owner_id == "s3"
        assert art_path(w, lf).read_bytes().startswith(b"\x89PNG")
        from reelforge.db.models import ArtifactInput
        from sqlalchemy import select

        with w.ctx.session_factory() as s:
            ins = list(s.scalars(select(ArtifactInput).where(ArtifactInput.artifact_id == lf)))
        assert [i.input_artifact_id for i in ins] == [take3["id"]]
        assert shot(w, pid, "s4")["blockers"] == []
        job4, done4 = render_shot(w, pid, "s4")
        assert done4.status == "succeeded", done4.error
        task = w.adapter.of_job(job4["id"])
        assert task.params["mode"] == "generate" and task.kind == "video"
        assert [str(p) for p in task.input_paths] == [str(art_path(w, lf))]
        assert active_take(shot(w, pid, "s4"))["inputs"] == [lf]


def test_continue_previous_frame_uses_last_frame_of_previous_shot(tmp_path):
    w = world(tmp_path)
    with w.client:
        pid = voices_approved(w)
        r = w.client.post(f"{base(pid)}/frames:generate", json={"mode": "scenes", "scenes": ["s1", "s2", "s3", "s5"]})
        wait_all(w, r.json()["jobs"])
        for sid in ("s1", "s2", "s3", "s5"):
            w.client.post(f"{base(pid)}/frames/{sid}:approve")
        w.client.post(f"{base(pid)}/frames/s4:continue-previous", json={"enabled": True})
        assert w.client.get(base(pid)).json()["stage"] == "FRAMES_APPROVED"
        _, done = render_shot(w, pid, "s3")
        assert done.status == "succeeded", done.error
        assert active_take(shot(w, pid, "s3"))["last_frame_id"]
        card = frame(w, pid, "s4")
        assert card["state"] == "continue_previous" and "waiting_for_previous_shot" not in card["notes"]


# AC-4 ------------------------------------------------------------------------------------

def test_reroll_adds_a_take_to_that_shot_only(tmp_path):
    w = world(tmp_path)
    with w.client:
        pid = ready(w)
        render_all_shots(w, pid)
        assert w.client.post(f"{base(pid)}/shots/s9:reroll").status_code == 404
        before = {s["scene_id"]: s for s in get_shots(w, pid)["shots"]}
        assert all(len(s["takes"]) == 1 and s["state"] == "ready" for s in before.values())
        rows_before = {
            a.id: (a.is_active, a.status) for a in artifacts_of(w.ctx, pid) if a.owner_id != "s2"
        }
        job, done = render_shot(w, pid, "s2", "reroll")
        assert done.status == "succeeded", done.error
        after = {s["scene_id"]: s for s in get_shots(w, pid)["shots"]}
        for sid in SIDS:
            if sid != "s2":
                assert after[sid]["takes"] == before[sid]["takes"] and after[sid]["state"] == before[sid]["state"]
        s2 = after["s2"]
        assert [t["take_no"] for t in s2["takes"]] == [1, 2] and active_take(s2)["take_no"] == 2
        old, new = s2["takes"]
        assert old["seed"] != new["seed"] and s2["motion_prompt"] == before["s2"]["motion_prompt"]
        assert s2["motion_prompt"].strip() and s2["motion_prompt"] in w.adapter.of_job(job["id"]).prompt
        assert w.adapter.of_job(job["id"]).seed == new["seed"] != old["seed"]
        rows_after = {
            a.id: (a.is_active, a.status) for a in artifacts_of(w.ctx, pid) if a.owner_id != "s2"
        }
        assert rows_after == rows_before  # the other four shots' cache entries are untouched
        r = w.client.post(f"{base(pid)}/shots/s2:select-take", json={"take_id": old["id"]})
        assert r.status_code == 200 and active_take(r.json()["shot"])["take_no"] == 1


def test_reroll_without_a_shot_is_409(tmp_path):
    w = world(tmp_path)
    with w.client:
        pid = ready(w)
        r = w.client.post(f"{base(pid)}/shots/s1:reroll")
        assert r.status_code == 409 and r.json() == {"detail": "This scene has no shot yet."}
        r = w.client.post(f"{base(pid)}/shots/s1:approve")
        assert r.status_code == 409 and r.json() == {"detail": "This scene has no shot yet."}


def test_save_prompt_and_rerender_use_the_edited_motion_prompt(tmp_path):
    w = world(tmp_path)
    with w.client:
        pid = ready(w)
        r = w.client.post(f"{base(pid)}/shots/s3:save-prompt", json={"prompt": "slow push in, steam rising"})
        assert r.status_code == 200 and r.json()["shot"]["motion_prompt"] == "slow push in, steam rising"
        r = w.client.post(f"{base(pid)}/shots/s3:save-prompt", json={"prompt": "pan left, confetti", "rerender": True})
        assert r.status_code == 200
        done = wait_job(w.ctx, r.json()["job"]["id"], TERMINAL)
        assert done.status == "succeeded" and "pan left, confetti" in w.adapter.of_job(done.id).prompt


# AC-6 -------------------------------------------------------------------------------------

@pytest.mark.parametrize("how", ["adapter_error", "exit137", "exit_minus9"])
def test_killed_shot_is_oom_once_and_offers_draft_retry(tmp_path, how):
    w = world(tmp_path)
    with w.client:
        pid = ready(w)
        w.client.post(f"{base(pid)}/shots/s3:set-quality", json={"quality": "final"})
        if how == "adapter_error":
            w.adapter.video_fail = OOM
        else:
            w.adapter.video_exit = 137 if how == "exit137" else -9
        before = len(w.adapter.video_tasks())
        job, done = render_shot(w, pid, "s3")
        assert done.status == "failed" and done.error == OOM
        assert len(w.adapter.video_tasks()) == before + 1  # not retried
        card = shot(w, pid, "s3")
        assert card["state"] == "failed" and card["message"] == OOM and card["oom"] is True
        assert card["can_retry_draft"] is True and card["takes"] == [] and card["quality"] == "final"
        w.adapter.video_fail = None
        w.adapter.video_exit = None
        r = w.client.post(f"{base(pid)}/shots/s3:retry-draft")
        assert r.status_code == 202
        done = wait_job(w.ctx, r.json()["id"], TERMINAL)
        assert done.status == "succeeded", done.error
        task = w.adapter.of_job(done.id)
        assert (task.params["width"], task.params["height"]) == (320, 576)
        card = shot(w, pid, "s3")
        assert card["quality"] == "draft" and len(card["takes"]) == 1 and card["takes"][0]["quality"] == "draft"
        assert "oom" not in card


def test_oom_at_draft_size_has_no_retry_button_flag(tmp_path):
    w = world(tmp_path)
    with w.client:
        pid = ready(w)
        w.adapter.video_fail = OOM
        _, done = render_shot(w, pid, "s3")
        assert done.status == "failed"
        card = shot(w, pid, "s3")
        assert card["oom"] is True and "can_retry_draft" not in card


def test_other_failure_is_not_oom(tmp_path):
    w = world(tmp_path)
    with w.client:
        pid = ready(w)
        w.adapter.video_fail = "ltx-2-mlx failed: bad frames"
        _, done = render_shot(w, pid, "s3")
        assert done.status == "failed"
        card = shot(w, pid, "s3")
        assert card["state"] == "failed" and card["message"] == "ltx-2-mlx failed: bad frames"
        assert "oom" not in card and card["takes"] == []


# AC-7 --------------------------------------------------------------------------------------

def test_shot_memory_shortfall_names_shot_mem_gb_then_runs_with_enough(tmp_path):
    w = world(tmp_path, shot_mem_gb=16.0)
    with w.client:
        pid = ready(w)
        w.set_gb(9.2)
        _, done = render_shot(w, pid, "s3")
        assert done.status == "failed"
        assert done.error == "Not enough free memory for a shot: need 16.0 GB (shot_mem_gb), have 9.2 GB"
        assert shot(w, pid, "s3")["takes"] == [] and not w.adapter.video_tasks()
        w.set_gb(20.0)
        before = len(w.unloads)
        _, ok = render_shot(w, pid, "s3")
        assert ok.status == "succeeded", ok.error
        assert len(w.unloads) > before  # Ollama unloaded before the heavy job


def test_shot_mem_gb_setting_is_used_not_image_mem_gb(tmp_path):
    w = world(tmp_path, shot_mem_gb=12.5, image_mem_gb=1.0)
    with w.client:
        pid = ready(w)
        w.set_gb(10.0)
        _, done = render_shot(w, pid, "s3")
        assert done.error == "Not enough free memory for a shot: need 12.5 GB (shot_mem_gb), have 10.0 GB"
        w.set_gb(13.0)
        assert render_shot(w, pid, "s3")[1].status == "succeeded"


def test_only_one_heavy_job_at_a_time(tmp_path):
    w = world(tmp_path)
    with w.client:
        pid = ready(w)
        w.adapter.sleep_s = 0.3
        w.adapter.max_active = 0
        r = w.client.post(f"{base(pid)}/shots:render-all", json={"mode": "missing"})
        assert all(d.status == "succeeded" for d in wait_all(w, r.json()["jobs"]))
        assert w.adapter.max_active == 1


# AC-9 --------------------------------------------------------------------------------------

def test_render_all_skips_blocked_and_keeps_story_order_and_batch(tmp_path):
    w = world(tmp_path)
    with w.client:
        pid = ready(w)
        r = w.client.post(f"{base(pid)}/shots:render-all", json={"mode": "missing"})
        assert r.status_code == 202, r.text
        jobs = r.json()["jobs"]
        assert [j["payload"]["scene_id"] for j in jobs] == ["s1", "s2", "s3", "s5"]
        assert r.json()["skipped"] == [{"scene_id": "s4", "reason": "waiting_previous"}]
        assert len({j["payload"]["batch_id"] for j in jobs}) == 1 and {j["payload"]["total"] for j in jobs} == {4}
        assert [j["payload"]["shot_type"] for j in jobs] == ["talking", "talking", "action", "talking"]
        wait_all(w, jobs)
        again = w.client.post(f"{base(pid)}/shots:render-all", json={"mode": "missing"})
        assert again.status_code == 202 and [j["payload"]["scene_id"] for j in again.json()["jobs"]] == ["s4"]
        wait_all(w, again.json()["jobs"])
        nothing = w.client.post(f"{base(pid)}/shots:render-all", json={"mode": "missing"})
        assert nothing.status_code == 409 and nothing.json() == {"detail": "Nothing to generate."}


def test_queue_estimates_total_reorder_pause_resume_and_remove(tmp_path):
    from reelforge.shots.state import DEFAULT_ESTIMATE_S

    w = world(tmp_path)
    with w.client:
        pid = ready(w)
        assert w.client.post(f"{base(pid)}/shots/queue:pause").json()["paused"] is True
        r = w.client.post(f"{base(pid)}/shots:render-all", json={"mode": "missing"})
        jobs = r.json()["jobs"]
        q = get_shots(w, pid)["queue"]
        assert q["paused"] is True and [row["scene_id"] for row in q["rows"]] == ["s1", "s2", "s3", "s5"]
        assert [row["position"] for row in q["rows"]] == [1, 2, 3, 4]
        assert all(row["status"] == "queued" and row["can_move"] for row in q["rows"])
        want = [DEFAULT_ESTIMATE_S[(row["shot_type"], row["quality"])] for row in q["rows"]]
        assert [row["estimate_s"] for row in q["rows"]] == want
        assert [row["estimate_text"] for row in q["rows"]] == [f"about {max(1, math.ceil(s / 60))} min" for s in want]
        assert q["total_shots"] == 4 and q["total_s"] == sum(want)
        assert q["total_text"] == f"4 shots - about {max(1, math.ceil(sum(want) / 60))} min - keep the Mac plugged in"
        time.sleep(0.6)  # paused: nothing may start
        assert all(w.ctx.queue.get(j["id"]).status == "queued" for j in jobs)
        assert not w.adapter.video_tasks()
        by_scene = {j["payload"]["scene_id"]: j["id"] for j in jobs}
        mv = w.client.post(f"{base(pid)}/shots/queue:move", json={"job_id": by_scene["s2"], "direction": "down"})
        assert mv.status_code == 200 and [row["scene_id"] for row in mv.json()["rows"]] == ["s1", "s3", "s2", "s5"]
        mv = w.client.post(f"{base(pid)}/shots/queue:move", json={"job_id": by_scene["s5"], "direction": "up"})
        assert [row["scene_id"] for row in mv.json()["rows"]] == ["s1", "s3", "s5", "s2"]
        rm = w.client.post(f"{base(pid)}/shots/s1:dequeue")
        assert rm.status_code == 200
        q = get_shots(w, pid)["queue"]
        assert [row["scene_id"] for row in q["rows"]] == ["s3", "s5", "s2"] and q["total_text"].startswith("3 shots - about ")
        assert w.client.post(f"{base(pid)}/shots/queue:resume").json()["paused"] is False
        for sid in ("s3", "s5", "s2"):
            assert wait_job(w.ctx, by_scene[sid], TERMINAL, timeout=60).status == "succeeded"
        order = [next(sc for sc, jid in by_scene.items() if jid == j) for j, _ in w.adapter.video_tasks()]
        assert order == ["s3", "s5", "s2"]  # the queue order is the run order
        assert w.ctx.queue.get(by_scene["s1"]).status == "cancelled"


def test_estimate_uses_recorded_render_times_for_same_type_and_size(tmp_path):
    from reelforge.shots.state import DEFAULT_ESTIMATE_S

    w = world(tmp_path)
    with w.client:
        pid = ready(w)
        _, d1 = render_shot(w, pid, "s1")
        _, d2 = render_shot(w, pid, "s2")
        times = [d1.result["render_s"], d2.result["render_s"]]
        mean = sum(times) / 2
        w.client.post(f"{base(pid)}/shots/s5:set-quality", json={"quality": "final"})
        w.client.post(f"{base(pid)}/shots/queue:pause")
        a = w.client.post(f"{base(pid)}/shots/s1:reroll")  # talking, draft: has history
        b = w.client.post(f"{base(pid)}/shots/s3:render")  # action, draft: no history
        c = w.client.post(f"{base(pid)}/shots/s5:render")  # talking, final: no history
        assert a.status_code == b.status_code == c.status_code == 202
        rows = {row["scene_id"]: row for row in get_shots(w, pid)["queue"]["rows"]}
        assert abs(rows["s1"]["estimate_s"] - mean) <= 1 and rows["s1"]["estimate_s"] != DEFAULT_ESTIMATE_S[("talking", "draft")]
        assert rows["s3"]["estimate_s"] == DEFAULT_ESTIMATE_S[("action", "draft")]
        assert rows["s5"]["estimate_s"] == DEFAULT_ESTIMATE_S[("talking", "final")]
        assert (rows["s5"]["width"], rows["s5"]["height"]) == (448, 768)
        w.client.post(f"{base(pid)}/shots/queue:cancel")


def test_pause_lets_the_running_shot_finish_and_resume_continues(tmp_path):
    w = world(tmp_path)
    with w.client:
        pid = ready(w)
        w.adapter.sleep_s = 1.2
        r = w.client.post(f"{base(pid)}/shots:render-all", json={"mode": "missing"})
        jobs = r.json()["jobs"]
        wait_job(w.ctx, jobs[0]["id"], {"running"})
        q = get_shots(w, pid)["queue"]
        assert q["running"]["scene_id"] == "s1" and q["running"]["total"] == 4
        assert q["rows"][0]["status"] == "running" and q["rows"][0]["can_move"] is False
        mv = w.client.post(f"{base(pid)}/shots/queue:move", json={"job_id": jobs[0]["id"], "direction": "down"})
        assert mv.status_code == 409 and mv.json() == {"detail": "That shot has already started."}
        assert w.client.post(f"{base(pid)}/shots/queue:pause").json()["paused"] is True
        assert wait_job(w.ctx, jobs[0]["id"], TERMINAL, timeout=30).status == "succeeded"
        time.sleep(1.0)
        assert w.ctx.queue.get(jobs[1]["id"]).status == "queued"
        w.client.post(f"{base(pid)}/shots/queue:resume")
        assert all(d.status == "succeeded" for d in wait_all(w, jobs, timeout=60))


def test_cancel_stops_the_running_shot_and_removes_the_queue(tmp_path):
    w = world(tmp_path)
    with w.client:
        pid = ready(w)
        w.adapter.sleep_s = 30.0
        r = w.client.post(f"{base(pid)}/shots:render-all", json={"mode": "missing"})
        jobs = r.json()["jobs"]
        wait_job(w.ctx, jobs[0]["id"], {"running"})
        t0 = time.monotonic()
        q = w.client.post(f"{base(pid)}/shots/queue:cancel")
        assert q.status_code == 200
        for j in jobs:
            assert wait_job(w.ctx, j["id"], TERMINAL, timeout=20).status == "cancelled"
        assert time.monotonic() - t0 < 20
        board = get_shots(w, pid)
        assert board["queue"]["rows"] == [] and board["queue"]["running"] is None
        assert all(s["takes"] == [] for s in board["shots"])


def test_generic_job_cancel_works_on_a_shot_job(tmp_path):
    w = world(tmp_path)
    with w.client:
        pid = ready(w)
        w.adapter.sleep_s = 30.0
        r = w.client.post(f"{base(pid)}/shots/s3:render")
        wait_job(w.ctx, r.json()["id"], {"running"})
        assert w.client.post(f"/api/v1/jobs/{r.json()['id']}/cancel").status_code in (200, 202)
        assert wait_job(w.ctx, r.json()["id"], TERMINAL, timeout=20).status == "cancelled"
        assert shot(w, pid, "s3")["takes"] == []


# AC-10 -------------------------------------------------------------------------------------

def test_action_change_stales_only_that_scenes_frame_and_shot(tmp_path):
    w = world(tmp_path)
    with w.client:
        pid = ready(w)
        render_all_shots(w, pid)
        jobs_before = len(w.client.get("/api/v1/jobs").json())
        edit_action(w, pid, "s3", "Tamatar and Aloo shake hands warmly")
        fr = {f["scene_id"]: f["state"] for f in get_frames(w, pid)["frames"]}
        sh = {s["scene_id"]: s["state"] for s in get_shots(w, pid)["shots"]}
        assert fr["s3"] == "stale" and sh["s3"] == "stale"
        assert [k for k, v in fr.items() if v == "stale"] == ["s3"]
        assert [k for k, v in sh.items() if v == "stale"] == ["s3"]
        assert get_shots(w, pid)["stale_count"] == 1 and get_frames(w, pid)["stale_count"] == 1
        assert len(w.client.get("/api/v1/jobs").json()) == jobs_before  # nothing regenerates
        r = w.client.post(f"{base(pid)}/shots/s3:approve")
        assert r.status_code == 409 and r.json() == {"detail": "This shot is out of date. Render it again first."}


def test_new_voice_take_stales_only_that_scenes_talking_shot(tmp_path):
    w = world(tmp_path)
    with w.client:
        pid = ready(w)
        render_all_shots(w, pid)
        r = w.client.post(f"{base(pid)}/voices:generate", json={"mode": "lines", "lines": ["s2"]})
        assert r.status_code == 202
        wait_job(w.ctx, r.json()["id"], TERMINAL, timeout=60)
        assert action(w.client, pid, "s2", "approve").status_code == 200
        # a user brings the key frame gate back by re-confirming the frames
        for sid in SIDS:
            w.client.post(f"{base(pid)}/frames/{sid}:approve")
        assert w.client.get(base(pid)).json()["stage"] == "FRAMES_APPROVED"
        sh = {s["scene_id"]: s["state"] for s in get_shots(w, pid)["shots"]}
        assert sh["s2"] == "stale" and [k for k, v in sh.items() if v == "stale"] == ["s2"]
        assert get_frames(w, pid)["stale_count"] == 0
        assert get_shots(w, pid)["stale_count"] == 1
        r = w.client.post(f"{base(pid)}/shots:render-all", json={"mode": "stale"})
        assert r.status_code == 202 and [j["payload"]["scene_id"] for j in r.json()["jobs"]] == ["s2"]
        wait_all(w, r.json()["jobs"])
        assert get_shots(w, pid)["stale_count"] == 0


def test_changed_approved_frame_stales_its_shot(tmp_path):
    w = world(tmp_path)
    with w.client:
        pid = ready(w)
        render_all_shots(w, pid)
        r = w.client.post(f"{base(pid)}/frames/s2:generate")  # a new active frame for s2
        wait_job(w.ctx, r.json()["id"], TERMINAL)
        assert w.client.post(f"{base(pid)}/frames/s2:approve").status_code == 200
        sh = {s["scene_id"]: s["state"] for s in get_shots(w, pid)["shots"]}
        assert sh["s2"] == "stale" and sh["s1"] == "ready" and sh["s5"] == "ready"


# AC-11 -------------------------------------------------------------------------------------

def test_shots_approved_only_when_every_shot_has_an_approved_take(tmp_path):
    w = world(tmp_path)
    with w.client:
        pid = ready(w)
        render_all_shots(w, pid)
        for sid in SIDS[:-1]:
            out = w.client.post(f"{base(pid)}/shots/{sid}:approve").json()
            assert out["project_stage"] == "FRAMES_APPROVED"
        out = w.client.post(f"{base(pid)}/shots/s5:approve").json()
        assert out["project_stage"] == "SHOTS_APPROVED" and out["approved_count"] == 5 and out["total"] == 5
        assert get_shots(w, pid)["approved_count"] == 5 and shot(w, pid, "s1")["state"] == "approved"
        # changing quality on an approved shot reopens only that shot
        r = w.client.post(f"{base(pid)}/shots/s1:set-quality", json={"quality": "final"})
        assert r.json()["shot"]["state"] == "stale" and r.json()["project_stage"] == "FRAMES_APPROVED"
        assert [s["state"] for s in get_shots(w, pid)["shots"]].count("approved") == 4


def test_editing_an_approved_frame_reopens_only_that_frame_and_its_shot(tmp_path):
    w = world(tmp_path)
    with w.client:
        pid = ready(w)
        shots_approved(w, pid)
        r = w.client.post(f"{base(pid)}/frames/s2:set-framing", json={"framing": "wide"})
        assert r.status_code == 200 and r.json()["project_stage"] == "VOICES_APPROVED"
        assert {f["scene_id"] for f in get_frames(w, pid)["frames"] if f["state"] == "stale"} == {"s2"}
        g = w.client.post(f"{base(pid)}/frames/s2:generate")
        wait_job(w.ctx, g.json()["id"], TERMINAL)
        assert w.client.post(f"{base(pid)}/frames/s2:approve").json()["project_stage"] == "FRAMES_APPROVED"
        sh = {s["scene_id"]: s["state"] for s in get_shots(w, pid)["shots"]}
        assert sh == {"s1": "approved", "s2": "stale", "s3": "approved", "s4": "approved", "s5": "approved"}


# AC-12 (clips) ----------------------------------------------------------------------------

def _clip_url(pid, sid="s3"):
    return f"{base(pid)}/shots/{sid}:upload-clip"


def test_upload_clip_is_checked_by_content_and_stored_under_generated_name(tmp_path):
    w = world(tmp_path)
    with w.client:
        pid = ready(w)
        url = _clip_url(pid)
        bad = w.client.post(url, files={"file": ("movie.mp4", png_bytes(9, 16), "video/mp4")})
        assert bad.status_code == 415 and bad.json() == {"detail": "That file is not a video."}
        empty = w.client.post(url, files={"file": ("movie.mp4", b"", "video/mp4")})
        assert empty.status_code == 415
        wide = w.client.post(url, files={"file": ("w.mp4", mp4_bytes(tmp_path, "wide.mp4", "128x72"), "video/mp4")})
        assert wide.status_code == 422 and wide.json() == {"detail": "The clip must be vertical 9:16."}
        long = w.client.post(url, files={"file": ("l.mp4", mp4_bytes(tmp_path, "long.mp4", "36x64", 21.0), "video/mp4")})
        assert long.status_code == 422 and long.json() == {"detail": "The clip must be 20 seconds or shorter."}
        assert shot(w, pid, "s3")["takes"] == []
        good = mp4_bytes(tmp_path, "good.mp4", "72x128", 1.0)
        r = w.client.post(url, files={"file": ("../../evil_name.txt", good, "text/plain")})
        assert r.status_code == 201, r.text
        card = r.json()["shot"]
        t = active_take(card)
        assert t["source"] == "upload" and t["take_no"] == 1 and t["last_frame_id"]
        stored = art_path(w, t["id"])
        assert stored.name.startswith("take_") and "evil_name" not in str(stored) and stored.suffix == ".mp4"
        assert art_path(w, t["last_frame_id"]).read_bytes().startswith(b"\x89PNG")
        assert w.client.get(t["video_url"]).status_code == 200
        assert artifact(w, t["id"]).params.get("source") == "upload"
        assert artifact(w, t["last_frame_id"]).kind == "last_frame"


def test_upload_clip_oversize_is_rejected_naming_the_limit(tmp_path):
    w = world(tmp_path, max_clip_mb=1)
    with w.client:
        pid = ready(w)
        big = noisy_mp4_bytes(tmp_path)
        assert len(big) > 1024 * 1024, len(big)
        r = w.client.post(_clip_url(pid), files={"file": ("big.mp4", big, "video/mp4")})
        assert r.status_code == 413 and r.json() == {"detail": "That clip is larger than 1 MB."}
        assert shot(w, pid, "s3")["takes"] == []
