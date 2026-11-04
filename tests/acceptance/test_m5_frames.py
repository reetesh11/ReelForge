"""m5 AC-1, AC-2, AC-11 (frames), AC-12 (image), AC-13, AC-17, AC-18 and prompt helpers."""

from __future__ import annotations

import asyncio
import json

from m3_helpers import png_bytes
from m4_helpers import cast_approved
from m5_helpers import (
    POTATO_LOOK,
    SIDS,
    TERMINAL,
    TOMATO_LOOK,
    active_take,
    art_path,
    artifact,
    base,
    frame,
    gen_frame,
    get_frames,
    jpeg_bytes,
    media_id,
    random_png,
    ready,
    story_text,
    voices_approved,
    wait_all,
    world,
)
from rf_helpers import wait_job


# prompt helpers ---------------------------------------------------------------

def test_compose_frame_prompt_contains_looks_framing_and_product_only_when_asked():
    from reelforge.frames.prompts import FRAMING_PHRASES, PRODUCT_PHRASE, compose_frame_prompt

    assert set(FRAMING_PHRASES) == {"wide", "medium", "closeup"}
    kw = dict(scene_sentence="Tamatar argues", look=TOMATO_LOOK, framing="closeup",
              style="3D cartoon", other_looks=[("Aloo", POTATO_LOOK)])
    with_pack = compose_frame_prompt(**kw, product=True)
    without = compose_frame_prompt(**kw, product=False)
    for p in (with_pack, without):
        assert TOMATO_LOOK in p and POTATO_LOOK in p and FRAMING_PHRASES["closeup"] in p
        assert "Tamatar argues" in p
    assert PRODUCT_PHRASE in with_pack and PRODUCT_PHRASE not in without
    assert "pack" in PRODUCT_PHRASE.lower() and ("hand" in PRODUCT_PHRASE or "table" in PRODUCT_PHRASE)


def test_mock_llm_writes_scene_sentence_and_motion_prompt():
    from reelforge.adapters.mock_llm import MockLlm

    msgs = [{"role": "user", "content": "Action: Aloo bursts in through the crowd"}]
    out = json.loads(asyncio.run(MockLlm().chat(msgs, schema={"properties": {"scene_sentence": {}}})))
    assert "Aloo bursts in through the crowd" in out["scene_sentence"]
    out = json.loads(asyncio.run(MockLlm().chat(msgs, schema={"properties": {"motion_prompt": {}}})))
    assert isinstance(out["motion_prompt"], str) and out["motion_prompt"].strip()


# AC-1 --------------------------------------------------------------------------

def test_frames_need_voices_approved(tmp_path):
    w = world(tmp_path)
    with w.client:
        pid = cast_approved(w.client, w.ctx, text=story_text())
        r = w.client.get(f"{base(pid)}/frames")
        assert r.status_code == 409 and r.json() == {"detail": "Approve the voices first."}
        r = w.client.post(f"{base(pid)}/frames:generate", json={"mode": "missing"})
        assert r.status_code == 409 and r.json() == {"detail": "Approve the voices first."}


