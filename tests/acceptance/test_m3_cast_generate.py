"""AC-3, AC-6, AC-11 (and AC-8: mock adapter, network guard active in conftest)."""

from __future__ import annotations

from m3_helpers import approved_project, cast_item, generate, get_cast, new_world
from rf_helpers import artifacts_of, sidecar_of


def _artifact(ctx, pid, aid):
    return next(a for a in artifacts_of(ctx, pid) if a.id == aid)


def test_four_candidates_with_consecutive_seeds_then_cache(tmp_path):
    ctx, client, adapter = new_world(tmp_path)
    with client:
        pid = approved_project(client)
        resp, job = generate(client, ctx, pid, "tomato", seed=100)
        assert resp["payload"]["stage"] == "cast" and resp["payload"]["key"] == "tomato"
        assert resp["payload"]["total"] == 4
        assert job.status == "succeeded", job.error
        assert adapter.seeds == [100, 101, 102, 103]
        assert all(c["kind"] == "image" for c in adapter.calls)

        res = client.get(f"/api/v1/jobs/{job.id}").json()["result"]
        assert res["completed"] == 4 and res["total"] == 4 and len(res["candidate_ids"]) == 4
        assert res["elapsed_s"] >= 0

        item = cast_item(client, pid, "tomato")
        assert item["state"] == "ready"
        cands = item["candidates"]
        assert [c["seed"] for c in cands] == [100, 101, 102, 103]
        assert all(c["kind"] == "generated" and c["prompt"] and c["model"] for c in cands)
        assert all(abs(c["width"] / c["height"] - 9 / 16) < 0.02 for c in cands)
        for c in cands:
            art = _artifact(ctx, pid, c["id"])
            side = sidecar_of(ctx, art)
            assert side["prompt"] == c["prompt"] and side["seed"] == c["seed"]
            assert side["model"] == "image" and side["model_id"] == c["model"]
            assert client.get(c["image_url"]).status_code == 200
        assert cast_item(client, pid, "potato")["candidates"] == []

        before = len(adapter.calls)
        _, job2 = generate(client, ctx, pid, "tomato", seed=100)
        assert job2.status == "succeeded", job2.error
        assert len(adapter.calls) == before  # served from cache: 0 adapter calls
        again = cast_item(client, pid, "tomato")["candidates"]
        assert [c["id"] for c in again] == [c["id"] for c in cands]


def test_regenerate_appends_four_more_seeds_and_refine_adds_one(tmp_path):
    ctx, client, adapter = new_world(tmp_path)
    with client:
        pid = approved_project(client)
        generate(client, ctx, pid, "tomato", seed=10)
        _, job = generate(client, ctx, pid, "tomato", regenerate=True)
        assert job.status == "succeeded", job.error
        assert adapter.seeds == [10, 11, 12, 13, 14, 15, 16, 17]
        cands = cast_item(client, pid, "tomato")["candidates"]
        assert [c["seed"] for c in cands] == list(range(10, 18))

        src = cands[1]
        n = len(adapter.calls)
        _, job = generate(
            client, ctx, pid, "tomato",
            refine={"from_candidate": src["id"], "instruction": "wear a blue hat"},
        )
        assert job.status == "succeeded", job.error
        assert len(adapter.calls) == n + 1
        last = adapter.calls[-1]
        assert last["seed"] == 18 and len(last["inputs"]) == 1
        cands = cast_item(client, pid, "tomato")["candidates"]
        assert len(cands) == 9 and cands[-1]["kind"] == "refine"

        r = client.post(
            f"/api/v1/projects/{pid}/cast/tomato:generate",
            json={"refine": {"from_candidate": "nope", "instruction": "x"}},
        )
        assert r.status_code == 404


def test_cancel_after_image_two_keeps_two_and_stops(tmp_path):
    ctx, client, adapter = new_world(tmp_path)

    def after(n, job_id):
        if n == 2:
            ctx.queue.cancel(job_id)

    adapter.after = after
    with client:
        pid = approved_project(client)
        _, job = generate(client, ctx, pid, "tomato", seed=20)
        assert job.status == "cancelled"
        assert len(adapter.calls) == 2
        assert len(artifacts_of(ctx, pid)) == 2
        item = cast_item(client, pid, "tomato")
        assert [c["seed"] for c in item["candidates"]] == [20, 21]
        assert item["state"] == "stopped"
        assert item["progress"]["completed"] == 2 and item["progress"]["total"] == 4


def test_bible_line_returned_and_edited_text_used_in_next_prompt(tmp_path):
    ctx, client, adapter = new_world(tmp_path)
    with client:
        pid = approved_project(client)
        generate(client, ctx, pid, "tomato", seed=30)
        item = cast_item(client, pid, "tomato")
        assert item["bible_line"].strip() != ""
        assert item["bible_source"] in {"llm", "raw"}
        assert item["state"] == "ready"

        edited = "EDITEDBIBLE round red tomato in a gold sherwani, plain background"
        n = len(adapter.calls)
        _, job = generate(client, ctx, pid, "tomato", look_text=edited, seed=30)
        assert job.status == "succeeded", job.error
        new_calls = adapter.calls[n:]
        assert len(new_calls) == 4
        assert all("EDITEDBIBLE" in c["prompt"] for c in new_calls)
        item = cast_item(client, pid, "tomato")
        assert item["bible_line"] == edited and item["bible_source"] == "user"
        assert len(item["candidates"]) == 4


def test_generate_errors(tmp_path):
    ctx, client, adapter = new_world(tmp_path)
    with client:
        from rf_helpers import create_project

        draft = create_project(client)["id"]
        r = client.post(f"/api/v1/projects/{draft}/cast/tomato:generate", json={})
        assert r.status_code == 409 and r.json() == {"detail": "Approve the story first."}
        assert client.get(f"/api/v1/projects/{draft}/cast").status_code == 409
        pid = approved_project(client)
        r = client.post(f"/api/v1/projects/{pid}/cast/ghost:generate", json={})
        assert r.status_code == 404 and r.json() == {"detail": "character not found"}
        r = client.post("/api/v1/projects/01ARZ3NDEKTSV4RRFFQ69G5FAV/cast/tomato:generate", json={})
        assert r.status_code == 404 and r.json() == {"detail": "project not found"}
        assert len(get_cast(client, pid)["characters"]) == 2
        assert adapter.calls == []


def test_progress_is_image_n_of_4_in_job_events(tmp_path):
    """AC-16: progress is 'image n of 4' + elapsed seconds, via existing job events."""
    import queue as _q

    ctx, client, adapter = new_world(tmp_path)
    events = ctx.queue.bus.subscribe()
    with client:
        pid = approved_project(client)
        _, job = generate(client, ctx, pid, "tomato", seed=300)
        assert job.status == "succeeded", job.error
        msgs = []
        while True:
            try:
                ev = events.get_nowait()
            except Exception:
                break
            if ev.type == "job.updated" and ev.data.get("job_id") == job.id:
                msgs.append(ev.data.get("message") or "")
        for n in range(1, 5):
            assert any(f"image {n} of 4" in m for m in msgs), msgs
        res = client.get(f"/api/v1/jobs/{job.id}").json()["result"]
        assert res["completed"] == 4 and res["total"] == 4 and res["elapsed_s"] >= 0
