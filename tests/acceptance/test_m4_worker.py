"""m4 AC-4 (tts_worker batch), R1-R3 (selftest, mock backend), AC-12 (no network)."""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys

from m4_helpers import WORKER_SRC, read_wav


def _lines(texts, **over):
    return [
        {"id": f"l{i}", "text": t, "model": "m/one", "voice": "v", "ref_audio": None,
         "ref_text": None, "speed": 1.0, "lang": "hi", **over}
        for i, t in enumerate(texts)
    ]


def _stub_loader(loads: list[str], rate: int = 24000, fail_on: str | None = None):
    def load_model(model_id: str):
        import numpy as np

        loads.append(model_id)

        def synth(line: dict):
            if fail_on and fail_on in line["text"]:
                raise RuntimeError("boom")
            n = int(rate * 0.4)
            return np.sin(np.linspace(0, 200, n)).astype("float32") * 0.5, rate

        return synth

    return load_model


def test_run_batch_three_lines_one_load(tmp_path):
    from reelforge.adapters.tts_worker import run_batch

    loads: list[str] = []
    events: list[dict] = []
    code = run_batch(_lines(["ek do", "teen char", "paanch"]), tmp_path, backend="real",
                     load_model=_stub_loader(loads), emit=events.append)
    assert code == 0 and loads == ["m/one"]
    assert [e["id"] for e in events] == ["l0", "l1", "l2"]
    for e in events:
        assert "error" not in e and e["duration_s"] > 0
        samples, rate, ch, width = read_wav(tmp_path / f"{e['id']}.wav")
        assert (rate, ch, width) == (24000, 1, 2) and samples
        assert str(e["path"]).endswith(f"{e['id']}.wav")


def test_run_batch_failed_line_carries_error_and_continues(tmp_path):
    from reelforge.adapters.tts_worker import run_batch

    loads: list[str] = []
    events: list[dict] = []
    code = run_batch(_lines(["ek", "BAD line", "teen"]), tmp_path, backend="real",
                     load_model=_stub_loader(loads, fail_on="BAD"), emit=events.append)
    assert code == 0 and len(loads) == 1
    by = {e["id"]: e for e in events}
    assert set(by) == {"l0", "l1", "l2"}
    assert "error" in by["l1"] and by["l1"]["error"]
    assert "error" not in by["l0"] and "error" not in by["l2"]
    assert (tmp_path / "l0.wav").exists() and (tmp_path / "l2.wav").exists()
    assert not (tmp_path / "l1.wav").exists()


def test_run_batch_loads_each_distinct_model_once_and_resamples(tmp_path):
    from reelforge.adapters.tts_worker import run_batch

    loads: list[str] = []
    lines = _lines(["a b"]) + _lines(["c d"], model="m/two") + _lines(["e f"])
    for i, ln in enumerate(lines):
        ln["id"] = f"x{i}"
    events: list[dict] = []
    run_batch(lines, tmp_path, load_model=_stub_loader(loads, rate=16000), emit=events.append)
    assert sorted(loads) == ["m/one", "m/two"]
    for e in events:
        assert read_wav(tmp_path / f"{e['id']}.wav")[1] == 24000


def _run_cli(args, tmp_path, **kw):
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    return subprocess.run([sys.executable, str(WORKER_SRC), *args], capture_output=True, text=True,
                          cwd=tmp_path, env=env, timeout=60, **kw)


def _write_batch(tmp_path, lines):
    p = tmp_path / "batch.jsonl"
    p.write_text("\n".join(json.dumps(x) for x in lines) + "\n")
    return p


def test_cli_mock_batch_progress_lines_and_failure(tmp_path):
    texts = ["ek do teen", "yeh [[fail]] hai", "char paanch chhe saat"]
    batch = _write_batch(tmp_path, _lines(texts))
    out = tmp_path / "out"
    res = _run_cli(["--batch", str(batch), "--out-dir", str(out), "--backend", "mock"], tmp_path)
    assert res.returncode == 0, res.stderr
    events = [json.loads(x) for x in res.stdout.splitlines() if x.strip()]
    assert [e["id"] for e in events] == ["l0", "l1", "l2"]
    assert "error" in events[1] and "error" not in events[0] and "error" not in events[2]
    for i in (0, 2):
        samples, rate, ch, width = read_wav(out / f"l{i}.wav")
        assert (rate, ch, width) == (24000, 1, 2)
        assert events[i]["duration_s"] == __import__("pytest").approx(len(samples) / rate, abs=0.02)
    assert not (out / "l1.wav").exists()


def test_cli_mock_is_deterministic_and_speed_and_words_matter(tmp_path):
    lines = _lines(["ek do teen char"]) + _lines(["ek do teen char"], speed=1.25) + _lines(
        ["ek do teen char paanch chhe saat aath"]
    )
    for i, ln in enumerate(lines):
        ln["id"] = f"w{i}"
    batch = _write_batch(tmp_path, lines)
    blobs = []
    for run in ("a", "b"):
        out = tmp_path / run
        res = _run_cli(["--batch", str(batch), "--out-dir", str(out), "--backend", "mock"], tmp_path)
        assert res.returncode == 0, res.stderr
        blobs.append([(out / f"w{i}.wav").read_bytes() for i in range(3)])
    assert blobs[0] == blobs[1]
    d = [len(read_wav(b)[0]) for b in blobs[0]]
    assert d[1] < d[0] < d[2]
    # leading and trailing silence so trimming is observable
    samples, rate, _, _ = read_wav(blobs[0][0])
    head = samples[: int(0.2 * rate)]
    tail = samples[-int(0.2 * rate):]
    assert max(abs(x) for x in head) < 200 and max(abs(x) for x in tail) < 200
    assert max(abs(x) for x in samples) > 2000


def test_cli_selftest_mock_exits_zero(tmp_path):
    res = _run_cli(["--selftest", "--backend", "mock"], tmp_path)
    assert res.returncode == 0, res.stderr


def test_cli_unreadable_batch_exits_nonzero(tmp_path):
    assert _run_cli(["--selftest", "--backend", "mock"], tmp_path).returncode == 0  # worker exists
    res = _run_cli(["--batch", str(tmp_path / "missing.jsonl"), "--out-dir", str(tmp_path / "o"),
                    "--backend", "mock"], tmp_path)
    assert res.returncode != 0


def test_worker_imports_only_stdlib_numpy_and_mlx():
    tree = ast.parse(WORKER_SRC.read_text())
    mods: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            mods.add(node.module.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.level:
            mods.add("<relative>")
    allowed = set(sys.stdlib_module_names) | {"numpy", "mlx_audio", "mlx", "__future__"}
    assert mods <= allowed, mods - allowed
    assert "reelforge" not in mods