def test_frame_job_gets_master_and_prompt_with_look_verbatim(tmp_path):
    w = world(tmp_path)
    with w.client:
        pid = voices_approved(w)
        board = get_frames(w, pid)
        assert (board["total"], board["approved_count"], board["stale_count"]) == (5, 0, 0)
        assert [f["scene_id"] for f in board["frames"]] == SIDS
        assert [f["state"] for f in board["frames"]] == ["no_frame"] * 5
        s1 = frame(w, pid, "s1")
        assert s1["master"]["key"] == "tomato" and s1["framing"] == "medium"
        job, done = gen_frame(w, pid, "s1")
        assert job["type"] == "gen_frame" and done.status == "succeeded", done.error
        assert done.payload["stage"] == "frames" and done.payload["scene_id"] == "s1"
        assert done.heavy and done.mem_need_gb == w.settings.image_mem_gb
        task = w.adapter.of_job(job["id"])
        master_id = s1["master"]["artifact_id"]
        assert task.kind == "image"
        assert [str(p) for p in task.input_paths] == [str(art_path(w, master_id))]
        assert TOMATO_LOOK in task.prompt
        from reelforge.frames.prompts import FRAMING_PHRASES

        assert FRAMING_PHRASES["medium"] in task.prompt
        assert (task.params["strength"], task.params["width"], task.params["height"]) == (0.6, 576, 1024)
        assert done.result["scene_id"] == "s1" and done.result["inputs"] == [master_id]
        card = frame(w, pid, "s1")
        assert card["state"] == "ready" and card["prompt"] and TOMATO_LOOK in card["prompt"]
        assert card["prompt_source"] == "llm" and card["look_removed"] is False
        take = active_take(card)
        assert take["inputs"] == [master_id] and take["take_no"] == 1 and take["source"] == "render"
        assert take["id"] == done.result["take_id"]
        art = artifact(w, take["id"])
        assert art.kind == "frame" and art.owner_type == "scene" and art.owner_id == "s1"
        assert w.client.get(take["image_url"]).content.startswith(b"\x89PNG")
        assert media_id(take["image_url"]) == take["id"]


def test_master_choice_speaker_then_mention_then_first_character_and_default_framing(tmp_path):
    from reelforge.frames.prompts import FRAMING_PHRASES

    w = world(tmp_path)
    with w.client:
        pid = voices_approved(w)
        want = {"s1": "tomato", "s2": "potato", "s3": "tomato", "s4": "tomato", "s5": "tomato"}
        frames = {f["scene_id"]: f for f in get_frames(w, pid)["frames"]}
        assert {k: v["master"]["key"] for k, v in frames.items()} == want
        assert frames["s2"]["framing"] == "closeup"  # dialogue with no explicit framing
        assert frames["s3"]["framing"] == "wide"
        job, done = gen_frame(w, pid, "s2")
        assert done.status == "succeeded", done.error
        task = w.adapter.of_job(job["id"])
        assert POTATO_LOOK in task.prompt and FRAMING_PHRASES["closeup"] in task.prompt
        assert TOMATO_LOOK not in task.prompt
        assert [str(p) for p in task.input_paths] == [str(art_path(w, frames["s2"]["master"]["artifact_id"]))]


def test_two_characters_one_master_other_described_not_copied(tmp_path):
    w = world(tmp_path)
    with w.client:
        pid = voices_approved(w)
        card = frame(w, pid, "s3")
        assert [c["key"] for c in card["characters"]] == ["tomato", "potato"]
        assert card["notes"]["second_character"] == {"master_name": "Tamatar", "other_name": "Aloo"}
        assert "second_character" not in frame(w, pid, "s1")["notes"]
        job, done = gen_frame(w, pid, "s3")
        assert done.status == "succeeded", done.error
        task = w.adapter.of_job(job["id"])
        assert len(task.input_paths) == 1  # never a second init image
        assert TOMATO_LOOK in task.prompt and POTATO_LOOK in task.prompt


def test_regenerate_makes_new_take_new_seed_same_prompt_and_keeps_old(tmp_path):
    w = world(tmp_path)
    with w.client:
        pid = voices_approved(w)
        j1, d1 = gen_frame(w, pid, "s1")
        j2, d2 = gen_frame(w, pid, "s1")
        assert d1.status == d2.status == "succeeded"
        t1, t2 = w.adapter.of_job(j1["id"]), w.adapter.of_job(j2["id"])
        assert t1.seed != t2.seed and t1.prompt == t2.prompt
        card = frame(w, pid, "s1")
        assert [t["take_no"] for t in card["takes"]] == [1, 2]
        assert active_take(card)["take_no"] == 2
        r = w.client.post(f"{base(pid)}/frames/s1:select-take", json={"take_id": card["takes"][0]["id"]})
        assert r.status_code == 200 and active_take(r.json()["frame"])["take_no"] == 1
        bad = w.client.post(f"{base(pid)}/frames/s1:select-take", json={"take_id": "nope"})
        assert bad.status_code == 404 and bad.json() == {"detail": "take not found"}


