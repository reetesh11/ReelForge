"""Migration 0003 keeps existing characters and adds the cast columns and table."""

from __future__ import annotations

import sqlite3

from reelforge.db.migrate import upgrade


def test_upgrade_from_0002_keeps_characters(tmp_path):
    db = tmp_path / "r.db"
    upgrade(db, "0002")
    with sqlite3.connect(db) as c:
        c.execute(
            "insert into characters (id, name, aliases, look_text, sheet_artifact_ids, tags) "
            "values ('c1','Tamatar','[]','round','[]','[]')"
        )
    upgrade(db)
    with sqlite3.connect(db) as c:
        row = c.execute(
            "select name, look_text, license, voice_reference, created_at, seed from characters"
        ).fetchone()
        assert row[0] == "Tamatar" and row[1] == "round"
        assert row[2] == "" and row[3] == "" and row[4] is not None and row[5] is None
        cols = {r[1] for r in c.execute("pragma table_info(characters)")}
        assert {"master_path", "master_sha256", "model_id", "model_key", "license_url"} <= cols
        pk = {r[1] for r in c.execute("pragma table_info(cast_slots)") if r[5]}
        assert pk == {"project_id", "story_key"}
