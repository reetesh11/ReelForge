"""AC-13: migrations create all tables with WAL; ULIDs; relative paths."""

from __future__ import annotations

import sqlite3
import time

from rf_helpers import create_project, make_client, make_ctx, make_settings, store_bytes

TABLES = {
    "projects",
    "story_versions",
    "characters",
    "voices",
    "project_characters",
    "scenes",
    "lines",
    "artifacts",
    "artifact_inputs",
    "jobs",
    "approvals",
    "reel_versions",
    "brand_kits",
    "settings",
}


def test_upgrade_on_empty_db_creates_all_tables_with_wal(tmp_path):
    from reelforge.db.migrate import upgrade

    db = tmp_path / "nested" / "reelforge.db"
    upgrade(db)
    assert db.exists()
    with sqlite3.connect(db) as c:
        names = {
            r[0] for r in c.execute("select name from sqlite_master where type='table'")
        }
        assert TABLES <= names
        assert c.execute("pragma journal_mode").fetchone()[0] == "wal"
    upgrade(db)  # idempotent
    upgrade(str(db), "head")


def test_engine_sets_pragmas_on_every_connection(tmp_path):
    from reelforge.db.migrate import upgrade
    from reelforge.db.session import make_engine
    from sqlalchemy import text

    db = tmp_path / "r.db"
    upgrade(db)
    engine = make_engine(db)
    for _ in range(2):
        with engine.connect() as c:
            assert c.execute(text("pragma journal_mode")).scalar() == "wal"
            assert c.execute(text("pragma foreign_keys")).scalar() == 1
            assert c.execute(text("pragma busy_timeout")).scalar() == 5000
    engine.dispose()


def test_models_map_to_expected_table_names():
    from reelforge.db import models as m

    mapping = {
        "Project": "projects",
        "StoryVersion": "story_versions",
        "Character": "characters",
        "Voice": "voices",
        "ProjectCharacter": "project_characters",
        "Scene": "scenes",
        "Line": "lines",
        "Artifact": "artifacts",
        "ArtifactInput": "artifact_inputs",
        "Job": "jobs",
        "Approval": "approvals",
        "ReelVersion": "reel_versions",
        "BrandKit": "brand_kits",
        "Setting": "settings",
    }
    for cls, table in mapping.items():
        assert getattr(m, cls).__tablename__ == table


def test_ulids():
    from reelforge.ids import is_ulid, new_id

    a = new_id()
    time.sleep(0.01)
    b = new_id()
    assert len(a) == 26 and is_ulid(a) and is_ulid(b) and a < b
    assert (
        not is_ulid("")
        and not is_ulid("abc")
        and not is_ulid("U" * 26)
        and not is_ulid("0" * 25)
    )
    assert is_ulid("01ARZ3NDEKTSV4RRFFQ69G5FAV")


def test_ids_and_stored_paths_are_ulid_and_relative(tmp_path):
    from reelforge.ids import is_ulid

    ctx = make_ctx(make_settings(tmp_path))
    root = str(ctx.settings.data_root)
    with make_client(ctx, start_worker=False) as client:
        proj = create_project(client)
        job = ctx.queue.enqueue(type="x", project_id=proj["id"])
    assert is_ulid(proj["id"]) and is_ulid(job.id)
    assert not proj["data_dir"].startswith("/") and root not in proj["data_dir"]
    assert (ctx.settings.data_root / proj["data_dir"]).is_dir()
    _, art = store_bytes(ctx, proj["id"])
    assert is_ulid(art.id)
    assert not art.path.startswith("/") and root not in art.path
    assert (ctx.settings.data_root / art.path).is_file()
    ctx.close()


def test_context_creates_data_root_layout(tmp_path):
    ctx = make_ctx(make_settings(tmp_path))
    root = ctx.settings.data_root
    for sub in ("cache/tmp", "logs/jobs", "projects"):
        assert (root / sub).is_dir()
    assert ctx.settings.db_path.exists()
    ctx.close()
