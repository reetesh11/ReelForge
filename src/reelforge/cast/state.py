"""Cast slot state: story characters, seeds and candidate listing."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from reelforge.db.models import Artifact, CastSlot, utcnow
from reelforge.library.service import artifact_meta
from reelforge.story import service as story_service
from reelforge.story.errors import StoryInvalid
from reelforge.story.yamlio import parse_story

if TYPE_CHECKING:
    from reelforge.context import AppContext

GENERATE_JOB = "cast.generate"
OWNER_TYPE = "character"
CANDIDATES_PER_RUN = 4
GENERATED_PREFIX = "cast_cand_"
REFINE_PREFIX = "cast_refine_"
MASTER_KIND = "cast_master"
UPLOAD_KIND = "cast_upload"
SEED_SPACE = 2**31 - 1024


@dataclass(frozen=True)
class StoryCharacter:
    key: str
    name: str
    look: str
    aliases: list[str]


@dataclass(frozen=True)
class StoryCast:
    style: str
    characters: dict[str, StoryCharacter]


def load_story_cast(ctx: AppContext, project_id: str) -> StoryCast:
    """The characters of the current story version (empty when there is none)."""
    current = story_service.current_version(ctx, project_id)
    if current is None:
        return StoryCast(style="", characters={})
    try:
        story = parse_story(current.yaml_text)
    except StoryInvalid:
        return StoryCast(style="", characters={})
    return StoryCast(
        style=story.style,
        characters={
            key: StoryCharacter(key=key, name=c.name, look=c.look, aliases=[])
            for key, c in story.characters.items()
        },
    )


def derive_seed(project_id: str, key: str) -> int:
    digest = hashlib.sha256(f"{project_id}:{key}".encode()).hexdigest()
    return int(digest[:12], 16) % SEED_SPACE


def get_slot(ctx: AppContext, project_id: str, key: str) -> CastSlot | None:
    with ctx.session_factory() as s:
        return s.get(CastSlot, (project_id, key))


def list_slots(ctx: AppContext, project_id: str) -> dict[str, CastSlot]:
    with ctx.session_factory() as s:
        rows = s.scalars(select(CastSlot).where(CastSlot.project_id == project_id))
        return {r.story_key: r for r in rows}


def update_slot(ctx: AppContext, project_id: str, key: str, **values: Any) -> CastSlot:
    """Create the slot when missing, then apply `values`."""
    with ctx.session_factory.begin() as s:
        slot = s.get(CastSlot, (project_id, key))
        if slot is None:
            slot = CastSlot(project_id=project_id, story_key=key, candidate_ids=[])
            s.add(slot)
        for name, value in values.items():
            setattr(slot, name, value)
        slot.updated_at = utcnow()
        s.flush()
        s.expunge(slot)
    return slot


def candidate_kind(artifact_kind: str) -> str:
    if artifact_kind.startswith(REFINE_PREFIX):
        return "refine"
    if artifact_kind == UPLOAD_KIND:
        return "upload"
    return "generated"


def candidate_item(ctx: AppContext, artifact: Artifact) -> dict[str, Any]:
    meta = artifact_meta(ctx, artifact)
    item: dict[str, Any] = {
        "id": artifact.id,
        "kind": candidate_kind(artifact.kind),
        "prompt": artifact.prompt,
        "seed": artifact.seed,
        "model": meta["model_id"],
        "model_key": artifact.model_key,
        "image_url": f"/media/{artifact.id}",
        "width": artifact.width,
        "height": artifact.height,
    }
    for name in ("license", "license_url"):
        if meta[name]:
            item[name] = meta[name]
    return item


def candidates(ctx: AppContext, slot: CastSlot | None) -> list[dict[str, Any]]:
    if slot is None:
        return []
    ids = list(slot.candidate_ids or [])
    if not ids:
        return []
    with ctx.session_factory() as s:
        rows = {a.id: a for a in s.scalars(select(Artifact).where(Artifact.id.in_(ids)))}
    return [candidate_item(ctx, rows[i]) for i in ids if i in rows]
