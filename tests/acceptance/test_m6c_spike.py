"""m6c R15, AC-13 (tool only): `tools/audio_spike.py` on the mock backend. The table from the
reference Mac and the owner's verdicts in `docs/audio-levers.md` are manual."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from m4_helpers import wav_seconds

ROOT = Path(__file__).resolve().parents[2]
COLUMNS = [
    "model", "cue", "duration requested (s)", "duration got (s)", "accuracy (s)",
    "generation time (s)", "peak memory (MB)", "loudness (LUFS)", "note",
]


def _run(tmp_path, *extra):
    tool = ROOT / "tools" / "audio_spike.py"
    assert tool.exists(), "tools/audio_spike.py is missing"
    out, table = tmp_path / "out", tmp_path / "table.md"
    res = subprocess.run(
        [sys.executable, str(tool), "--out", str(out), "--backend", "mock", "--table", str(table), *extra],
        capture_output=True, text=True, timeout=300, cwd=ROOT,
    )
    return res, out, table


def _rows(table: Path):
    lines = [ln for ln in table.read_text().splitlines() if ln.strip().startswith("|")]
    cells = [[c.strip() for c in ln.strip().strip("|").split("|")] for ln in lines]
    return cells[0], [r for r in cells[2:]]


def test_the_spike_tool_writes_the_table_and_the_files_on_the_mock_backend(tmp_path):
    res, out, table = _run(tmp_path)
    assert res.returncode == 0, res.stderr[-800:]
    assert str(table) in res.stdout
    header, rows = _rows(table)
    assert header == COLUMNS
    # 3 music descriptions + 5 effects + 1 ambience, at 3 durations each, per model
    assert len(rows) >= 27 and len(rows) % 27 == 0
    assert all(len(r) == 9 for r in rows)
    for r in rows:
        want, got, acc = float(r[2]), float(r[3]), float(r[4])
        assert got == pytest.approx(want, abs=0.05) and abs(acc) <= 0.05 + 1e-9
    assert len({r[2] for r in rows}) >= 3
    wavs = sorted(out.rglob("*.wav"))
    assert len(wavs) >= 27
    assert all(wav_seconds(p) > 0.5 for p in wavs[:5])
    assert len({r[1] for r in rows}) == 9

