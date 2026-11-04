"""Frame-exact joins with real ffmpeg on synthetic clips."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from reelforge.assembly.edl import Edl, EdlShot
from reelforge.assembly.ffmpeg import filter_script_args
from reelforge.assembly.filtergraph import build_join_graph, build_normalise_graph

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


def _run(*args: str) -> None:
    subprocess.run(["ffmpeg", "-y", "-v", "error", *args], check=True, timeout=120)  # noqa: S603, S607


def _frames(path: Path) -> int:
    out = subprocess.run(  # noqa: S603
        [
            "ffprobe",
            "-v",
            "error",
            "-count_frames",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=nb_read_frames",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return int(json.loads(out.stdout)["streams"][0]["nb_read_frames"])


@pytest.mark.parametrize("fade", [0.0, 0.5])
def test_join_has_exactly_the_edl_frame_count(tmp_path: Path, fade: float) -> None:
    lengths = [1.0, 1.5, 1.25]
    shots = [
        EdlShot(
            scene_id=f"s{i}",
            artifact="a",
            source_duration_s=n,
            in_s=0.0,
            out_s=n,
            transition_in_s=fade if i else 0.0,
        )
        for i, n in enumerate(lengths)
    ]
    edl = Edl(project_id="p", video=shots, dialogue=[], captions=[])
    prepared: list[Path] = []
    for i, shot in enumerate(shots):
        src = tmp_path / f"src{i}.mp4"
        _run("-f", "lavfi", "-i", f"testsrc=size=160x284:rate=30:duration={shot.out_s}", str(src))
        script = tmp_path / f"n{i}.fg"
        script.write_text(build_normalise_graph(shot, 108, 192).to_script())
        dst = tmp_path / f"p{i}.mp4"
        _run("-i", str(src), *filter_script_args(script), "-map", "[v]", "-an", str(dst))
        assert _frames(dst) == shot.frames
        prepared.append(dst)
    script = tmp_path / "join.fg"
    script.write_text(build_join_graph(edl).to_script())
    out = tmp_path / "joined.mp4"
    args: list[str] = []
    for p in prepared:
        args += ["-i", str(p)]
    _run(*args, *filter_script_args(script), "-map", "[v]", "-an", str(out))
    assert _frames(out) == edl.total_frames
