"""Migration 0006 only adds the emotion clip table."""

import sqlite3

from alembic import command
from alembic.config import Config

from reelforge.db.migrate import MIGRATIONS_DIR, upgrade


def _tables(c):
    return {r[0] for r in c.execute("select name from sqlite_master where type='table'")}


def test_upgrade_adds_the_table_and_keeps_rows(tmp_path):
    db = tmp_path / "r.db"
    upgrade(db, "0005")
    with sqlite3.connect(db) as c:
        c.execute(
            "insert into projects (id, slug, title, data_dir, stage, created_at, updated_at) "
            "values ('p1','s','t','/x','DRAFT','2026-01-01','2026-01-01')"
        )
    upgrade(db)
    with sqlite3.connect(db) as c:
        assert "voice_emotion_clips" in _tables(c)
        assert c.execute("select count(*) from projects").fetchone() == (1,)
        pk = {r[1] for r in c.execute("pragma table_info(voice_emotion_clips)") if r[5]}
        assert pk == {"project_id", "story_key", "emotion"}


def test_downgrade_drops_the_table(tmp_path):
    db = tmp_path / "r.db"
    upgrade(db)
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
    cfg.set_main_option("db_path", str(db))
    command.downgrade(cfg, "0005")
    with sqlite3.connect(db) as c:
        assert "voice_emotion_clips" not in _tables(c)
