"""m6b AC-6 (no emotion behaves as before) and AC-12 (response shapes keep their keys): green today."""

from __future__ import annotations

from m3_helpers import approved_project, get_cast, new_world
from m6b_helpers import LINES, active_take, voice_world, gen_lines, line_of, project_with_presets, rows_for
from m6b_helpers import get_voices, take_rows, wrap_worker

LINE_KEYS_NEW = {"emotion", "edit_text", "effective", "settings_changed"}


def test_plain_line_has_exactly_todays_params_and_row(tmp_path, monkeypatch):
    ctx, client = voice_world(tmp_path)
    log = wrap_worker(tmp_path, monkeypatch)
    with client:
        pid = project_with_presets(client, ctx)
        gen_lines(client, ctx, pid, "s1", "s2")
        for s in ("s1", "s2"):
            t = take_rows(ctx, pid, s)[0]
            assert set(t.params) == {"text", "speed", "voice", "source"}, t.params
            assert t.params["text"] == LINES[s] and t.params["speed"] == 1.0
            row = rows_for(log, s)[0]
            assert row["id"] == s and row["text"] == LINES[s] and row["speed"] == 1.0


def test_voices_response_omits_new_fields_when_empty(tmp_path):
    ctx, client = voice_world(tmp_path)
    with client:
        pid = project_with_presets(client, ctx)
        gen_lines(client, ctx, pid, "s1")
        v = get_voices(client, pid)
        for ln in v["lines"]:
            assert not LINE_KEYS_NEW & set(ln), ln
            for t in ln["takes"]:
                assert "settings" not in t
        assert line_of(client, pid, "s1")["text"] == LINES["s1"]
        assert active_take(client, pid, "s1")["stale"] is False
        for c in v["characters"]:
            assert "age" not in c and "age_band" not in c
            assert "emotion_clips" not in (c["voice"] or {})


def test_cast_items_omit_age_when_unset(tmp_path):
    ctx, client, _ = new_world(tmp_path)
    with client:
        pid = approved_project(client)
        for c in get_cast(client, pid)["characters"]:
            assert "age" not in c and "age_band" not in c