def test_duplicate_click_returns_the_running_job(tmp_path):
    w = world(tmp_path)
    with w.client:
        pid = voices_approved(w)
        w.adapter.sleep_s = 1.5
        a = w.client.post(f"{base(pid)}/frames/s1:generate")
        b = w.client.post(f"{base(pid)}/frames/s1:generate")
        assert a.status_code == b.status_code == 202 and a.json()["id"] == b.json()["id"]
        wait_job(w.ctx, a.json()["id"], TERMINAL)
        assert len(frame(w, pid, "s1")["takes"]) == 1


def test_save_prompt_keeps_user_text_and_flags_removed_look(tmp_path):
    w = world(tmp_path)
    with w.client:
        pid = voices_approved(w)
        mine = "a very plain red thing waving, flat colours"
        r = w.client.post(f"{base(pid)}/frames/s1:save-prompt", json={"prompt": mine})
        assert r.status_code == 200, r.text
        card = r.json()["frame"]
        assert card["prompt"] == mine and card["prompt_source"] == "user" and card["look_removed"] is True
        r = w.client.post(f"{base(pid)}/frames/s1:set-framing", json={"framing": "wide"})
        assert r.status_code == 200 and r.json()["frame"]["framing"] == "wide"
        assert r.json()["frame"]["prompt"] == mine  # a user-written prompt is kept
        r = w.client.post(f"{base(pid)}/frames/s1:save-prompt", json={"prompt": mine, "regenerate": True})
        assert r.status_code == 200 and r.json()["job"]["type"] == "gen_frame"
        done = wait_job(w.ctx, r.json()["job"]["id"], TERMINAL)
        assert done.status == "succeeded", done.error
        assert mine in w.adapter.of_job(done.id).prompt


def test_set_framing_rewrites_llm_prompt_for_that_scene_only(tmp_path):
    from reelforge.frames.prompts import FRAMING_PHRASES

    w = world(tmp_path)
    with w.client:
        pid = voices_approved(w)
        gen_frame(w, pid, "s1")
        gen_frame(w, pid, "s5")
        r = w.client.post(f"{base(pid)}/frames/s1:set-framing", json={"framing": "closeup"})
        assert r.status_code == 200 and r.json()["frame"]["state"] == "stale"
        assert frame(w, pid, "s5")["state"] == "ready"
        job, done = gen_frame(w, pid, "s1")
        assert done.status == "succeeded"
        assert FRAMING_PHRASES["closeup"] in w.adapter.of_job(job["id"]).prompt
        assert frame(w, pid, "s1")["state"] == "ready"


# AC-2 --------------------------------------------------------------------------

def test_pack_image_is_second_input_and_prompt_asks_for_it(tmp_path):
    from reelforge.frames.prompts import PRODUCT_PHRASE

    pack = tmp_path / "data" / "pack.png"
    w = world(tmp_path)
    with w.client:
        pack.parent.mkdir(parents=True, exist_ok=True)
        pack.write_bytes(png_bytes(9, 16, (10, 200, 10)))
        pid = voices_approved(w, story_text(str(pack)))
        card = frame(w, pid, "s2")
        assert card["notes"]["product"] == "included"
        assert "product" not in frame(w, pid, "s1")["notes"]
        job, done = gen_frame(w, pid, "s2")
        assert done.status == "succeeded", done.error
        task = w.adapter.of_job(job["id"])
        master_id = card["master"]["artifact_id"]
        assert len(task.input_paths) == 2 and str(task.input_paths[0]) == str(art_path(w, master_id))
        assert PRODUCT_PHRASE in task.prompt
        pack_id = done.result["inputs"][1]
        assert done.result["inputs"][0] == master_id
        assert artifact(w, pack_id).kind == "product_pack"
        assert active_take(frame(w, pid, "s2"))["inputs"] == [master_id, pack_id]
        _, again = gen_frame(w, pid, "s2")
        assert again.result["inputs"][1] == pack_id  # deduplicated by content
        _, other = gen_frame(w, pid, "s1")
        assert len(other.result["inputs"]) == 1


