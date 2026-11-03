"""Library characters: records, master image copies and the character.json mirror."""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from sqlalchemy import select

from reelforge.db.models import Artifact, Character, Voice, utcnow
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


def to_record(ch: Character, voice: dict[str, Any] | None = None) -> dict[str, Any]:
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
    if voice is not None:
        rec["voice"] = voice
    return rec


def record(ctx: AppContext, ch: Character) -> dict[str, Any]:
    """`to_record` plus the character's voice (only when it has one)."""
    return to_record(ch, voice_record(ctx, ch.id))


VOICE_KEYS = (
    "mode", "model", "voice_id", "reference_path", "reference_sha256",
    "reference_text", "speed", "language",
)  # fmt: skip


def _voice_row(ctx: AppContext, cid: str) -> Voice | None:
    with ctx.session_factory() as s:
        ch = s.get(Character, cid)
        return s.get(Voice, ch.voice_id) if ch is not None and ch.voice_id else None


def get_voice(ctx: AppContext, character_id: str) -> dict[str, Any] | None:
    v = _voice_row(ctx, character_id)
    if v is None:
        return None
    return {
        "mode": v.mode,
        "model": v.model_key,
        "voice_id": v.voice_ref,
        "reference_path": v.reference_path,
        "reference_sha256": v.reference_sha256,
        "reference_text": v.reference_text,
        "speed": v.speed,
        "language": v.language,
    }


def voice_clip_seconds(ctx: AppContext, character_id: str) -> float | None:
    v = _voice_row(ctx, character_id)
    return v.clip_seconds if v is not None else None


def voice_record(ctx: AppContext, character_id: str) -> dict[str, Any] | None:
    """The `voice` object of the library JSON (VoiceOut fields)."""
    from reelforge.voice.slots import current_voice_model  # noqa: PLC0415

    v = get_voice(ctx, character_id)
    if v is None:
        return None
    out: dict[str, Any] = {
        "mode": v["mode"],
        "model": v["model"],
        "voice_id": v["voice_id"],
        "reference_text": v["reference_text"],
        "speed": v["speed"],
        "language": v["language"],
        "model_mismatch": v["model"] is not None and v["model"] != current_voice_model(ctx),
    }
    if v["mode"] == "cloned" and v["reference_path"]:
        out["reference_url"] = f"/api/v1/library/characters/{character_id}/voice-reference"
        seconds = voice_clip_seconds(ctx, character_id)
        if seconds is not None:
            out["clip_seconds"] = seconds
    return out


def voice_reference_file(ctx: AppContext, character_id: str) -> Path | None:
    v = get_voice(ctx, character_id)
    if v is None or not v["reference_path"]:
        return None
    path = ctx.settings.data_root / v["reference_path"]
    return path if path.is_file() else None


def store_voice_reference(ctx: AppContext, cid: str, src: Path) -> tuple[str, str]:
    """Copy a clip to `voice_reference.<ext>` in the character folder; return (path, sha256)."""
    folder = library_dir(ctx, cid)
    data = src.read_bytes()
    ext = src.suffix.lstrip(".").lower() or "wav"
    for old in folder.glob("voice_reference.*"):
        if old.suffix != f".{ext}":
            old.unlink(missing_ok=True)
    _atomic_write(folder / f"voice_reference.{ext}", data)
    rel = (Path("library") / "characters" / cid / f"voice_reference.{ext}").as_posix()
    return rel, hashlib.sha256(data).hexdigest()


def set_voice(
    ctx: AppContext,
    character_id: str,
    voice: dict[str, Any] | None,
    *,
    clip_seconds: float | None = None,
) -> None:
    """Save (or with None, remove) the voice of a library character."""
    with ctx.session_factory.begin() as s:
        ch = s.get(Character, character_id)
        if ch is None:
            raise CharacterNotFound(character_id)
        row = s.get(Voice, ch.voice_id) if ch.voice_id else None
        if voice is None:
            if row is not None:
                ch.voice_id = None
                s.flush()
                s.delete(row)
        else:
            if row is None:
                row = Voice()
                s.add(row)
            row.mode = voice["mode"]
            row.model_key = voice.get("model")
            row.voice_ref = voice.get("voice_id")
            row.reference_path = voice.get("reference_path")
            row.reference_sha256 = voice.get("reference_sha256")
            row.reference_text = voice.get("reference_text") or ""
            row.speed = float(voice.get("speed") or 1.0)
            row.language = voice.get("language") or "hi"
            row.clip_seconds = clip_seconds
            s.flush()
            ch.voice_id = row.id
        s.flush()
        s.expunge(ch)
    if voice is None:
        for old in library_dir(ctx, character_id).glob("voice_reference.*"):
            old.unlink(missing_ok=True)
    _mirror(ctx, ch)


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
    text = json.dumps(record(ctx, ch), indent=2, sort_keys=True)
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
    side: dict[str, Any] = {}
    with contextlib.suppress(OSError, ValueError):
        parsed: Any = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(parsed, dict):
            side = cast("dict[str, Any]", parsed)
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
    voice = get_voice(ctx, original.id)
    if voice is not None:
        if voice["reference_path"]:
            src_clip = ctx.settings.data_root / voice["reference_path"]
            if src_clip.is_file():
                voice["reference_path"], voice["reference_sha256"] = store_voice_reference(
                    ctx, variant.id, src_clip
                )
        set_voice(ctx, variant.id, voice, clip_seconds=voice_clip_seconds(ctx, original.id))
        return require(ctx, variant.id)
    _mirror(ctx, variant)
    return variant


def master_file(ctx: AppContext, ch: Character) -> tuple[Path, str] | None:
    if not ch.master_path:
        return None
    path = ctx.settings.data_root / ch.master_path
    if not path.is_file():
        return None
    return path, MASTER_MEDIA.get(path.suffix.lstrip(".").lower(), "application/octet-stream")
