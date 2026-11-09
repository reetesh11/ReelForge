"""Measure candidate sound-generation models on the reference cues (reference Mac only).

    python tools/audio_spike.py --out DIR [--backend real|mock] [--models KEY,...] [--table PATH]

For every candidate in the `[candidates.*]` tables of `models.toml` it renders the nine
reference cues (three music descriptions, five screenplay effects, the wedding ambience) at
three durations each and writes a Markdown table with the requested and got length, the
generation time, peak memory and integrated loudness. `--backend mock` writes tones and needs
no model. This file imports nothing from `reelforge`; it reads `models.toml` with `tomllib`.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import time
import tomllib
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
MODELS = HERE.parent / "src" / "reelforge" / "models.toml"
COLUMNS = (
    "model",
    "cue",
    "duration requested (s)",
    "duration got (s)",
    "accuracy (s)",
    "generation time (s)",
    "peak memory (MB)",
    "loudness (LUFS)",
    "note",
)
FREQ = {"music": 220.0, "sfx": 880.0, "ambience": 330.0}
DURATIONS = {"music": (10.0, 20.0, 30.0), "sfx": (1.0, 2.0, 4.0), "ambience": (10.0, 20.0, 30.0)}
CUES: list[tuple[str, str, str]] = [
    ("music_festive", "music", "festive shehnai and dholak, wedding celebration, upbeat"),
    ("music_soft", "music", "soft sitar and tabla, calm and warm, slow tempo"),
    ("music_tense", "music", "tense low strings with a slow drum pulse, building"),
    ("sfx_gong", "sfx", "single gong slam with a long ringing tail"),
    ("sfx_drumroll", "sfx", "short snare drum roll building to a hit"),
    ("sfx_ceramic", "sfx", "ceramic plate crash and breaking on a tile floor"),
    ("sfx_crinkle", "sfx", "plastic packaging crinkle, being opened"),
    ("sfx_crunch", "sfx", "a loud crunch of someone biting a crisp snack"),
    ("amb_wedding", "ambience", "wedding hall crowd murmur with distant music, steady"),
]
_LUFS = re.compile(r"I:\s+(-?\d+(?:\.\d+)?|-inf)\s+LUFS")
_RSS = re.compile(r"(\d+)\s+maximum resident set size")


def _run(argv: list[str], timeout: float = 3600.0) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, capture_output=True, text=True, timeout=timeout, check=False)  # noqa: S603


def duration_of(path: Path) -> float:
    res = _run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)]
    )
    try:
        return float(res.stdout.strip())
    except ValueError:
        return 0.0


def loudness(path: Path) -> str:
    res = _run(["ffmpeg", "-nostdin", "-i", str(path), "-af", "ebur128", "-f", "null", "-"])
    found = _LUFS.findall(res.stderr)
    return found[-1] if found else "n/a"


def mock_tone(path: Path, kind: str, seconds: float) -> None:
    res = _run(
        [
            "ffmpeg", "-nostdin", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
            f"sine=frequency={FREQ[kind]}:sample_rate=48000:duration={seconds}",
            "-ac", "2", "-c:a", "pcm_s16le", str(path),
        ]
    )  # fmt: skip
    if res.returncode != 0:
        raise RuntimeError(res.stderr.strip() or "ffmpeg failed")


def candidates(models: Path, wanted: list[str] | None) -> dict[str, dict[str, Any]]:
    with models.open("rb") as fh:
        table: dict[str, dict[str, Any]] = tomllib.load(fh).get("candidates", {})
    if wanted:
        missing = [k for k in wanted if k not in table]
        if missing:
            raise SystemExit(f"unknown candidate: {', '.join(missing)}")
        return {k: table[k] for k in wanted}
    return table


def real_run(
    cand: dict[str, Any], prompt: str, seconds: float, seed: int, out: Path
) -> tuple[float, str, str]:
    """Run the candidate command under `/usr/bin/time -l`; returns (seconds, peak MB, note)."""
    argv = [
        str(a).format(prompt=prompt, seconds=seconds, seed=seed, out=str(out))
        for a in cand.get("command", [])
    ]
    if not argv:
        return 0.0, "n/a", "no command in models.toml"
    started = time.monotonic()
    res = _run(["/usr/bin/time", "-l", *argv])
    took = time.monotonic() - started
    rss = _RSS.search(res.stderr)
    peak = f"{int(rss.group(1)) / 1_048_576:.0f}" if rss else "n/a"
    note = "" if res.returncode == 0 else f"exit {res.returncode}"
    return took, peak, note


def row(cells: list[str]) -> str:
    return "| " + " | ".join(cells) + " |"


def spike(out: Path, backend: str, models: Path, wanted: list[str] | None) -> str:
    lines = [row(list(COLUMNS)), row(["---"] * len(COLUMNS))]
    for key, cand in candidates(models, wanted).items():
        folder = out / key
        folder.mkdir(parents=True, exist_ok=True)
        for name, kind, prompt in CUES:
            for seconds in DURATIONS[kind]:
                path = folder / f"{name}_{seconds:g}s.wav"
                note, peak, took = "", "-", 0.0
                started = time.monotonic()
                try:
                    if backend == "mock":
                        mock_tone(path, kind, seconds)
                        took = time.monotonic() - started
                    else:
                        took, peak, note = real_run(cand, prompt, seconds, 1, path)
                except (RuntimeError, OSError, subprocess.SubprocessError) as exc:
                    note = str(exc)[:80]
                got = duration_of(path) if path.is_file() else 0.0
                lines.append(
                    row(
                        [
                            key,
                            name,
                            f"{seconds:g}",
                            f"{got:.3f}",
                            f"{got - seconds:+.3f}",
                            f"{took:.2f}",
                            peak,
                            loudness(path) if path.is_file() else "n/a",
                            note,
                        ]
                    )  # fmt: skip
                )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="audio_spike")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--backend", choices=("real", "mock"), default="real")
    parser.add_argument("--models", default="")
    parser.add_argument("--table", type=Path, default=None)
    args = parser.parse_args(argv)
    wanted = [k.strip() for k in args.models.split(",") if k.strip()] or None
    args.out.mkdir(parents=True, exist_ok=True)
    table = spike(args.out, args.backend, MODELS, wanted)
    path = args.table or args.out / "audio_spike.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(table, encoding="utf-8")
    print(path)  # noqa: T201
    return 0


if __name__ == "__main__":
    here = HERE.resolve()
    sys.path[:] = [p for p in sys.path if Path(p or ".").resolve() != here]
    raise SystemExit(main())
