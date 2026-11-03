import ast
import json
import os
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np
import pytest

from reelforge.adapters import tts_worker
from reelforge.adapters.tts_worker import main, resample, run_batch

WORKER = Path(tts_worker.__file__)


def _line(i, text, **over):
    return {
        "id": f"l{i}",
        "text": text,
        "model": "m/a",
        "voice": None,
        "ref_audio": None,
        "ref_text": None,
        "speed": 1.0,
        "lang": "hi",
        **over,
    }


def _loader(loads, rate=24000, bad="BAD"):
    def load(model_id):
        loads.append(model_id)

        def synth(line):
            if bad in line["text"]:
                raise RuntimeError("boom")
            return np.sin(np.linspace(0, 100, int(rate * 0.3))).astype("float32") * 0.4, rate

        return synth

    return load


def test_three_lines_one_load(tmp_path):
    loads, ev = [], []
    code = run_batch(
        [_line(i, "a b") for i in range(3)], tmp_path, load_model=_loader(loads), emit=ev.append
    )
    assert code == 0 and loads == ["m/a"] and len(ev) == 3
    assert all((tmp_path / f"l{i}.wav").exists() for i in range(3))


def test_failed_line_continues(tmp_path):
    ev = []
    lines = [_line(0, "ok"), _line(1, "BAD"), _line(2, "ok")]
    assert run_batch(lines, tmp_path, load_model=_loader([]), emit=ev.append) == 0
    assert "error" in ev[1] and "error" not in ev[0] and "error" not in ev[2]


def test_load_failure_stops_batch(tmp_path):
    def load(_):
        raise RuntimeError("no model")

    with pytest.raises(RuntimeError, match="no model"):
        run_batch([_line(0, "x")], tmp_path, load_model=load, emit=lambda e: None)


def test_resample_changes_length():
    x = np.ones(16000, dtype="float32")
    assert resample(x, 16000).size == 24000
    assert resample(x, 24000) is x


def test_main_mock_selftest_and_bad_batch(tmp_path, capsys):
    assert main(["--selftest", "--backend", "mock"]) == 0
    assert main(["--batch", str(tmp_path / "nope.jsonl"), "--out-dir", str(tmp_path)]) != 0
    assert main([]) != 0


def test_main_mock_batch_deterministic(tmp_path, capsys):
    batch = tmp_path / "b.jsonl"
    batch.write_text(json.dumps(_line(0, "ek do teen")) + "\n")
    outs = []
    for name in ("a", "b"):
        assert (
            main(["--batch", str(batch), "--out-dir", str(tmp_path / name), "--backend", "mock"])
            == 0
        )
        outs.append((tmp_path / name / "l0.wav").read_bytes())
    assert outs[0] == outs[1]
    with wave.open(str(tmp_path / "a" / "l0.wav")) as w:
        assert (w.getframerate(), w.getnchannels(), w.getsampwidth()) == (24000, 1, 2)
    printed = [json.loads(x) for x in capsys.readouterr().out.splitlines()]
    assert [p["id"] for p in printed] == ["l0", "l0"]


def test_subprocess_without_pythonpath(tmp_path):
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    res = subprocess.run(
        [sys.executable, str(WORKER), "--selftest", "--backend", "mock"],
        capture_output=True,
        text=True,
        env=env,
        cwd=tmp_path,
        timeout=60,
    )
    assert res.returncode == 0, res.stderr


def test_source_never_imports_reelforge():
    tree = ast.parse(WORKER.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert all(not a.name.startswith("reelforge") for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0 and not (node.module or "").startswith("reelforge")
