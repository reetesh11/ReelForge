"""m3c: behaviour that must not change (green before and after)."""

from __future__ import annotations

from rf_helpers import run_async


def test_non_cast_preflight_wording_unchanged():
    from reelforge.jobs.preflight import preflight

    async def unload():
        return None

    r = run_async(preflight(12.0, available_gb=lambda: 3.0, unload_ollama=unload, wait_s=0))
    assert "image_mem_gb" not in str(r.reason)
    assert r.reason == "Only 3.0 GB free, job needs 12.0 GB."
