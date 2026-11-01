"""Story versions, approve, semantic diff and staleness (computed on read)."""

from __future__ import annotations

import time

import yaml_samples as ys
from _helpers import make_ctx

from reelforge.artifacts.store import ArtifactSpec
from reelforge.db.models import Project
from reelforge.story import service
from reelforge.story.schema import Story
from reelforge.story.staleness import diff_stories
from reelforge.story.yamlio import parse_story


def _project(ctx) -> str:
    with ctx.session_factory.begin() as s:
        p = Project(slug="t", title="T", data_dir="projects/p1")
        s.add(p)
        s.flush()
        return p.id


def _story(text: str = ys.STORY) -> Story:
    return parse_story(text)


def test_version_numbers_and_single_current(tmp_path):
    ctx = make_ctx(tmp_path)
    pid = _project(ctx)
    for expected in (1, 2, 3):
        assert service.save_version(ctx, pid, ys.STORY).version == expected
    rows = service.list_versions(ctx, pid)
    assert [r.version for r in rows] == [3, 2, 1]
    assert [r.is_current for r in rows] == [True, False, False]
    assert (ctx.settings.data_root / "projects/p1/story.yaml").read_text() == ys.STORY


def test_stage_only_drops_to_draft_on_semantic_change(tmp_path):
    ctx = make_ctx(tmp_path)
    pid = _project(ctx)
    service.save_version(ctx, pid, ys.STORY)
    assert service.approve(ctx, pid).stage == "STORY_APPROVED"
    same = service.save_version(ctx, pid, ys.STORY.replace("# a tale", "# other"))
    assert same.affected == []
    assert service.approve(ctx, pid).stage == "STORY_APPROVED"
    changed = service.save_version(ctx, pid, ys.STORY.replace("Hello", "Bye"))
    assert [(a.owner_id, a.kinds) for a in changed.affected] == [("s2", ["voice_take", "shot"])]
    with ctx.session_factory() as s:
        assert s.get(Project, pid).stage == "DRAFT"  # type: ignore[union-attr]


def test_approve_is_idempotent_and_needs_story(tmp_path):
    ctx = make_ctx(tmp_path)
    pid = _project(ctx)
    try:
        service.approve(ctx, pid)
    except service.NoStory:
        pass
    else:
        raise AssertionError("expected NoStory")
    service.save_version(ctx, pid, ys.STORY)
    service.approve(ctx, pid)
    first = service.current_version(ctx, pid).approved_at  # type: ignore[union-attr]
    service.approve(ctx, pid)
    assert service.current_version(ctx, pid).approved_at == first  # type: ignore[union-attr]


def test_diff_rules():
    base = _story()
    line = _story(ys.STORY.replace("Hello", "Bye"))
    assert [(a.owner_id, a.kinds) for a in diff_stories(base, line)] == [
        ("s2", ["voice_take", "shot"])
    ]
    action = _story(ys.STORY.replace('"enters"', '"leaves"'))
    assert [(a.owner_id, a.kinds) for a in diff_stories(base, action)] == [("s1", ["*"])]
    look = _story(ys.STORY.replace("big eyes", "small eyes"))
    assert [(a.owner_type, a.owner_id) for a in diff_stories(base, look)] == [
        ("character", "tomato")
    ]
    top = _story(ys.STORY.replace("fps: 24", "fps: 30"))
    assert {(a.owner_type, a.owner_id) for a in diff_stories(base, top)} == {
        ("scene", "s1"),
        ("scene", "s2"),
        ("character", "tomato"),
    }
    title = _story(ys.STORY.replace('"Wedding"', '"Other"'))
    assert diff_stories(base, title) == []
    reordered = base.model_copy(update={"scenes": list(reversed(base.scenes))})
    assert diff_stories(base, reordered) == []


def test_stale_uses_artifacts_through_store(tmp_path):
    ctx = make_ctx(tmp_path)
    pid = _project(ctx)
    service.save_version(ctx, pid, ys.STORY)
    service.approve(ctx, pid)
    for owner, kind in [("s2", "voice_take"), ("s2", "frame"), ("s1", "shot")]:
        ctx.store.write(
            ArtifactSpec(
                project_id=pid,
                owner_type="scene",
                owner_id=owner,
                kind=kind,
                subdir="x",
                prompt="p",
                seed=1,
                model_key="image",
                model_revision="r1",
                adapter="mock",
                version="mock-1",
            ),
            kind.encode(),
            ext="png",
        )
    time.sleep(0.05)
    service.save_version(ctx, pid, ys.STORY.replace("Hello", "Bye"))
    items = service.stale_items(ctx, pid)
    assert {(i.owner_id, i.kind) for i in items} == {("s2", "voice_take")}
