"""Edit operations on the working EDL (no media needed)."""

from __future__ import annotations

from pathlib import Path

import pytest
from _helpers import make_client, make_ctx

from reelforge.assembly.build import working_edl_path
from reelforge.assembly.edit import apply_edit
from reelforge.assembly.edl import Edl, EdlCaption, EdlDialogue, EdlShot, save_edl
from reelforge.assembly.state import AssemblyError
from reelforge.db.models import Project


def _setup(tmp_path: Path):
    ctx = make_ctx(tmp_path)
    with ctx.session_factory.begin() as s:
        p = Project(slug="t", title="T", data_dir="projects/t", stage="SHOTS_APPROVED")
        s.add(p)
        s.flush()
        pid = p.id
    shots = [
        EdlShot(scene_id=f"s{i}", artifact=f"a{i}", source_duration_s=2.0, in_s=0.0, out_s=2.0)
        for i in (1, 2, 3)
    ]
    edl = Edl(
        project_id=pid,
        video=shots,
        dialogue=[
            EdlDialogue(scene_id="s1", artifact="v1", offset_s=0.0, duration_s=1.5),
            EdlDialogue(scene_id="s3", artifact="v3", offset_s=4.0, duration_s=1.5),
        ],
        captions=[
            EdlCaption(scene_id="s1", speaker="A", line_no=1, text="one", start_s=0, end_s=1.5),
            EdlCaption(scene_id="s3", speaker="B", line_no=2, text="three", start_s=4, end_s=5.5),
        ],
    )
    save_edl(edl, working_edl_path(ctx, pid))
    return ctx, pid


def test_trim_rounds_and_keeps_minimum_length(tmp_path: Path) -> None:
    ctx, pid = _setup(tmp_path)
    edl, notes = apply_edit(
        ctx, pid, {"op": "trim", "scene_id": "s2", "in_s": 0.123, "out_s": 1.987}
    )
    assert (edl.video[1].in_s, edl.video[1].out_s) == (0.12, 1.99) and notes == []
    with pytest.raises(AssemblyError) as exc:
        apply_edit(ctx, pid, {"op": "trim", "scene_id": "s2", "in_s": 1.0, "out_s": 1.2})
    assert (exc.value.status, exc.value.message) == (422, "A shot must be at least 0.5 s long.")
    ctx.close()


def test_trim_cuts_dialogue_that_runs_past_the_end(tmp_path: Path) -> None:
    ctx, pid = _setup(tmp_path)
    edl, notes = apply_edit(ctx, pid, {"op": "trim", "scene_id": "s3", "in_s": 0.0, "out_s": 1.0})
    assert notes == ["Dialogue was trimmed to fit."]
    clip = edl.dialogue[1]
    assert clip.offset_s + clip.duration_s <= edl.total_duration_s + 1e-6
    assert edl.captions[1].end_s == pytest.approx(clip.offset_s + clip.duration_s)
    ctx.close()


def test_reorder_moves_clips_and_renumbers_captions(tmp_path: Path) -> None:
    ctx, pid = _setup(tmp_path)
    edl, _ = apply_edit(ctx, pid, {"op": "reorder", "scene_ids": ["s3", "s1", "s2"]})
    assert [d.scene_id for d in edl.dialogue] == ["s3", "s1"]
    assert [d.offset_s for d in edl.dialogue] == [0.0, 2.0]
    assert [(c.scene_id, c.line_no) for c in edl.captions] == [("s3", 1), ("s1", 2)]
    with pytest.raises(AssemblyError):
        apply_edit(ctx, pid, {"op": "reorder", "scene_ids": ["s1"]})
    ctx.close()


def test_transition_is_capped_and_noted(tmp_path: Path) -> None:
    ctx, pid = _setup(tmp_path)
    apply_edit(ctx, pid, {"op": "trim", "scene_id": "s2", "in_s": 0.0, "out_s": 0.6})
    edl, notes = apply_edit(ctx, pid, {"op": "set_transition", "scene_id": "s2", "seconds": 0.5})
    assert edl.video[1].transition_in_s == pytest.approx(0.3)
    assert "Crossfade shortened to fit" in notes
    with pytest.raises(AssemblyError) as exc:
        apply_edit(ctx, pid, {"op": "set_transition", "scene_id": "s3", "seconds": 0.6})
    assert exc.value.status == 422
    ctx.close()


def test_nudge_and_caption_edits(tmp_path: Path) -> None:
    ctx, pid = _setup(tmp_path)
    edl, _ = apply_edit(ctx, pid, {"op": "nudge_dialogue", "scene_id": "s1", "offset_s": 1.0})
    assert edl.dialogue[0].offset_s == 1.0 and edl.captions[0].start_s == 1.0
    with pytest.raises(AssemblyError) as exc:
        apply_edit(ctx, pid, {"op": "nudge_dialogue", "scene_id": "s1", "offset_s": 99})
    assert exc.value.message == "Dialogue cannot start before 0 or after the end of the reel."
    edl, _ = apply_edit(ctx, pid, {"op": "set_caption_text", "scene_id": "s1", "text": "new"})
    assert edl.captions[0].text == "new" and edl.dialogue[0].artifact == "v1"
    edl, _ = apply_edit(ctx, pid, {"op": "set_caption_style", "style": "bold_pop"})
    assert edl.caption_style == "bold_pop"
    with pytest.raises(AssemblyError):
        apply_edit(ctx, pid, {"op": "set_caption_style", "style": "comic_sans"})
    ctx.close()


def test_routes_are_locked_below_shots_approved(tmp_path: Path) -> None:
    ctx = make_ctx(tmp_path)
    with ctx.session_factory.begin() as s:
        p = Project(slug="t", title="T", data_dir="projects/t", stage="FRAMES_APPROVED")
        s.add(p)
        s.flush()
        pid = p.id
    with make_client(ctx, start_worker=False) as client:
        r = client.get(f"/api/v1/projects/{pid}/assembly")
        assert r.status_code == 409 and r.json() == {"detail": "Approve the shots first."}
        r = client.get("/api/v1/projects/nope/assembly")
        assert r.status_code == 404 and r.json() == {"detail": "project not found"}
    ctx.close()
