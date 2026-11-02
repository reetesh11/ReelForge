"""AC-4 (backend half): Draw Things unreachable on the real backend."""

from __future__ import annotations

from m3_helpers import approved_project, cast_item, fake_mflux, generate, get_cast
from rf_helpers import free_port, make_client, make_ctx, make_settings


def _real(tmp_path, port: int, **over):
    tmp_path.mkdir(parents=True, exist_ok=True)
    settings = make_settings(
        tmp_path, backend="real", drawthings_url=f"http://127.0.0.1:{port}", **over
    )
    ctx = make_ctx(settings)
    return ctx, make_client(ctx)


def test_unreachable_reported_and_generation_fails_with_exact_message(tmp_path):
    port = free_port()
    ctx, client = _real(tmp_path, port)
    with client:
        pid = approved_project(client)
        backend = get_cast(client, pid)["image_backend"]
        assert backend == {
            "kind": "draw_things", "reachable": False, "port": port, "mflux_available": False,
        }
        _, job = generate(client, ctx, pid, "tomato")
        assert job.status == "failed"
        assert job.error == f"Draw Things isn't reachable on port {port}"
        item = cast_item(client, pid, "tomato")
        assert item["state"] == "failed"
        assert item["error"] == f"Draw Things isn't reachable on port {port}"


def test_mflux_available_only_when_configured(tmp_path):
    port = free_port()
    cmd, _ = fake_mflux(tmp_path)

    ctx, client = _real(tmp_path / "a", port, image_fallback="mflux")  # no command
    with client:
        pid = approved_project(client)
        assert get_cast(client, pid)["image_backend"]["mflux_available"] is False

    ctx, client = _real(tmp_path / "b", port, mflux_command=cmd)  # not selected
    with client:
        pid = approved_project(client)
        assert get_cast(client, pid)["image_backend"]["mflux_available"] is False

    ctx, client = _real(tmp_path / "c", port, image_fallback="mflux", mflux_command=cmd)
    with client:
        pid = approved_project(client)
        assert get_cast(client, pid)["image_backend"]["mflux_available"] is True


def test_mock_backend_is_always_reachable(tmp_path):
    ctx = make_ctx(make_settings(tmp_path))
    client = make_client(ctx)
    with client:
        pid = approved_project(client)
        body = get_cast(client, pid)
        assert body["image_backend"]["kind"] == "mock" and body["image_backend"]["reachable"] is True
        assert body["stage"] == "STORY_APPROVED" and body["total"] == 2 and body["approved_count"] == 0
