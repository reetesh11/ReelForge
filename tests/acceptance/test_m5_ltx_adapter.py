"""m5 AC-5 (doctor flag check), AC-6 (adapter exit classification), R5/R6 (argv of a real run)."""

from __future__ import annotations

import asyncio
import threading
import time

import pytest
from m5_helpers import REQ, calls, fake_ltx, ltx_task, opt, run_ltx

SUBS = ("a2v", "generate", "extend")


def test_required_flags_exact():
    from reelforge.adapters.ltx import REQUIRED_FLAGS

    assert REQUIRED_FLAGS == {
        "a2v": ("--prompt", "--output", "--audio", "--image", "--frame-rate", "--frames", "--width",
                "--height", "--model", "--seed", "--distilled", "--low-ram"),
        "generate": ("--prompt", "--output", "--image", "--frame-rate", "--frames", "--width",
                     "--height", "--model", "--seed", "--distilled", "--low-ram", "--no-audio"),
        "extend": ("--prompt", "--output", "--video", "--extend-frames", "--distilled", "--low-ram",
                   "--image"),
    }


def test_parse_flags_finds_long_options():
    from reelforge.adapters.ltx import parse_flags

    text = "Usage: x\n  --prompt TEXT  the prompt\n  -p, --frame-rate INT\n  --no-audio / --audio\n  --3d-mode\n  a-b --c"
    assert parse_flags(text) == {"--prompt", "--frame-rate", "--no-audio", "--audio", "--3d-mode", "--c"}


def test_check_passes_when_all_flags_present(tmp_path):
    from reelforge.adapters.ltx import LtxAdapter

    fake_ltx(tmp_path)
    rep = LtxAdapter(tmp_path).check()
    assert rep.ok and rep.name == "ltx", rep.detail
    other = tmp_path / "other"
    flags = {k: list(v) for k, v in REQ.items()}
    flags["generate"].remove("--no-audio")
    fake_ltx(other, help_flags=flags)
    assert not LtxAdapter(other).check().ok


def test_check_extra_flags_are_fine(tmp_path):
    from reelforge.adapters.ltx import LtxAdapter

    fake_ltx(tmp_path, help_flags={k: [*v, "--extra-thing"] for k, v in REQ.items()})
    assert LtxAdapter(tmp_path).check().ok
    other = tmp_path / "other"
    fake_ltx(other, help_flags={k: [f for f in v if f != "--model"] for k, v in REQ.items()})
    assert "--model" in LtxAdapter(other).check().detail


def test_check_missing_flags_message_format(tmp_path):
    from reelforge.adapters.ltx import LtxAdapter

    flags = {k: list(v) for k, v in REQ.items()}
    flags["a2v"].remove("--frame-rate")
    flags["extend"].remove("--image")
    fake_ltx(tmp_path, help_flags=flags)
    rep = LtxAdapter(tmp_path).check()
    assert not rep.ok
    assert rep.detail == "ltx-2-mlx is missing required options: a2v: --frame-rate; extend: --image"


def test_check_lists_several_missing_flags_in_required_order(tmp_path):
    from reelforge.adapters.ltx import LtxAdapter

    flags = {k: list(v) for k, v in REQ.items()}
    flags["generate"] = [f for f in flags["generate"] if f not in ("--seed", "--no-audio")]
    fake_ltx(tmp_path, help_flags=flags)
    rep = LtxAdapter(tmp_path).check()
    assert rep.detail == "ltx-2-mlx is missing required options: generate: --seed, --no-audio"


def test_check_executable_missing(tmp_path):
    from reelforge.adapters.ltx import LtxAdapter

    (tmp_path / ".venv" / "bin").mkdir(parents=True)
    rep = LtxAdapter(tmp_path).check()
    assert not rep.ok
    assert rep.detail == f"ltx-2-mlx executable not found in {tmp_path}/.venv/bin"


def test_check_help_that_cannot_run(tmp_path):
    from reelforge.adapters.ltx import LtxAdapter

    flags = {k: list(v) for k, v in REQ.items()}
    del flags["extend"]  # the fake exits 2 for an unknown subcommand
    fake_ltx(tmp_path, help_flags=flags)
    rep = LtxAdapter(tmp_path).check()
    assert not rep.ok and rep.detail == "ltx-2-mlx could not run 'extend --help'"


def test_async_health_matches_check(tmp_path):
    from reelforge.adapters.ltx import LtxAdapter

    fake_ltx(tmp_path)
    a = LtxAdapter(tmp_path)
    assert asyncio.run(a.health()).ok
    assert asyncio.run(a.capabilities()) == {"video"}


def test_doctor_check_ltx_fails_with_the_message_and_keeps_key(tmp_path):
    from reelforge.config import Settings
    from reelforge.doctor import CHECKS, check_ltx

    flags = {k: list(v) for k, v in REQ.items()}
    flags["a2v"].remove("--audio")
    fake_ltx(tmp_path, help_flags=flags)
    res = check_ltx(Settings(data_root=tmp_path / "d", ltx_path=tmp_path))
    assert res.name == "ltx" and res.status == "fail" and res.severity == "blocking"
    assert res.detail == "ltx-2-mlx is missing required options: a2v: --audio"
    assert list(CHECKS).index("ltx") == 3
    good = tmp_path / "good"
    fake_ltx(good)
    ok = check_ltx(Settings(data_root=tmp_path / "d", ltx_path=good))
    assert ok.status == "pass"


