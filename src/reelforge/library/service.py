"""Library characters: records, master image copies and the character.json mirror."""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from reelforge.db.models import Artifact, Character, utcnow
from reelforge.ids import new_id

if TYPE_CHECKING:
    from reelforge.context import AppContext

MASTER_MEDIA = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg"}
PATCHABLE = ("name", "aliases", "tags")


class CharacterNotFound(Exception):
    pass


class ArtifactNotFound(Exception):
    pass


def library_dir(ctx: AppContext, cid: str) -> Path:
    return ctx.settings.data_root / "library" / "characters" / cid


def to_record(ch: Character) -> dict[str, Any]:
    """The LibraryCharacter JSON; also the exact content of character.json."""
    rec: dict[str, Any] = {
        "id": ch.id,
        "name": ch.name,
        "aliases": list(ch.aliases or []),
        "look_text": ch.look_text,
        "created_at": ch.created_at.isoformat(),
        "tags": list(ch.tags or []),
        "voice_reference": ch.voice_reference or "",
    }
    optional: dict[str, Any] = {
        "master_image_url": f"/api/v1/library/characters/{ch.id}/master" if ch.master_path else "",
        "master_sha256": ch.master_sha256,
        "seed": ch.seed,
        "model": ch.model_key,
        "model_id": ch.model_id,
        "license": ch.license,
        "license_url": ch.license_url,
        "parent_character_id": ch.parent_character_id,
    }
    rec.update({k: v for k, v in optional.items() if v not in (None, "")})
    return rec


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{new_id()}.tmp")
    try:
        tmp.write_bytes(data)
        os.replace(tmp, path)
    finally:
        with contextlib.suppress(OSError):
            tmp.unlink()


def _mirror(ctx: AppContext, ch: Character) -> None:
    text = json.dumps(to_record(ch), indent=2, sort_keys=True)
    _atomic_write(library_dir(ctx, ch.id) / "character.json", text.encode("utf-8"))


def _write_master(ctx: AppContext, cid: str, data: bytes, ext: str) -> str:
    folder = library_dir(ctx, cid)
    for old in folder.glob("master.*"):
        if old.suffix != f".{ext}":
            old.unlink(missing_ok=True)
    _atomic_write(folder / f"master.{ext}", data)
    return (Path("library") / "characters" / cid / f"master.{ext}").as_posix()


def list_all(ctx: AppContext) -> list[Character]:
    with ctx.session_factory() as s:
        return list(s.scalars(select(Character).order_by(Character.created_at, Character.id)))


def get(ctx: AppContext, cid: str) -> Character | None:
    with ctx.session_factory() as s:
        return s.get(Character, cid)


def require(ctx: AppContext, cid: str) -> Character:
    ch = get(ctx, cid)
    if ch is None:
        raise CharacterNotFound(cid)
    return ch


def artifact_meta(ctx: AppContext, artifact: Artifact) -> dict[str, str]:
    """model_id and licence of an artifact, read from its sidecar."""
    path = ctx.store.absolute_path(artifact).with_suffix(".json")
    try:
        side = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        side = {}
    return {key: str(side.get(key) or "") for key in ("model_id", "license", "license_url")}


def _apply_master(ctx: AppContext, ch: Character, artifact: Artifact) -> None:
    source = ctx.store.absolute_path(artifact)
    data = source.read_bytes()
    ext = source.suffix.lstrip(".").lower()
    meta = artifact_meta(ctx, artifact)
    ch.master_path = _write_master(ctx, ch.id, data, ext)
    ch.master_sha256 = hashlib.sha256(data).hexdigest()
    ch.master_artifact_id = artifact.id
    ch.model_key = artifact.model_key
    ch.model_id = meta["model_id"] or None
    ch.license = meta["license"]
    ch.license_url = meta["license_url"]


def create(
    ctx: AppContext,
    *,
    name: str,
    look_text: str,
    aliases: list[str] | None = None,
    tags: list[str] | None = None,
    seed: int | None = None,
    voice_reference: str = "",
    master_artifact_id: str | None = None,
    parent_character_id: str | None = None,
) -> Character:
    artifact: Artifact | None = None
    if master_artifact_id is not None:
        with ctx.session_factory() as s:
            artifact = s.get(Artifact, master_artifact_id)
        if artifact is None:
            raise ArtifactNotFound(master_artifact_id)
    ch = Character(
        id=new_id(),
        name=name,
        aliases=list(aliases or []),
        look_text=look_text,
        tags=list(tags or []),
        seed=seed,
        voice_reference=voice_reference,
        parent_character_id=parent_character_id,
        created_at=utcnow(),
    )
    if artifact is not None:
        _apply_master(ctx, ch, artifact)
    with ctx.session_factory.begin() as s:
        s.add(ch)
    _mirror(ctx, ch)
    return ch


def patch(ctx: AppContext, cid: str, changes: dict[str, Any]) -> Character:
    with ctx.session_factory.begin() as s:
        ch = s.get(Character, cid)
        if ch is None:
            raise CharacterNotFound(cid)
        for key in PATCHABLE:
            if key in changes:
                setattr(ch, key, changes[key])
        s.flush()
        s.expunge(ch)
    _mirror(ctx, ch)
    return ch


def save_from_artifact(
    ctx: AppContext,
    *,
    artifact: Artifact,
    name: str,
    aliases: list[str],
    look_text: str,
    seed: int | None,
    voice_reference: str = "",
    existing_id: str | None = None,
) -> Character:
    """Create a library character from a master artifact, or update `existing_id` in place."""
    if existing_id is None:
        return create(
            ctx,
            name=name,
            aliases=aliases,
            look_text=look_text,
            seed=seed,
            voice_reference=voice_reference,
            master_artifact_id=artifact.id,
        )
    with ctx.session_factory.begin() as s:
        ch = s.get(Character, existing_id)
        if ch is None:
            raise CharacterNotFound(existing_id)
        ch.name = name
        ch.aliases = list(aliases)
        ch.look_text = look_text
        ch.seed = seed
        if voice_reference:
            ch.voice_reference = voice_reference
        _apply_master(ctx, ch, artifact)
        s.flush()
        s.expunge(ch)
    _mirror(ctx, ch)
    return ch


def make_variant(ctx: AppContext, original_id: str) -> Character:
    """A copy of a library character linked to it; the original is never written."""
    original = require(ctx, original_id)
    variant = Character(
        id=new_id(),
        name=f"{original.name} (variant)",
        aliases=list(original.aliases or []),
        look_text=original.look_text,
        tags=list(original.tags or []),
        seed=original.seed,
        model_key=original.model_key,
        model_id=original.model_id,
        license=original.license,
        license_url=original.license_url,
        master_sha256=original.master_sha256,
        master_artifact_id=original.master_artifact_id,
        voice_reference=original.voice_reference,
        parent_character_id=original.id,
        created_at=utcnow(),
    )
    if original.master_path:
        src = ctx.settings.data_root / original.master_path
        if src.is_file():
            dest = library_dir(ctx, variant.id) / src.name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dest)
            variant.master_path = (
                Path("library") / "characters" / variant.id / src.name
            ).as_posix()
    with ctx.session_factory.begin() as s:
        s.add(variant)
    _mirror(ctx, variant)
    return variant


def master_file(ctx: AppContext, ch: Character) -> tuple[Path, str] | None:
    if not ch.master_path:
        return None
    path = ctx.settings.data_root / ch.master_path
    if not path.is_file():
        return None
    return path, MASTER_MEDIA.get(path.suffix.lstrip(".").lower(), "application/octet-stream")
