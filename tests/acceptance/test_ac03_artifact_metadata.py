"""AC-3: row and sidecar agree on prompt, seed, model and version."""

from __future__ import annotations

from rf_helpers import (
    artifacts_of,
    create_project,
    make_client,
    make_ctx,
    make_settings,
    sidecar_of,
    store_bytes,
    submit,
    wait_job,
)

REQUIRED = ("prompt", "seed", "model", "version")


def _check_pair(ctx, art):
    side = sidecar_of(ctx, art)
    for key in (
        "id",
        "kind",
        "owner_type",
        "owner_id",
        "take_no",
        "prompt",
        "seed",
        "model",
        "model_id",
        "model_revision",
        "version",
        "adapter",
        "params",
        "inputs_fp",
        "job_id",
        "sha256",
        "created_at",
    ):
        assert key in side, key
    assert art.prompt and side["prompt"]
    assert art.model_key and side["model"]
    assert art.version and side["version"]
    assert art.seed is not None and side["seed"] is not None
    assert art.prompt == side["prompt"]
    assert art.seed == side["seed"]
    assert art.model_key == side["model"]
    assert art.version == side["version"]
    assert art.inputs_fp == side["inputs_fp"]
    assert art.sha256 == side["sha256"]
    assert art.params == side["params"]
    assert art.created_by_job == side["job_id"]


def test_job_generated_artifacts_match_sidecar_for_every_media(tmp_path):
    ctx = make_ctx(make_settings(tmp_path))
    with make_client(ctx) as client:
        pid = create_project(client)["id"]
        for media, kind in (
            ("image", "candidate"),
            ("audio", "voice_take"),
            ("video", "shot"),
        ):
            job = submit(
                client,
                pid,
                media=media,
                kind=kind,
                owner_id=f"o-{media}",
                prompt=f"p {media}",
                seed=11,
            )
            wait_job(ctx, job["job_id"], {"succeeded"}, timeout=60)
    arts = artifacts_of(ctx, pid)
    assert {a.kind for a in arts} == {"candidate", "voice_take", "shot"}
    for a in arts:
        _check_pair(ctx, a)
        assert a.created_by_job
    ctx.close()


def test_directly_written_artifact_matches_sidecar(tmp_path):
    ctx = make_ctx(make_settings(tmp_path))
    with make_client(ctx, start_worker=False) as client:
        pid = create_project(client)["id"]
    _, art = store_bytes(ctx, pid, b"abc", prompt="direct prompt", seed=99)
    _check_pair(ctx, art)
    side = sidecar_of(ctx, art)
    assert side["prompt"] == "direct prompt" and side["seed"] == 99
    ctx.close()