# run() ---------------------------------------------------------------------------

def test_run_a2v_argv(tmp_path):
    from reelforge.adapters.ltx import LtxAdapter

    proj = tmp_path / "proj"
    exe, log = fake_ltx(proj, help_flags=None)
    task = ltx_task(tmp_path, "a2v")
    out = run_ltx(LtxAdapter(proj), task, tmp_path)
    assert len(out) == 1 and out[0].path.name == "out.mp4" and out[0].path.exists()
    (argv,) = calls(log)
    assert argv[0] == "a2v"
    assert opt(argv, "--prompt") == "a tomato waves"
    assert opt(argv, "--image") == str(task.input_paths[0])
    assert opt(argv, "--audio") == str(task.input_paths[1])
    assert opt(argv, "--output") == str(tmp_path / "out" / "out.mp4")
    assert (opt(argv, "--frame-rate"), opt(argv, "--frames")) == ("24", "81")
    assert (opt(argv, "--width"), opt(argv, "--height")) == ("320", "576")
    assert opt(argv, "--model") == "test-org/ltx-test" and opt(argv, "--seed") == "77"
    assert "--distilled" in argv and "--low-ram" in argv
    assert "--no-audio" not in argv


def test_run_generate_is_silent_and_has_no_audio_input(tmp_path):
    from reelforge.adapters.ltx import LtxAdapter

    proj = tmp_path / "proj"
    exe, log = fake_ltx(proj)
    run_ltx(LtxAdapter(proj), ltx_task(tmp_path, "generate"), tmp_path)
    (argv,) = calls(log)
    assert argv[0] == "generate" and "--no-audio" in argv and "--audio" not in argv
    assert opt(argv, "--image").endswith("in.png")


def test_steps_only_when_model_has_steps_and_help_lists_it(tmp_path):
    from reelforge.adapters.ltx import LtxAdapter

    proj = tmp_path / "proj"
    with_steps = {k: [*v, "--steps"] for k, v in REQ.items()}
    exe, log = fake_ltx(proj, help_flags=with_steps)
    run_ltx(LtxAdapter(proj), ltx_task(tmp_path, "generate", steps=8), tmp_path)
    run_ltx(LtxAdapter(proj), ltx_task(tmp_path, "generate", steps=None), tmp_path)
    first, second = calls(log)
    assert opt(first, "--steps") == "8" and "--steps" not in second
    proj2 = tmp_path / "proj2"
    exe2, log2 = fake_ltx(proj2)
    run_ltx(LtxAdapter(proj2), ltx_task(tmp_path, "generate", steps=8), tmp_path)
    assert "--steps" not in calls(log2)[0]


@pytest.mark.parametrize("how", ["exit137", "kill9"])
def test_exit_137_and_minus_9_are_oom(tmp_path, how):
    from reelforge.adapters.base import AdapterError
    from reelforge.adapters.ltx import LtxAdapter

    proj = tmp_path / "proj"
    fake_ltx(proj, **({"mode": "exit", "code": 137} if how == "exit137" else {"mode": "kill"}))
    with pytest.raises(AdapterError) as ei:
        run_ltx(LtxAdapter(proj), ltx_task(tmp_path, "a2v"), tmp_path)
    assert str(ei.value) == "Killed, likely out of memory."


def test_other_nonzero_exit_names_last_stderr_line(tmp_path):
    from reelforge.adapters.base import AdapterError
    from reelforge.adapters.ltx import LtxAdapter

    proj = tmp_path / "proj"
    fake_ltx(proj, mode="exit", code=3, stderr="warming up\nBoom: bad frames")
    with pytest.raises(AdapterError) as ei:
        run_ltx(LtxAdapter(proj), ltx_task(tmp_path, "a2v"), tmp_path)
    assert str(ei.value) == "ltx-2-mlx failed: Boom: bad frames"


def test_timeout_is_reported(tmp_path):
    from reelforge.adapters.base import AdapterError
    from reelforge.adapters.ltx import LtxAdapter

    proj = tmp_path / "proj"
    fake_ltx(proj, mode="sleep")
    t0 = time.monotonic()
    with pytest.raises(AdapterError) as ei:
        run_ltx(LtxAdapter(proj, timeout_s=0.5, sample_interval_s=0.1), ltx_task(tmp_path), tmp_path)
    assert str(ei.value) == "Timed out" and time.monotonic() - t0 < 20


def test_cancel_stops_the_subprocess(tmp_path):
    from reelforge.adapters.base import AdapterError, CancelToken
    from reelforge.adapters.ltx import LtxAdapter

    proj = tmp_path / "proj"
    fake_ltx(proj, mode="sleep")
    cancel = CancelToken()
    threading.Timer(0.8, cancel.cancel).start()
    t0 = time.monotonic()
    with pytest.raises(AdapterError) as ei:
        run_ltx(LtxAdapter(proj, sample_interval_s=0.1), ltx_task(tmp_path), tmp_path, cancel)
    assert str(ei.value) == "cancelled" and time.monotonic() - t0 < 15
