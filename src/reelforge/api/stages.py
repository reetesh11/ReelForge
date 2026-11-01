"""Stage stepper derivation from `projects.stage` plus the project's jobs."""

from __future__ import annotations

from reelforge.api.schemas import StageInfo
from reelforge.db.models import Job

STAGE_ORDER = [
    "DRAFT",
    "STORY_APPROVED",
    "CAST_APPROVED",
    "VOICES_APPROVED",
    "FRAMES_APPROVED",
    "SHOTS_APPROVED",
    "ASSEMBLED",
    "EXPORTED",
]
STAGES = [
    ("story", "Story"),
    ("cast", "Cast"),
    ("voices", "Voices"),
    ("frames", "Key frames"),
    ("shots", "Shots"),
    ("assembly", "Assembly"),
]


def stages_approved(stage: str) -> int:
    return min(STAGE_ORDER.index(stage), 6)


def derive_stages(project_stage: str, jobs: list[Job]) -> list[StageInfo]:
    gate = STAGE_ORDER.index(project_stage)
    out: list[StageInfo] = []
    locked = False
    for index, (key, label) in enumerate(STAGES):
        approved = gate >= index + 1
        state = "approved"
        progress: int | None = None
        if not approved:
            mine = sorted(
                (j for j in jobs if j.payload.get("stage") == key),
                key=lambda j: j.created_at,
            )
            running = [j for j in mine if j.status == "running"]
            queued = [j for j in mine if j.status == "queued"]
            if running:
                state, progress = "rendering", running[-1].progress
            elif queued:
                state = "queued"
            elif mine and mine[-1].status == "failed":
                state = "failed"
            else:
                state = "not_started"
        out.append(
            StageInfo(
                key=key,
                label=label,
                state=state,  # type: ignore[arg-type]
                progress=progress,
                locked=locked,
            )
        )
        if not approved:
            locked = True
    return out
