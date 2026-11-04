"""m6 unchanged behaviour: the Assembly stage before export keeps its M1 derivation."""

from __future__ import annotations

from datetime import datetime, timezone


def _job(status: str, progress: int = 0, type_: str = "assemble_preview"):
    from reelforge.db.models import Job

    return Job(
        type=type_, status=status, progress=progress, payload={"stage": "assembly"},
        created_at=datetime.now(timezone.utc),
    )


def test_assembly_stage_unchanged_before_export():
    """Unchanged: Assembly unlocks at SHOTS_APPROVED and reflects its jobs."""
    from reelforge.api.stages import derive_stages, stages_approved

    assert stages_approved("SHOTS_APPROVED") == 5
    last = derive_stages("SHOTS_APPROVED", [])[-1]
    assert last.key == "assembly" and last.state != "approved"
    assert derive_stages("SHOTS_APPROVED", [_job("running", 40)])[-1].state == "rendering"
    assert derive_stages("SHOTS_APPROVED", [_job("running", 40)])[-1].progress == 40
    assert derive_stages("SHOTS_APPROVED", [_job("queued")])[-1].state == "queued"
    assert derive_stages("SHOTS_APPROVED", [_job("failed")])[-1].state == "failed"
