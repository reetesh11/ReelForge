"""Story versions: save, read, approve, stale (all computed from rows, no flags)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy import func, select

from reelforge.db.models import Artifact, Job, Project, StoryChange, StoryVersion, utcnow
from reelforge.story.errors import StoryInvalid
from reelforge.story.schema import Story
from reelforge.story.staleness import Affected, ChangeRow, diff_stories, is_stale
from reelforge.story.yamlio import parse_story

if TYPE_CHECKING:
    from reelforge.context import AppContext

MAX_STORY_BYTES = 1_048_576
STRUCTURE_JOB = "story.structure"


class ProjectMissing(Exception):
    pass


class NoStory(Exception):
    pass


class StructuringRunning(Exception):
    pass


@dataclass(frozen=True)
class SavedVersion:
    id: str
    version: int
    is_current: bool
    approved_at: datetime | None
    created_at: datetime
    affected: list[Affected]


def _saved(row: StoryVersion, affected: list[Affected]) -> SavedVersion:
    return SavedVersion(
        id=row.id,
        version=row.version,
        is_current=row.is_current,
        approved_at=row.approved_at,
        created_at=row.created_at,
        affected=affected,
    )


def _write_file(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".yaml.tmp")
    tmp.write_text(text, encoding="utf-8", newline="")
    os.replace(tmp, path)


def _try_parse(text: str) -> Story | None:
    try:
        return parse_story(text)
    except StoryInvalid:
        return None


def save_version(
    ctx: AppContext,
    project_id: str,
    text: str,
    *,
    keep_stage: bool = False,
    record_changes: bool = True,
) -> SavedVersion:
    """Validate and store `text` as the new current version (raw text kept as submitted).

    `keep_stage` leaves the project stage alone (and the new version inherits the previous
    version's approval); `record_changes=False` skips the `story_changes` rows.
    """
    new_story = parse_story(text)
    stage_changed = False
    affected: list[Affected] = []
    with ctx.session_factory.begin() as s:
        project = s.get(Project, project_id)
        if project is None:
            raise ProjectMissing(project_id)
        rows = list(s.scalars(select(StoryVersion).where(StoryVersion.project_id == project_id)))
        previous = next((r for r in rows if r.is_current), None)
        number = max((r.version for r in rows), default=0) + 1
        for r in rows:
            r.is_current = False
        row = StoryVersion(
            project_id=project_id,
            version=number,
            yaml_text=text,
            is_current=True,
            approved_at=previous.approved_at if keep_stage and previous is not None else None,
            created_at=utcnow(),
        )
        s.add(row)
        s.flush()
        if project.stage != "DRAFT" and previous is not None:
            old_story = _try_parse(previous.yaml_text)
            if old_story is None or old_story != new_story:
                if old_story is not None:
                    affected = diff_stories(old_story, new_story)
                now = utcnow()
                for a in affected if record_changes else []:
                    s.add(
                        StoryChange(
                            project_id=project_id,
                            story_version_id=row.id,
                            owner_type=a.owner_type,
                            owner_id=a.owner_id,
                            kinds=a.kinds,
                            created_at=now,
                        )
                    )
                if not keep_stage:
                    project.stage = "DRAFT"
                    stage_changed = True
        project.updated_at = utcnow()
        s.flush()
        saved = _saved(row, affected)
        data_dir = project.data_dir
    _write_file(ctx.settings.data_root / data_dir / "story.yaml", text)
    if stage_changed:
        ctx.bus.publish("stage.changed", {"project_id": project_id, "stage": "DRAFT"})
    return saved


def current_version(ctx: AppContext, project_id: str) -> StoryVersion | None:
    with ctx.session_factory() as s:
        return s.scalars(
            select(StoryVersion).where(
                StoryVersion.project_id == project_id, StoryVersion.is_current.is_(True)
            )
        ).first()


def list_versions(ctx: AppContext, project_id: str) -> list[StoryVersion]:
    with ctx.session_factory() as s:
        return list(
            s.scalars(
                select(StoryVersion)
                .where(StoryVersion.project_id == project_id)
                .order_by(StoryVersion.version.desc())
            )
        )


def get_version(ctx: AppContext, project_id: str, number: int) -> StoryVersion | None:
    with ctx.session_factory() as s:
        return s.scalars(
            select(StoryVersion).where(
                StoryVersion.project_id == project_id, StoryVersion.version == number
            )
        ).first()


def approve(ctx: AppContext, project_id: str) -> Project:
    """Approve the current version; idempotent. Raises NoStory / StructuringRunning."""
    stage_changed = False
    with ctx.session_factory.begin() as s:
        project = s.get(Project, project_id)
        if project is None:
            raise ProjectMissing(project_id)
        current = s.scalars(
            select(StoryVersion).where(
                StoryVersion.project_id == project_id, StoryVersion.is_current.is_(True)
            )
        ).first()
        if current is None:
            raise NoStory(project_id)
        running = s.scalar(
            select(func.count())
            .select_from(Job)
            .where(
                Job.project_id == project_id,
                Job.type == STRUCTURE_JOB,
                Job.status.in_(("queued", "running")),
            )
        )
        if running:
            raise StructuringRunning(project_id)
        if current.approved_at is None:
            current.approved_at = utcnow()
        if project.stage == "DRAFT":
            project.stage = "STORY_APPROVED"
            stage_changed = True
        project.updated_at = utcnow()
        s.flush()
        s.expunge(project)
    if stage_changed:
        ctx.bus.publish("stage.changed", {"project_id": project_id, "stage": project.stage})
    return project


@dataclass(frozen=True)
class StaleEntry:
    artifact_id: str
    owner_type: str
    owner_id: str
    kind: str


def stale_items(ctx: AppContext, project_id: str) -> list[StaleEntry]:
    with ctx.session_factory() as s:
        changes = [
            ChangeRow(c.owner_type, c.owner_id, list(c.kinds), c.created_at)
            for c in s.scalars(select(StoryChange).where(StoryChange.project_id == project_id))
        ]
        if not changes:
            return []
        artifacts = list(
            s.scalars(
                select(Artifact)
                .where(Artifact.project_id == project_id, Artifact.is_active.is_(True))
                .order_by(Artifact.created_at, Artifact.id)
            )
        )
    by_owner: dict[tuple[str, str], list[ChangeRow]] = {}
    for c in changes:
        by_owner.setdefault((c.owner_type, c.owner_id), []).append(c)
    return [
        StaleEntry(a.id, a.owner_type, a.owner_id, a.kind)
        for a in artifacts
        if is_stale(a.kind, a.created_at, by_owner.get((a.owner_type, a.owner_id), []))
    ]
