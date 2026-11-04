"""Artifact kinds of the shots stage, and queries over them shared with the frames stage."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select

from reelforge.db.models import Artifact, ArtifactInput

if TYPE_CHECKING:
    from reelforge.context import AppContext

SHOT_KIND = "shot"
LAST_FRAME_KIND = "last_frame"
OWNER_SCENE = "scene"


def active_shot(ctx: AppContext, project_id: str, scene_id: str) -> Artifact | None:
    with ctx.session_factory() as s:
        return s.scalars(
            select(Artifact)
            .where(
                Artifact.project_id == project_id,
                Artifact.owner_type == OWNER_SCENE,
                Artifact.owner_id == scene_id,
                Artifact.kind == SHOT_KIND,
                Artifact.is_active.is_(True),
            )
            .order_by(Artifact.take_no.desc())
        ).first()


def last_frame_for_take(ctx: AppContext, shot_take_id: str) -> Artifact | None:
    """The `last_frame` artifact that was cut from the given shot take."""
    with ctx.session_factory() as s:
        return s.scalars(
            select(Artifact)
            .join(ArtifactInput, ArtifactInput.artifact_id == Artifact.id)
            .where(
                ArtifactInput.input_artifact_id == shot_take_id,
                Artifact.kind == LAST_FRAME_KIND,
            )
            .order_by(Artifact.take_no.desc())
        ).first()
