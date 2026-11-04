from __future__ import annotations

import asyncio
import json
import subprocess
import wave

from reelforge.adapters.base import CancelToken, TaskSpec
from reelforge.adapters.mock import MockAdapter
from reelforge.models_registry import ModelEntry, ModelRegistry


def _wav(path):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(b"\0\0" * 8000)


def _run(tmp_path, mode, inputs):
    task = TaskSpec(
        kind="video",
        prompt="x",
        seed=1,
        params={"mode": mode, "frames": 17, "fps": 24, "width": 320, "height": 576},
        model=ModelEntry(key="video", id="m", revision="r"),
        input_paths=inputs,
    )
    adapter = MockAdapter(ModelRegistry([]))
    out = asyncio.run(adapter.run(task, tmp_path / "out", lambda p, m: None, CancelToken()))
    res = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "stream=codec_type,width,height,nb_frames",
            "-of",
            "json",
            str(out[0].path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return out[0], json.loads(res.stdout)["streams"]


def test_frames_size_and_audio(tmp_path):
    wav = tmp_path / "a.wav"
    _wav(wav)
    produced, streams = _run(tmp_path / "a2v", "a2v", [tmp_path / "k.png", wav])
    video = next(s for s in streams if s["codec_type"] == "video")
    assert (video["width"], video["height"], int(video["nb_frames"])) == (320, 576, 17)
    assert any(s["codec_type"] == "audio" for s in streams)
    assert produced.duration_s == 17 / 24


def test_generate_is_silent(tmp_path):
    _, streams = _run(tmp_path, "generate", [tmp_path / "k.png"])
    assert [s["codec_type"] for s in streams] == ["video"]
