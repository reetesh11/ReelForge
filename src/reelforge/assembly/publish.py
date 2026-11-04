"""Credits and licence checks for an exported reel, and writing the versioned folder."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from reelforge.assembly.align import ALIGN_MODEL_KEY, MlxWhisperAligner
from reelforge.assembly.edl import Edl
from reelforge.cast.licence import _NON_COMMERCIAL_MARKERS  # pyright: ignore[reportPrivateUsage]
from reelforge.db.models import Artifact, ArtifactInput

if TYPE_CHECKING:
    from reelforge.context import AppContext


def _model_keys(ctx: AppContext, edl: Edl) -> set[str]:
    """Model keys of the shot and voice takes and of everything they were made from."""
    pending = list(
        dict.fromkeys([*(s.artifact for s in edl.video), *(d.artifact for d in edl.dialogue)])
    )
    seen: set[str] = set()
    keys: set[str] = set()
    with ctx.session_factory() as s:
        while pending:
            aid = pending.pop()
            if aid in seen:
                continue
            seen.add(aid)
            art = s.get(Artifact, aid)
            if art is None:
                continue
            keys.add(art.model_key)
            pending.extend(
                s.scalars(
                    select(ArtifactInput.input_artifact_id).where(ArtifactInput.artifact_id == aid)
                )
            )
    return keys


def collect_credits(ctx: AppContext, project_id: str, edl: Edl) -> list[dict[str, Any]]:
    """One `{model, version, licence}` per distinct model used by the reel."""
    del project_id
    keys = _model_keys(ctx, edl)
    if isinstance(ctx.aligner, MlxWhisperAligner) and any(c.text.strip() for c in edl.captions):
        keys.add(ALIGN_MODEL_KEY)
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for entry in ctx.registry.entries():
        if entry.key not in keys or entry.id in seen:
            continue
        seen.add(entry.id)
        out.append({"model": entry.id, "version": entry.revision, "licence": entry.license})
    return out


def licence_warnings(credits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The credits whose licence is empty or non-commercial."""
    out: list[dict[str, Any]] = []
    for c in credits:
        text = str(c.get("licence", ""))
        if not text.strip() or any(m in text.lower() for m in _NON_COMMERCIAL_MARKERS):
            out.append(c)
    return out
