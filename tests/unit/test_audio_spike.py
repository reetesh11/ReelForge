import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COLUMNS = [
    "model", "cue", "duration requested (s)", "duration got (s)", "accuracy (s)",
    "generation time (s)", "peak memory (MB)", "loudness (LUFS)", "note",
]  # fmt: skip


def test_mock_run_for_one_model_writes_every_column(tmp_path):
    table = tmp_path / "t.md"
    res = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "audio_spike.py"), "--out", str(tmp_path / "o"),
         "--backend", "mock", "--models", "acestep", "--table", str(table)],
        capture_output=True, text=True, timeout=300, check=False,
    )  # fmt: skip
    assert res.returncode == 0, res.stderr
    assert res.stdout.strip() == str(table)
    lines = [ln for ln in table.read_text().splitlines() if ln.startswith("|")]
    header = [c.strip() for c in lines[0].strip("|").split("|")]
    assert header == COLUMNS
    assert len(lines) == 2 + 27


def test_unknown_model_is_refused(tmp_path):
    res = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "audio_spike.py"), "--out", str(tmp_path),
         "--backend", "mock", "--models", "nope"],
        capture_output=True, text=True, timeout=60, check=False,
    )  # fmt: skip
    assert res.returncode != 0
