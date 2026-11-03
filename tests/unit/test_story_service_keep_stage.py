import yaml_samples as ys
from _helpers import make_ctx
from sqlalchemy import select

from reelforge.db.models import Project, StoryChange
from reelforge.story import service


def _approved(tmp_path):
    ctx = make_ctx(tmp_path)
    with ctx.session_factory.begin() as s:
        p = Project(slug="t", title="T", data_dir="projects/p1")
        s.add(p)
        s.flush()
        pid = p.id
    service.save_version(ctx, pid, ys.STORY)
    service.approve(ctx, pid)
    return ctx, pid


def _stage(ctx, pid):
    with ctx.session_factory() as s:
        return s.get(Project, pid).stage


def _changes(ctx, pid):
    with ctx.session_factory() as s:
        return list(s.scalars(select(StoryChange).where(StoryChange.project_id == pid)))


def test_default_edit_resets_stage_to_draft(tmp_path):
    ctx, pid = _approved(tmp_path)
    service.save_version(ctx, pid, ys.STORY.replace("Hello", "Namaste"))
    assert _stage(ctx, pid) == "DRAFT"


def test_keep_stage_keeps_stage_and_approval_and_records_changes(tmp_path):
    ctx, pid = _approved(tmp_path)
    saved = service.save_version(
        ctx, pid, ys.STORY.replace("Hello", "Namaste"), keep_stage=True
    )
    assert _stage(ctx, pid) == "STORY_APPROVED"
    assert saved.approved_at is not None
    assert [(c.owner_id, c.kinds) for c in _changes(ctx, pid)] == [("s2", ["voice_take", "shot"])]


def test_record_changes_false_records_nothing(tmp_path):
    ctx, pid = _approved(tmp_path)
    service.save_version(
        ctx, pid, ys.STORY.replace("Hello", "Namaste"), keep_stage=True, record_changes=False
    )
    assert _changes(ctx, pid) == []
