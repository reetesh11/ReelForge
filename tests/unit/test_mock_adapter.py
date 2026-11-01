import asyncio
import json
import shutil
import subprocess
import wave
from pathlib import Path

import pytest

from reelforge.adapters.base import AdapterError, CancelToken, TaskSpec, TransientError
from reelforge.adapters.mock import MockAdapter
from reelforge.config import PACKAGED_MODELS
from reelforge.models_registry import load_models


def _run(kind, tmp_path: Path, **params):
    reg = load_models(PACKAGED_MODELS)
    key = {"image": "image", "audio": "tts", "video": "video"}[kind]
    adapter = MockAdapter(reg, sample_interval_s=0.05)
    task = TaskSpec(kind=kind, prompt="p", seed=3, params=params, model=reg.get(key))
    ticks: list[int] = []
    out = asyncio.run(
        adapter.run(task, tmp_path / "out", lambda p, m: ticks.append(p), CancelToken())
    )
    return out[0], ticks


def test_image_is_png(tmp_path):
    f, ticks = _run("image", tmp_path)
    assert f.path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n" and (f.width, f.height) == (320, 576)
    assert ticks == sorted(ticks) and ticks[-1] <= 100


def test_audio_is_wav(tmp_path):
    f, _ = _run("audio", tmp_path, mock={"duration_s": 0.5, "freq_hz": 220})
    with wave.open(str(f.path)) as w:
        assert w.getframerate() == 24000 and w.getnchannels() == 1 and w.getnframes() == 12000


@pytest.mark.skipif(shutil.which("ffprobe") is None, reason="ffmpeg/ffprobe not installed")
def test_video_is_mp4(tmp_path):
    f, _ = _run("video", tmp_path)
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_streams", "-of", "json", str(f.path)],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert json.loads(out)["streams"][0]["codec_type"] == "video"


def test_failure_hooks(tmp_path):
    with pytest.raises(TransientError):
        _run("image", tmp_path, mock={"kill": True})
    with pytest.raises(AdapterError, match="exit code 3"):
        _run("image", tmp_path, mock={"exit_code": 3})
    with pytest.raises(AdapterError, match="timed out after 1s"):
        _run("image", tmp_path, mock={"sleep_s": 30, "timeout_s": 1})
    with pytest.raises(AdapterError, match="nope"):
        _run("image", tmp_path, mock={"fail": "nope"})
