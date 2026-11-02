"""AC-14: behaviour that must not change (green before and after)."""

from __future__ import annotations

from m3_helpers import StubServer
from rf_helpers import free_port, make_client, make_ctx, make_settings


def test_health_has_no_licence_key_for_permissive_default_model(tmp_path):
    client = make_client(make_ctx(make_settings(tmp_path)))
    with client:
        body = client.get("/health").json()
        assert "image_licence_warning" not in body
        assert "checks" in body and "status" in body


def test_draw_things_check_unreachable_and_reachable_unchanged():
    from reelforge.adapters.drawthings import DrawThingsAdapter

    rep = DrawThingsAdapter(f"http://127.0.0.1:{free_port()}").check()
    assert rep.ok is False and rep.name == "draw_things"
    s = StubServer()
    try:
        ok = DrawThingsAdapter(s.url).check()
    finally:
        s.close()
    assert ok.ok is True and "reachable" in ok.detail


def test_doctor_keeps_eleven_check_names():
    from reelforge.doctor import CHECKS

    assert list(CHECKS) == [
        "arm64", "binaries_native", "ffmpeg_filters", "ltx", "mlx_audio", "draw_things",
        "ollama", "ports", "disk", "memory", "licenses",
    ]
