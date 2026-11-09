import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "acceptance"))

from m6c_helpers import STD_CUES, at, audio_url, cue, generated, light_world, take_artifacts  # noqa: E402  # pyright: ignore[reportMissingImports]

from reelforge.audio.state import NEEDS_APPROVAL  # noqa: E402


def test_a_second_request_returns_the_unfinished_job(tmp_path):
    with light_world(tmp_path, STD_CUES) as (ctx, client, pid):
        a = client.post(audio_url(pid, "/cues/fx1:generate")).json()
        b = client.post(audio_url(pid, "/cues/fx1:generate")).json()
        assert a["id"] == b["id"]


def test_a_suggested_cue_is_refused_without_a_job(tmp_path):
    cues = [cue("s1x", "sfx", at("s1"), duration=1.0, state="suggested")]
    with light_world(tmp_path, cues) as (ctx, client, pid):
        r = client.post(audio_url(pid, "/cues/s1x:generate"))
        assert (r.status_code, r.json()["detail"]) == (409, NEEDS_APPROVAL)
        assert ctx.queue.list(project_id=pid) == []


def test_take_numbers_count_up_and_each_new_take_is_picked(tmp_path):
    with light_world(tmp_path, STD_CUES) as (ctx, client, pid):
        for n in (1, 2, 3):
            generated(client, ctx, pid, "fx1")
            arts = take_artifacts(ctx, pid, "fx1")
            assert [a.take_no for a in arts] == list(range(1, n + 1))
            out = client.get(audio_url(pid)).json()["cues"][1]
            assert out["picked_take_id"] == arts[-1].id
