from __future__ import annotations

import os
import stat

from reelforge.adapters.ltx import REQUIRED_FLAGS, LtxAdapter, parse_flags


def _exe(project, flags_for):
    bindir = project / ".venv" / "bin"
    bindir.mkdir(parents=True)
    exe = bindir / "ltx-2-mlx"
    lines = ["#!/bin/sh", 'case "$1" in']
    for sub, flags in flags_for.items():
        lines.append(f"  {sub}) echo '{' '.join(flags)}' ;;")
    lines.append("esac")
    exe.write_text("\n".join(lines) + "\n")
    exe.chmod(exe.stat().st_mode | stat.S_IXUSR)
    return exe


def test_parse_flags_ignores_short_options_and_words():
    assert parse_flags("-p, --prompt TEXT\n  not-a-flag --a-1") == {"--prompt", "--a-1"}


def test_check_cache_follows_the_executable_file(tmp_path):
    full = {sub: list(f) for sub, f in REQUIRED_FLAGS.items()}
    exe = _exe(tmp_path, full)
    assert LtxAdapter(tmp_path).check().ok
    broken = {sub: list(f) for sub, f in REQUIRED_FLAGS.items()}
    broken["extend"] = broken["extend"][:-1]
    lines = exe.read_text().replace("--image", "")
    exe.write_text(lines + "# changed\n")
    os.utime(exe, ns=(1, 2))
    rep = LtxAdapter(tmp_path).check()
    assert not rep.ok and "missing required options" in rep.detail
