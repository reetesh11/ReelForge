"""AC-4: cache reuse by inputs_fp; new seed never hits; atomic, active-flag semantics."""

from __future__ import annotations

import hashlib

from rf_helpers import (
    artifacts_of,
    create_project,
    make_client,
    make_ctx,
    make_settings,
    store_bytes,
    wait_job,
)


def _req(pid, **over):
    from reelforge.artifacts.service import ArtifactRequest

    kw = {
        "project_id": pid,
        "owner_type": "character",
        "owner_id": "own1",
        "kind": "candidate",
        "media": "image",
        "prompt": "a happy tomato",
        "seed": 1,
    }
    kw.update(over)
    return ArtifactRequest(**kw)


def _first(ctx, client):
    from reelforge.artifacts.service import request_artifact

    pid = create_project(client)["id"]
    res = request_artifact(ctx, _req(pid))
    assert res.cache_hit is False and res.job is not None
    wait_job(ctx, res.job.id, {"succeeded"})
    return pid


def test_unchanged_request_is_a_cache_hit_with_no_new_job(tmp_path):
    from reelforge.artifacts.service import request_artifact

    ctx = make_ctx(make_settings(tmp_path))
    with make_client(ctx) as client:
        pid = _first(ctx, client)
        before = len(ctx.queue.list())
        res = request_artifact(ctx, _req(pid))
        assert res.cache_hit is True
        assert res.job is None
        assert res.artifact is not None
        assert len(ctx.queue.list()) == before == 1
        assert len(artifacts_of(ctx, pid)) == 1
    ctx.close()


def test_new_seed_never_hits_cache_and_becomes_active_take(tmp_path):
    from reelforge.artifacts.service import request_artifact

    ctx = make_ctx(make_settings(tmp_path))
    with make_client(ctx) as client:
        pid = _first(ctx, client)
        res = request_artifact(ctx, _req(pid, seed=2))
        assert res.cache_hit is False and res.job is not None
        wait_job(ctx, res.job.id, {"succeeded"})
        arts = artifacts_of(ctx, pid)
        assert [a.take_no for a in arts] == [1, 2]
        assert [a.is_active for a in arts] == [False, True]
        old = ctx.store.absolute_path(arts[0])
        assert old.exists()  # never deleted
        # the original seed is no longer the active take, so it is a miss again
        again = request_artifact(ctx, _req(pid, seed=1))
        assert again.cache_hit is False
    ctx.close()


def test_missing_file_is_a_miss(tmp_path):
    from reelforge.artifacts.service import request_artifact

    ctx = make_ctx(make_settings(tmp_path))
    with make_client(ctx) as client:
        pid = _first(ctx, client)
        art = artifacts_of(ctx, pid)[0]
        ctx.store.absolute_path(art).unlink()
        res = request_artifact(ctx, _req(pid))
        assert res.cache_hit is False and res.job is not None
    ctx.close()


def test_hash_mismatch_and_missing_sidecar_are_misses(tmp_path):
    from reelforge.artifacts.service import request_artifact

    ctx = make_ctx(make_settings(tmp_path))
    with make_client(ctx) as client:
        pid = _first(ctx, client)
        art = artifacts_of(ctx, pid)[0]
        path = ctx.store.absolute_path(art)
        original = path.read_bytes()
        path.write_bytes(original + b"corrupt")
        assert request_artifact(ctx, _req(pid)).cache_hit is False
        path.write_bytes(original)
        path.with_suffix(".json").unlink()
        assert request_artifact(ctx, _req(pid)).cache_hit is False
    ctx.close()


def test_store_write_is_atomic_relative_and_hashed(tmp_path):
    ctx = make_ctx(make_settings(tmp_path))
    with make_client(ctx, start_worker=False) as client:
        pid = create_project(client)["id"]
    spec, art = store_bytes(ctx, pid, b"payload-1", ext="png", subdir="frames/s2")
    path = ctx.store.absolute_path(art)
    root = ctx.settings.data_root.resolve()
    assert path.exists() and path.resolve().is_relative_to(root)
    assert not art.path.startswith("/")
    assert art.path.endswith("frames/s2/take_001.png")
    assert art.sha256 == hashlib.sha256(b"payload-1").hexdigest()
    assert path.with_suffix(".json").exists()
    assert list(ctx.settings.cache_tmp.rglob("*")) == [] or all(
        p.is_dir() for p in ctx.settings.cache_tmp.rglob("*")
    )
    assert ctx.store.lookup(spec) is not None
    _, art2 = store_bytes(ctx, pid, b"payload-2", ext="png", subdir="frames/s2", seed=8)
    assert art2.take_no == 2 and art2.is_active
    ctx.close()


def test_fingerprint_changes_with_every_input():
    from reelforge.artifacts.fingerprint import compute_inputs_fp

    base = {
        "adapter": "mock",
        "adapter_version": "mock-1",
        "model_key": "image",
        "model_revision": "r1",
        "prompt": "p",
        "seed": 1,
        "params": {"a": 1},
        "input_sha256": ["x"],
    }
    fp = compute_inputs_fp(**base)
    assert fp == compute_inputs_fp(**base)
    assert len(fp) == 64
    for key, val in (
        ("adapter", "other"),
        ("adapter_version", "v2"),
        ("model_key", "video"),
        ("model_revision", "r2"),
        ("prompt", "q"),
        ("seed", 2),
        ("params", {"a": 2}),
        ("input_sha256", ["y"]),
    ):
        assert compute_inputs_fp(**{**base, key: val}) != fp, key
    assert compute_inputs_fp(
        **{**base, "params": {"b": 1, "a": 1}}
    ) == compute_inputs_fp(**{**base, "params": {"a": 1, "b": 1}})
