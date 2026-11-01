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


def make_ctx(tmp_path: Path, **over: object):
    from reelforge.config import Settings
    from reelforge.context import AppContext

    async def unload() -> None:
        return None

    settings = Settings(
        data_root=tmp_path / "data",
        worker_poll_s=0.05,
        sample_interval_s=0.1,
        preflight_wait_s=0.0,
        health_poll_s=3600.0,
        **over,  # type: ignore[arg-type]
    )
    return AppContext.create(
        settings, available_gb=lambda: 64.0, ollama_unload=unload, doctor=lambda: _empty_report()
    )


def _empty_report():
    from reelforge.doctor import DoctorReport

    return DoctorReport(checks=[])
