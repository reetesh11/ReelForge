"""Mock backend: deterministic PNG / WAV / MP4 placeholders produced through real subprocesses."""

from __future__ import annotations

import asyncio
import contextlib
import math
import shutil
import struct
import sys
import wave
import zlib
from pathlib import Path
from typing import Any

from reelforge.adapters.base import (
    AdapterError,
    CancelToken,
    HealthReport,
    ProducedFile,
    ProgressCb,
    TaskSpec,
    TransientError,
)
from reelforge.adapters.runner import CommandResult, run_command
from reelforge.jobs.classify import OOM_REASON, classify_exit
from reelforge.models_registry import ModelRegistry


def _png(width: int, height: int, rgb: tuple[int, int, int]) -> bytes:
    def chunk(tag: bytes, data: bytes) -> bytes:
        body = tag + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    row = b"\x00" + bytes(rgb) * width
    raw = row * height
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw, 6))
        + chunk(b"IEND", b"")
    )


_AUDIO_KIND_HZ = {"music": 220.0, "sfx": 880.0, "ambience": 330.0}


def _colour(seed: int) -> tuple[int, int, int]:
    return ((seed * 67) % 200 + 40, (seed * 131) % 200 + 40, (seed * 197) % 200 + 40)


class MockAdapter:
    name = "mock"
    version = "mock-1"

    def __init__(
        self,
        registry: ModelRegistry,
        *,
        default_timeout_s: float = 600.0,
        sample_interval_s: float = 2.0,
    ) -> None:
        self.registry = registry
        self.default_timeout_s = default_timeout_s
        self.sample_interval_s = sample_interval_s
        self._attempts: dict[str, int] = {}

    async def health(self) -> HealthReport:
        return HealthReport(name=self.name, ok=True, version=self.version, detail="mock backend")

    async def capabilities(self) -> set[str]:
        return {"image", "audio", "video"}

    async def _command(
        self,
        argv: list[str],
        timeout_s: float,
        cancel: CancelToken,
        job_id: str | None,
    ) -> CommandResult:
        res = await run_command(
            argv,
            timeout_s=timeout_s,
            cancel=cancel,
            sample_interval_s=self.sample_interval_s,
            job_id=job_id,
        )
        if res.cancelled:
            raise AdapterError("cancelled")
        if res.timed_out:
            raise AdapterError(res.error or "timed out")
        if classify_exit(res.exit_code) is not None:
            raise TransientError(OOM_REASON)
        if res.exit_code != 0:
            raise AdapterError(f"exit code {res.exit_code}")
        return res

    async def run(
        self,
        task: TaskSpec,
        out_dir: Path,
        progress: ProgressCb,
        cancel: CancelToken,
        *,
        ctx_job_id: str | None = None,
    ) -> list[ProducedFile]:
        hooks: dict[str, Any] = dict(task.params.get("mock") or {})
        out_dir.mkdir(parents=True, exist_ok=True)
        key = ctx_job_id or ""
        self._attempts[key] = self._attempts.get(key, 0) + 1
        if self._attempts[key] <= int(hooks.get("transient_failures", 0)):
            raise TransientError(f"transient failure on attempt {self._attempts[key]}")
        if hooks.get("fail"):
            raise AdapterError(str(hooks["fail"]))

        sleep_s = float(hooks.get("sleep_s", 0.0))
        steps = max(1, int(hooks.get("steps", 5)))
        timeout_s = float(hooks.get("timeout_s", self.default_timeout_s))
        progress(1, "starting")
        argv = [
            sys.executable,
            "-m",
            "reelforge.adapters.mock_child",
            "--sleep",
            str(sleep_s),
            "--exit-code",
            str(int(hooks.get("exit_code", 0))),
        ]
        if hooks.get("kill"):
            argv.append("--kill")

        async def ticker() -> None:
            for i in range(1, steps + 1):
                await asyncio.sleep(sleep_s / steps)
                progress(min(90, int(90 * i / steps)), f"step {i}/{steps}")

        tick = asyncio.create_task(ticker()) if sleep_s > 0 else None
        try:
            await self._command(argv, timeout_s, cancel, ctx_job_id)
        finally:
            if tick is not None:
                tick.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await tick
        progress(92, "writing output")

        width = int(hooks.get("width", 320))
        height = int(hooks.get("height", 576))
        duration = float(hooks.get("duration_s", task.params.get("duration_s", 1.0)))
        if task.kind == "image":
            path = out_dir / "out.png"
            path.write_bytes(_png(width, height, _colour(task.seed)))
            produced = ProducedFile(path=path, ext="png", width=width, height=height)
        elif task.kind == "audio":
            path = out_dir / "out.wav"
            kind_hz = _AUDIO_KIND_HZ.get(str(task.params.get("audio_kind", "")), 440.0)
            self._write_wav(path, duration, float(hooks.get("freq_hz", kind_hz)))
            produced = ProducedFile(path=path, ext="wav", duration_s=duration)
        elif "frames" in task.params:
            path = out_dir / "out.mp4"
            frames = int(task.params["frames"])
            fps = int(task.params.get("fps", 24))
            width = int(task.params.get("width", width))
            height = int(task.params.get("height", height))
            audio = (
                task.input_paths[1]
                if task.params.get("mode") == "a2v" and len(task.input_paths) > 1
                else None
            )
            await self._write_shot_mp4(
                path, width, height, frames, fps, audio, timeout_s, cancel, ctx_job_id
            )
            produced = ProducedFile(
                path=path, ext="mp4", width=width, height=height, duration_s=frames / fps
            )
        else:
            path = out_dir / "out.mp4"
            await self._write_mp4(path, width, height, duration, timeout_s, cancel, ctx_job_id)
            produced = ProducedFile(
                path=path, ext="mp4", width=width, height=height, duration_s=duration
            )
        progress(99, "done")
        return [produced]

    @staticmethod
    def _write_wav(path: Path, duration: float, freq: float) -> None:
        rate = 24000
        frames = bytearray()
        for n in range(int(rate * duration)):
            sample = int(12000 * math.sin(2 * math.pi * freq * n / rate))
            frames += struct.pack("<h", sample)
        with wave.open(str(path), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(rate)
            wav.writeframes(bytes(frames))

    async def _write_shot_mp4(
        self,
        path: Path,
        width: int,
        height: int,
        frames: int,
        fps: int,
        audio: Path | None,
        timeout_s: float,
        cancel: CancelToken,
        job_id: str | None,
    ) -> None:
        """Exactly `frames` frames at `fps` and `width`x`height`; audio only when given."""
        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg is None:
            raise AdapterError("ffmpeg not found")
        argv = [
            ffmpeg,
            "-y",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"testsrc=size={width - width % 2}x{height - height % 2}:rate={fps}",
        ]
        if audio is not None:
            argv += ["-i", str(audio)]
        argv += ["-frames:v", str(frames), "-pix_fmt", "yuv420p", "-c:v", "libx264"]
        argv += ["-preset", "ultrafast"]
        argv += ["-c:a", "aac", "-map", "0:v", "-map", "1:a"] if audio is not None else ["-an"]
        argv.append(str(path))
        await self._command(argv, timeout_s, cancel, job_id)

    async def _write_mp4(
        self,
        path: Path,
        width: int,
        height: int,
        duration: float,
        timeout_s: float,
        cancel: CancelToken,
        job_id: str | None,
    ) -> None:
        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg is None:
            raise AdapterError("ffmpeg not found")
        argv = [
            ffmpeg,
            "-y",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"testsrc=size={width - width % 2}x{height - height % 2}:rate=24:duration={duration}",
            "-pix_fmt",
            "yuv420p",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            str(path),
        ]
        await self._command(argv, timeout_s, cancel, job_id)