def test_missing_pack_image_is_reported_and_frame_still_generates(tmp_path):
    from reelforge.frames.prompts import PRODUCT_PHRASE

    missing = tmp_path / "data" / "nowhere.png"
    w = world(tmp_path)
    with w.client:
        pid = voices_approved(w, story_text(str(missing)))
        card = frame(w, pid, "s2")
        assert card["notes"]["product"] == "missing"
        job, done = gen_frame(w, pid, "s2")
        assert done.status == "succeeded", done.error
        task = w.adapter.of_job(job["id"])
        assert len(task.input_paths) == 1 and PRODUCT_PHRASE not in task.prompt
        assert done.result["inputs"] == [card["master"]["artifact_id"]]
        assert frame(w, pid, "s2")["state"] == "ready"


def test_pack_outside_data_root_counts_as_missing(tmp_path):
    outside = tmp_path / "elsewhere" / "pack.png"
    outside.parent.mkdir()
    outside.write_bytes(png_bytes(9, 16))
    w = world(tmp_path)
    with w.client:
        pid = voices_approved(w, story_text(str(outside)))
        assert frame(w, pid, "s2")["notes"]["product"] == "missing"


# generate-all, cancel, memory -----------------------------------------------------

def test_generate_all_one_job_per_frame_in_story_order(tmp_path):
    w = world(tmp_path)
    with w.client:
        pid = voices_approved(w)
        r = w.client.post(f"{base(pid)}/frames:generate", json={"mode": "missing"})
        assert r.status_code == 202, r.text
        jobs = r.json()["jobs"]
        assert r.json()["skipped"] == [] and len(jobs) == 5
        assert [j["payload"]["scene_id"] for j in jobs] == SIDS
        assert [j["payload"]["total"] for j in jobs] == [5] * 5
        idx = [j["payload"]["index"] for j in jobs]
        assert idx == sorted(idx) and len(set(idx)) == 5
        assert len({j["payload"]["batch_id"] for j in jobs}) == 1
        assert all(j["type"] == "gen_frame" for j in jobs)
        done = wait_all(w, jobs)
        assert all(d.status == "succeeded" for d in done)
        ran = [t for j, t in w.adapter.tasks if t.kind == "image" and j in {x["id"] for x in jobs}]
        assert len(ran) == 5
        order = [next(x["payload"]["scene_id"] for x in jobs if x["id"] == j)
                 for j, t in w.adapter.tasks if j in {x["id"] for x in jobs}]
        assert order == SIDS
        assert w.adapter.max_active == 1  # one heavy job at a time
        board = get_frames(w, pid)
        assert board["jobs"] == [] and all(f["state"] == "ready" for f in board["frames"])
        nothing = w.client.post(f"{base(pid)}/frames:generate", json={"mode": "missing"})
        assert nothing.status_code == 409 and nothing.json() == {"detail": "Nothing to generate."}


def test_board_shows_active_jobs_with_progress_and_cancel_stops_them(tmp_path):
    w = world(tmp_path)
    with w.client:
        pid = voices_approved(w)
        w.adapter.sleep_s = 3.0
        r = w.client.post(f"{base(pid)}/frames:generate", json={"mode": "missing"})
        jobs = r.json()["jobs"]
        wait_job(w.ctx, jobs[0]["id"], {"running"})
        board = get_frames(w, pid)
        assert [j["payload"]["scene_id"] for j in board["jobs"]] == SIDS
        assert {f["state"] for f in board["frames"]} == {"rendering", "queued"}
        assert frame(w, pid, "s1")["state"] == "rendering" and frame(w, pid, "s5")["state"] == "queued"
        c = w.client.post(f"{base(pid)}/frames:cancel")
        assert c.status_code == 200 and c.json() == {"cancelled": 5}
        for j in jobs:
            assert wait_job(w.ctx, j["id"], TERMINAL, timeout=20).status == "cancelled"
        assert all(f["takes"] == [] for f in get_frames(w, pid)["frames"])


