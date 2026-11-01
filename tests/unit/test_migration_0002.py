"""Migration 0002 keeps existing rows and adds the story columns and table."""

from __future__ import annotations

import sqlite3

from reelforge.db.migrate import upgrade


def test_upgrade_from_0001_keeps_story_versions(tmp_path):
    db = tmp_path / "r.db"
    upgrade(db, "0001")
    with sqlite3.connect(db) as c:
        c.execute(
            "insert into projects (id, slug, title, data_dir, stage, created_at, updated_at) "
            "values ('p1','s','t','d','DRAFT','2026-01-01','2026-01-01')"
        )
        c.execute(
            "insert into story_versions (id, project_id, version, yaml_text, is_current) "
            "values ('v1','p1',1,'x',1)"
        )
    upgrade(db)
    with sqlite3.connect(db) as c:
        row = c.execute("select yaml_text, is_current, created_at from story_versions").fetchone()
        assert row[0] == "x" and row[1] == 1 and row[2] is not None
        cols = {r[1] for r in c.execute("pragma table_info(jobs)")}
        assert "result" in cols
        tables = {r[0] for r in c.execute("select name from sqlite_master where type='table'")}
        assert "story_changes" in tables
