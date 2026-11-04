"""Migration 0005 only adds the frame and shot slot tables."""

from __future__ import annotations

import sqlite3

from alembic import command
from alembic.config import Config

from reelforge.db.migrate import MIGRATIONS_DIR, upgrade


def _tables(c):
    return {r[0] for r in c.execute("select name from sqlite_master where type='table'")}


def test_upgrade_adds_tables_and_keeps_rows(tmp_path):
    db = tmp_path / "r.db"
    upgrade(db, "0004")
    with sqlite3.connect(db) as c:
        c.execute(
            "insert into projects (id, slug, title, data_dir, stage, created_at, updated_at) "
            "values ('p1','s','t','/x','DRAFT','2026-01-01','2026-01-01')"
        )
    upgrade(db)
    with sqlite3.connect(db) as c:
        assert {"frame_slots", "shot_slots"} <= _tables(c)
        assert c.execute("select count(*) from projects").fetchone() == (1,)
        for table in ("frame_slots", "shot_slots"):
            pk = {r[1] for r in c.execute(f"pragma table_info({table})") if r[5]}
            assert pk == {"project_id", "story_key"}


def test_downgrade_drops_tables(tmp_path):
    db = tmp_path / "r.db"
    upgrade(db)
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
    cfg.set_main_option("db_path", str(db))
    command.downgrade(cfg, "0004")
    with sqlite3.connect(db) as c:
        assert not {"frame_slots", "shot_slots"} & _tables(c)
