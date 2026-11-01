import pytest
from _helpers import make_store

from reelforge.db.models import Job
from reelforge.events import EventBus
from reelforge.jobs.queue import JobNotFound, JobQueue, JobStateError


def _queue(tmp_path):
    root, sf, _store, pid, engine = make_store(tmp_path)
    bus = EventBus()
    return JobQueue(sf, bus), sf, pid, engine, bus


def _set(sf, job_id, **values):
    with sf.begin() as s:
        for k, v in values.items():
            setattr(s.get(Job, job_id), k, v)


def test_state_machine(tmp_path):
    q, sf, pid, engine, _ = _queue(tmp_path)
    job = q.enqueue(type="x", project_id=pid)
    assert (job.status, job.attempts, job.progress) == ("queued", 0, 0)
    assert q.cancel(job.id).status == "cancelled"
    with pytest.raises(JobStateError):
        q.cancel(job.id)
    with pytest.raises(JobStateError):
        q.retry(job.id)
    failed = q.enqueue(type="x")
    _set(sf, failed.id, status="failed", error="e", attempts=2, progress=30)
    r = q.retry(failed.id)
    assert (r.status, r.attempts, r.error, r.progress) == ("queued", 0, None, 0)
    with pytest.raises(JobNotFound):
        q.get("nope")
    assert [j.id for j in q.list(status="queued")] == [failed.id]
    assert [j.id for j in q.list(project_id=pid)] == [job.id]
    engine.dispose()


def test_compare_and_set_blocks_second_finaliser(tmp_path):
    q, sf, _pid, engine, _ = _queue(tmp_path)
    job = q.enqueue(type="x")
    _set(sf, job.id, status="running")
    assert q.transition(job.id, "running", status="succeeded") is True
    assert q.transition(job.id, "running", status="cancelled") is False
    assert q.get(job.id).status == "succeeded"
    engine.dispose()


def test_recover_orphans(tmp_path):
    q, sf, _pid, engine, _ = _queue(tmp_path)
    job = q.enqueue(type="x", heavy=True)
    done = q.enqueue(type="y")
    _set(sf, job.id, status="running", pid=999_999, command=["nothing"])
    _set(sf, done.id, status="succeeded")
    assert q.recover_orphans() == [job.id]
    got = q.get(job.id)
    assert got.status == "queued" and got.pid is None and got.started_at is None
    assert q.recover_orphans() == []
    engine.dispose()
