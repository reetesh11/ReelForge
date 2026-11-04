"""The product pack image: found under the data root, registered once per content hash."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy import select

from reelforge.artifacts.store import ArtifactSpec
from reelforge.cast.uploads import NotAnImage, TooLarge, sniff_image
from reelforge.db.models import Artifact
from reelforge.frames.state import OWNER_PROJECT, PACK_KIND, PACK_OWNER_ID
from reelforge.story.schema import Story

if TYPE_CHECKING:
    from reelforge.context import AppContext


@dataclass(frozen=True)
class PackFile:
    path: Path
    data: bytes
    ext: str
    width: int
    height: int


def locate_product(ctx: AppContext, story: Story) -> PackFile | None:
    """The `product.asset` image when it is a PNG or JPEG file inside the data root."""
    product = story.product
    if product is None or not product.asset:
        return None
    root = ctx.settings.data_root.resolve()
    raw = Path(product.asset).expanduser()
    try:
        path = (raw if raw.is_absolute() else root / raw).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            return None
        if path.stat().st_size > ctx.settings.max_upload_mb * 1024 * 1024:
            return None
        data = path.read_bytes()
        ext, width, height = sniff_image(data)
    except (OSError, ValueError, NotAnImage, TooLarge):
        return None
    return PackFile(path, data, ext, width, height)


def resolve_product(ctx: AppContext, project_id: str, story: Story) -> Artifact | None:
    """Register the pack image as a `product_pack` artifact (deduplicated by sha256)."""
    pack = locate_product(ctx, story)
    if pack is None or story.product is None:
        return None
    sha = hashlib.sha256(pack.data).hexdigest()
    with ctx.session_factory() as s:
        found = s.scalars(
            select(Artifact)
            .where(
                Artifact.project_id == project_id,
                Artifact.kind == PACK_KIND,
                Artifact.sha256 == sha,
            )
            .order_by(Artifact.take_no.desc())
        ).first()
    if found is not None and ctx.store.absolute_path(found).is_file():
        return found
    spec = ArtifactSpec(
        project_id=project_id,
        owner_type=OWNER_PROJECT,
        owner_id=PACK_OWNER_ID,
        kind=PACK_KIND,
        subdir="product",
        prompt=story.product.name,
        seed=0,
        model_key="upload",
        model_revision="",
        adapter="upload",
        version="upload-1",
        params={"source": "story"},
        width=pack.width,
        height=pack.height,
    )
    return ctx.store.write(spec, pack.data, ext=pack.ext)