def test_frame_memory_shortfall_names_image_mem_gb_and_unloads_ollama_first(tmp_path):
    w = world(tmp_path, image_mem_gb=6.0)
    with w.client:
        pid = voices_approved(w)
        w.set_gb(2.5)
        _, done = gen_frame(w, pid, "s1")
        assert done.status == "failed" and "image_mem_gb" in done.error
        card = frame(w, pid, "s1")
        assert card["state"] == "failed" and "image_mem_gb" in card["message"] and card["takes"] == []
        w.set_gb(8.0)
        before = len(w.unloads)
        _, ok = gen_frame(w, pid, "s1")
        assert ok.status == "succeeded", ok.error
        assert len(w.unloads) > before


# gates, continue-previous, staleness (frames) ---------------------------------------

def test_approve_errors_and_unknown_scene(tmp_path):
    w = world(tmp_path)
    with w.client:
        pid = voices_approved(w)
        r = w.client.post(f"{base(pid)}/frames/s1:approve")
        assert r.status_code == 409 and r.json() == {"detail": "This scene has no frame yet."}
        r = w.client.post(f"{base(pid)}/frames/s99:approve")
        assert r.status_code == 404
        assert w.client.get(f"{base('nope')}/frames").status_code == 404


def test_frames_approved_only_when_every_scene_approved_or_continue_previous(tmp_path):
    w = world(tmp_path)
    with w.client:
        pid = voices_approved(w)
        r = w.client.post(f"{base(pid)}/frames:generate", json={"mode": "scenes", "scenes": ["s1", "s2", "s3", "s5"]})
        assert r.status_code == 202 and len(r.json()["jobs"]) == 4
        wait_all(w, r.json()["jobs"])
        for sid in ("s1", "s2", "s3"):
            out = w.client.post(f"{base(pid)}/frames/{sid}:approve").json()
            assert out["project_stage"] == "VOICES_APPROVED"
        out = w.client.post(f"{base(pid)}/frames/s5:approve").json()
        assert out["project_stage"] == "VOICES_APPROVED" and out["approved_count"] == 4
        # s4 continues from the previous shot: it counts as approved
        r = w.client.post(f"{base(pid)}/frames/s4:continue-previous", json={"enabled": True})
        assert r.status_code == 200, r.text
        card = r.json()["frame"]
        assert card["state"] == "continue_previous" and card["continue_previous"] is True
        assert card["notes"].get("waiting_for_previous_shot") is True  # s3 has no shot yet
        assert r.json()["project_stage"] == "FRAMES_APPROVED"
        assert w.client.get(base(pid)).json()["stage"] == "FRAMES_APPROVED"
        # such a scene is skipped by generate-all
        gen = w.client.post(f"{base(pid)}/frames:generate", json={"mode": "missing"})
        assert gen.status_code == 409
        r = w.client.post(f"{base(pid)}/frames/s4:continue-previous", json={"enabled": False})
        assert r.json()["project_stage"] == "VOICES_APPROVED"
        assert r.json()["frame"]["state"] == "no_frame"


def test_editing_an_approved_frame_reopens_only_that_frame(tmp_path):
    w = world(tmp_path)
    with w.client:
        pid = ready(w)
        r = w.client.post(f"{base(pid)}/frames/s2:set-framing", json={"framing": "wide"})
        assert r.status_code == 200
        assert r.json()["project_stage"] == "VOICES_APPROVED" and r.json()["approved_count"] == 4
        board = get_frames(w, pid)
        by = {f["scene_id"]: f["state"] for f in board["frames"]}
        assert by == {"s1": "approved", "s2": "stale", "s3": "approved", "s4": "approved", "s5": "approved"}
        assert board["stale_count"] == 1
        r = w.client.post(f"{base(pid)}/frames/s2:approve")
        assert r.status_code == 409 and r.json() == {"detail": "This frame is out of date. Make a new frame first."}
        _, done = gen_frame(w, pid, "s2")
        assert done.status == "succeeded"
        r = w.client.post(f"{base(pid)}/frames/s2:approve")
        assert r.status_code == 200 and r.json()["project_stage"] == "FRAMES_APPROVED"


