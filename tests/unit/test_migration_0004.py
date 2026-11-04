"""Migration 0004 keeps existing rows and adds the voice columns and table."""

from __future__ import annotations

import sqlite3

from reelforge.db.migrate import upgrade


def test_upgrade_from_0003_keeps_rows(tmp_path):
    db = tmp_path / "r.db"
    upgrade(db, "0003")
    with sqlite3.connect(db) as c:
        c.execute("insert into voices (id, mode, speed, language) values ('v1','preset',1.0,'hi')")
        c.execute(
            "insert into projects (id, slug, title, data_dir, stage, created_at, updated_at) "
            "values ('p1','s','t','/x','DRAFT','2026-01-01','2026-01-01')"
        )
        c.execute(
            "insert into scenes (id, project_id, story_key, position, shot_type, duration_s) "
            "values ('sc1','p1','s1',1,'',3.0)"
        )
    upgrade(db)
    with sqlite3.connect(db) as c:
        assert c.execute("select mode, reference_text, reference_path from voices").fetchone() == (
            "preset",
            "",
            None,
        )
        assert c.execute("select duration_s, shot_length_at from scenes").fetchone() == (3.0, None)
        assert "approved_artifact_id" in {r[1] for r in c.execute("pragma table_info(lines)")}
        pk = {r[1] for r in c.execute("pragma table_info(voice_slots)") if r[5]}
        assert pk == {"project_id", "story_key"}
        cols = {r[1] for r in c.execute("pragma table_info(voices)")}
        assert {"reference_sha256", "clip_seconds"} <= cols
