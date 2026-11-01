"""Shared helpers for unit tests (conftest.py files are frozen at Gate 2)."""

from __future__ import annotations

from pathlib import Path

from reelforge.artifacts.store import ArtifactSpec, ArtifactStore
from reelforge.db.migrate import upgrade
from reelforge.db.models import Project
from reelforge.db.session import make_engine, make_session_factory


def make_store(tmp_path: Path):
    root = tmp_path / "data"
    (root / "cache" / "tmp").mkdir(parents=True)
    upgrade(root / "reelforge.db")
    engine = make_engine(root / "reelforge.db")
    sf = make_session_factory(engine)
    with sf.begin() as s:
        p = Project(slug="t", title="T", data_dir="projects/2026-01-01_t_x")
        s.add(p)
        s.flush()
        pid = p.id
    return root, sf, ArtifactStore(root, sf), pid, engine


def spec_for(pid: str, **over: object) -> ArtifactSpec:
    kw: dict[str, object] = {
        "project_id": pid,
        "owner_type": "character",
        "owner_id": "o1",
        "kind": "candidate",
        "subdir": "frames/s2",
        "prompt": "p",
        "seed": 1,
        "model_key": "image",
        "model_revision": "r1",
        "adapter": "mock",
        "version": "mock-1",
    }
    kw.update(over)
    return ArtifactSpec(**kw)  # type: ignore[arg-type]