def test_action_change_stales_only_that_scenes_frame_and_nothing_regenerates(tmp_path):
    from m5_helpers import edit_action

    w = world(tmp_path)
    with w.client:
        pid = ready(w)
        jobs_before = len(w.client.get("/api/v1/jobs").json())
        edit_action(w, pid, "s2", "Aloo does a brand new dance")
        board = get_frames(w, pid)
        assert {f["scene_id"] for f in board["frames"] if f["state"] == "stale"} == {"s2"}
        assert board["stale_count"] == 1
        assert len(w.client.get("/api/v1/jobs").json()) == jobs_before
        r = w.client.post(f"{base(pid)}/frames:generate", json={"mode": "stale"})
        assert r.status_code == 202 and [j["payload"]["scene_id"] for j in r.json()["jobs"]] == ["s2"]
        wait_all(w, r.json()["jobs"])
        assert get_frames(w, pid)["stale_count"] == 0


# AC-12 (image) ---------------------------------------------------------------------

def test_upload_replacement_checked_by_content_and_stored_under_generated_name(tmp_path):
    w = world(tmp_path)
    with w.client:
        pid = voices_approved(w)
        url = f"{base(pid)}/frames/s1:upload"
        bad = w.client.post(url, files={"file": ("pretty.png", b"this is not an image", "image/png")})
        assert bad.status_code == 415 and bad.json() == {"detail": "That file is not an image."}
        empty = w.client.post(url, files={"file": ("empty.png", b"", "image/png")})
        assert empty.status_code == 415 and empty.json() == {"detail": "That file is not an image."}
        assert frame(w, pid, "s1")["takes"] == []
        r = w.client.post(url, files={"file": ("evil_name.txt", png_bytes(9, 16), "text/plain")})
        assert r.status_code == 201, r.text
        card = r.json()["frame"]
        t = active_take(card)
        assert t["source"] == "upload" and t["take_no"] == 1
        stored = art_path(w, t["id"])
        assert stored.name.startswith("take_") and "evil_name" not in str(stored)
        assert stored.suffix == ".png"
        r2 = w.client.post(url, files={"file": ("photo.dat", jpeg_bytes(tmp_path), "application/octet-stream")})
        assert r2.status_code == 201, r2.text
        assert len(r2.json()["frame"]["takes"]) == 2 and art_path(w, active_take(r2.json()["frame"])["id"]).suffix in (".jpg", ".jpeg")
        assert w.client.get(active_take(r2.json()["frame"])["image_url"]).status_code == 200
        art = artifact(w, active_take(r2.json()["frame"])["id"])
        assert art.kind == "frame" and art.params.get("source") == "upload"


def test_upload_replacement_oversize_is_rejected_naming_the_limit(tmp_path):
    w = world(tmp_path, max_upload_mb=1)
    with w.client:
        pid = voices_approved(w)
        big = random_png(700, 700)
        assert len(big) > 1024 * 1024
        r = w.client.post(f"{base(pid)}/frames/s1:upload", files={"file": ("big.png", big, "image/png")})
        assert r.status_code == 413 and r.json() == {"detail": "That image is larger than 1 MB."}
        assert frame(w, pid, "s1")["takes"] == []


def test_uploaded_frame_stales_only_by_story_change(tmp_path):
    from m5_helpers import edit_action

    w = world(tmp_path)
    with w.client:
        pid = voices_approved(w)
        w.client.post(f"{base(pid)}/frames/s1:upload", files={"file": ("a.png", png_bytes(9, 16), "image/png")})
        assert frame(w, pid, "s1")["state"] == "ready"
        r = w.client.post(f"{base(pid)}/frames/s1:set-framing", json={"framing": "wide"})
        assert r.json()["frame"]["state"] == "ready"  # framing does not stale an upload
        edit_action(w, pid, "s1", "Tamatar sits quietly")
        assert frame(w, pid, "s1")["state"] == "stale"
