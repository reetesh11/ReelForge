"""Artifact store: atomic file writes, sidecar JSON, sha256 and cache lookups."""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import threading
from collections.abc import Callable
from pathlib import Path, PurePosixPath
from typing import Any

from pydantic import BaseModel
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, sessionmaker

from reelforge.artifacts.fingerprint import compute_inputs_fp
from reelforge.db.models import Artifact, ArtifactInput, Project, utcnow
from reelforge.ids import new_id


class ArtifactSpec(BaseModel):
    project_id: str
    owner_type: str
    owner_id: str
    kind: str
    subdir: str
    prompt: str
    seed: int
    model_key: str
    model_revision: str
    adapter: str
    version: str
    params: dict[str, Any] = {}
    input_artifact_ids: list[str] = []
    job_id: str | None = None
    width: int | None = None
    height: int | None = None
    duration_s: float | None = None
    model_id: str = ""
    license: str = ""
    license_url: str = ""


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class ArtifactStore:
    def __init__(
        self,
        data_root: Path,
        session_factory: sessionmaker[Session],
        on_created: Callable[[Artifact], None] | None = None,
    ) -> None:
        self.data_root = data_root
        self.session_factory = session_factory
        self.on_created = on_created
        self._lock = threading.Lock()

    @property
    def cache_tmp(self) -> Path:
        return self.data_root / "cache" / "tmp"

    def absolute_path(self, artifact: Artifact) -> Path:
        return self.data_root / artifact.path

    def inputs_fp(self, spec: ArtifactSpec) -> str:
        shas: list[str] = []
        if spec.input_artifact_ids:
            with self.session_factory() as s:
                for aid in spec.input_artifact_ids:
                    row = s.get(Artifact, aid)
                    if row is None:
                        raise ValueError(f"input artifact {aid} not found")
                    shas.append(row.sha256)
        return compute_inputs_fp(
            adapter=spec.adapter,
            adapter_version=spec.version,
            model_key=spec.model_key,
            model_revision=spec.model_revision,
            prompt=spec.prompt,
            seed=spec.seed,
            params=spec.params,
            input_sha256=shas,
        )

    def lookup(self, spec: ArtifactSpec) -> Artifact | None:
        try:
            fp = self.inputs_fp(spec)
        except ValueError:
            return None
        with self.session_factory() as s:
            row = s.scalars(
                select(Artifact)
                .where(
                    Artifact.project_id == spec.project_id,
                    Artifact.owner_type == spec.owner_type,
                    Artifact.owner_id == spec.owner_id,
                    Artifact.kind == spec.kind,
                    Artifact.is_active.is_(True),
                    Artifact.inputs_fp == fp,
                )
                .order_by(Artifact.take_no.desc())
            ).first()
        if row is None:
            return None
        path = self.absolute_path(row)
        sidecar = path.with_suffix(".json")
        try:
            if not path.is_file() or _sha256_file(path) != row.sha256:
                return None
            parsed = json.loads(sidecar.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return row if isinstance(parsed, dict) else None

    def _stage_source(self, source: bytes | Path) -> Path:
        tmp_root = self.cache_tmp
        tmp_root.mkdir(parents=True, exist_ok=True)
        if isinstance(source, bytes):
            tmp = tmp_root / f"{new_id()}.part"
            with tmp.open("wb") as fh:
                fh.write(source)
                fh.flush()
                os.fsync(fh.fileno())
            return tmp
        if not source.is_file() or not source.resolve().is_relative_to(tmp_root.resolve()):
            raise ValueError("source path must be a file inside cache/tmp")
        return source

    def write(self, spec: ArtifactSpec, source: bytes | Path, *, ext: str) -> Artifact:
        if "." in ext or "/" in ext or not ext:
            raise ValueError("ext must be given without a dot")
        sub = PurePosixPath(spec.subdir)
        if sub.is_absolute() or ".." in sub.parts:
            raise ValueError("subdir must be relative to the project folder")
        fp = self.inputs_fp(spec)
        tmp = self._stage_source(source)
        moved: list[Path] = []
        try:
            sha = _sha256_file(tmp)
            with self._lock:
                with self.session_factory() as s:
                    project = s.get(Project, spec.project_id)
                    if project is None:
                        raise ValueError(f"project {spec.project_id} not found")
                    data_dir = project.data_dir
                    take = (
                        s.scalar(
                            select(func.max(Artifact.take_no)).where(
                                Artifact.project_id == spec.project_id,
                                Artifact.owner_type == spec.owner_type,
                                Artifact.owner_id == spec.owner_id,
                                Artifact.kind == spec.kind,
                            )
                        )
                        or 0
                    ) + 1
                target_dir = self.data_root / data_dir / spec.subdir
                target_dir.mkdir(parents=True, exist_ok=True)
                while (target_dir / f"take_{take:03d}.{ext}").exists():
                    take += 1
                rel = (PurePosixPath(data_dir) / sub / f"take_{take:03d}.{ext}").as_posix()
                dest = self.data_root / rel
                row = Artifact(
                    id=new_id(),
                    project_id=spec.project_id,
                    owner_type=spec.owner_type,
                    owner_id=spec.owner_id,
                    kind=spec.kind,
                    take_no=take,
                    path=rel,
                    sha256=sha,
                    inputs_fp=fp,
                    prompt=spec.prompt,
                    version=spec.version,
                    params=spec.params,
                    model_key=spec.model_key,
                    seed=spec.seed,
                    status="ready",
                    is_active=True,
                    duration_s=spec.duration_s,
                    width=spec.width,
                    height=spec.height,
                    created_by_job=spec.job_id,
                    created_at=utcnow(),
                )
                sidecar = {
                    "id": row.id,
                    "kind": row.kind,
                    "owner_type": row.owner_type,
                    "owner_id": row.owner_id,
                    "take_no": take,
                    "prompt": row.prompt,
                    "seed": row.seed,
                    "model": row.model_key,
                    "model_id": spec.model_id,
                    "model_revision": spec.model_revision,
                    "version": row.version,
                    "adapter": spec.adapter,
                    "params": row.params,
                    "inputs_fp": fp,
                    "job_id": spec.job_id,
                    "sha256": sha,
                    "created_at": row.created_at.isoformat(),
                }
                if spec.license:
                    sidecar["license"] = spec.license
                if spec.license_url:
                    sidecar["license_url"] = spec.license_url
                sidecar_tmp = self.cache_tmp / f"{new_id()}.part"
                moved.append(sidecar_tmp)
                sidecar_tmp.write_text(json.dumps(sidecar, indent=2, sort_keys=True))
                os.rename(tmp, dest)
                moved.append(dest)
                moved.remove(sidecar_tmp)
                os.rename(sidecar_tmp, dest.with_suffix(".json"))
                moved.append(dest.with_suffix(".json"))
                with self.session_factory.begin() as s:
                    s.execute(
                        update(Artifact)
                        .where(
                            Artifact.project_id == spec.project_id,
                            Artifact.owner_type == spec.owner_type,
                            Artifact.owner_id == spec.owner_id,
                            Artifact.kind == spec.kind,
                        )
                        .values(is_active=False)
                    )
                    s.add(row)
                    s.flush()
                    for input_id in spec.input_artifact_ids:
                        s.add(ArtifactInput(artifact_id=row.id, input_artifact_id=input_id))
        except BaseException:
            for leftover in (tmp, *moved):
                with contextlib.suppress(OSError):
                    leftover.unlink()
            raise
        if self.on_created is not None:
            self.on_created(row)
        return row

    def register_in_place(
        self, spec: ArtifactSpec, path: Path, *, kind_active: bool = True
    ) -> Artifact:
        """Register a file that already sits under the project folder.

        The file is not moved and no sidecar is written; other rows are left as they are.
        """
        fp = self.inputs_fp(spec)
        root = self.data_root.resolve()
        resolved = path.resolve()
        if not resolved.is_relative_to(root) or not resolved.is_file():
            raise ValueError("path must be an existing file inside the data root")
        rel = resolved.relative_to(root).as_posix()
        sha = _sha256_file(resolved)
        with self._lock:
            with self.session_factory.begin() as s:
                if s.get(Project, spec.project_id) is None:
                    raise ValueError(f"project {spec.project_id} not found")
                take = (
                    s.scalar(
                        select(func.max(Artifact.take_no)).where(
                            Artifact.project_id == spec.project_id,
                            Artifact.owner_type == spec.owner_type,
                            Artifact.owner_id == spec.owner_id,
                            Artifact.kind == spec.kind,
                        )
                    )
                    or 0
                ) + 1
                row = Artifact(
                    id=new_id(),
                    project_id=spec.project_id,
                    owner_type=spec.owner_type,
                    owner_id=spec.owner_id,
                    kind=spec.kind,
                    take_no=take,
                    path=rel,
                    sha256=sha,
                    inputs_fp=fp,
                    prompt=spec.prompt,
                    version=spec.version,
                    params=spec.params,
                    model_key=spec.model_key,
                    seed=spec.seed,
                    status="ready",
                    is_active=kind_active,
                    duration_s=spec.duration_s,
                    width=spec.width,
                    height=spec.height,
                    created_by_job=spec.job_id,
                    created_at=utcnow(),
                )
                s.add(row)
                s.flush()
                for input_id in spec.input_artifact_ids:
                    s.add(ArtifactInput(artifact_id=row.id, input_artifact_id=input_id))
                s.expunge(row)
        if self.on_created is not None:
            self.on_created(row)
        return row
