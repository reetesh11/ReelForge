"""Environment checks shared by `reelforge doctor` and `GET /health`."""

from __future__ import annotations

import platform
import re
import shutil
import socket
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Literal

import psutil
from pydantic import BaseModel

from reelforge.adapters.drawthings import DrawThingsAdapter
from reelforge.adapters.ltx import LtxAdapter
from reelforge.adapters.mlx_audio import VOICE_MODELS, MlxAudioAdapter
from reelforge.adapters.ollama import OllamaAdapter
from reelforge.config import Settings
from reelforge.models_registry import load_models

GB = 1024**3
DISK_OK_GB = 30
DISK_BLOCKING_GB = 5
MEMORY_MIN_GB = 24
REQUIRED_FILTERS = ("scale", "xfade", "loudnorm", "amix")

Severity = Literal["blocking", "warning"]


class CheckResult(BaseModel):
    name: str
    status: Literal["pass", "fail"]
    severity: Literal["blocking", "warning"]
    detail: str
    fix: str | None = None


class DoctorReport(BaseModel):
    checks: list[CheckResult]

    @property
    def passed(self) -> int:
        return sum(1 for c in self.checks if c.status == "pass")

    @property
    def warnings(self) -> int:
        return sum(1 for c in self.checks if c.status == "fail" and c.severity == "warning")

    @property
    def blocking_failures(self) -> int:
        return sum(1 for c in self.checks if c.status == "fail" and c.severity == "blocking")

    @property
    def ok(self) -> bool:
        return self.blocking_failures == 0

    @property
    def overall(self) -> Literal["ok", "degraded", "fail"]:
        if self.blocking_failures:
            return "fail"
        return "degraded" if self.warnings else "ok"


def _result(
    name: str, ok: bool, severity: Severity, detail: str, fix: str | None = None
) -> CheckResult:
    return CheckResult(
        name=name,
        status="pass" if ok else "fail",
        severity=severity,
        detail=detail,
        fix=None
        if ok
        else (fix or "See the Technical Spec, section Startup, doctor and configuration."),
    )


def _run(argv: list[str], timeout: float = 10.0) -> str:
    proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, check=False)
    return proc.stdout + proc.stderr


def check_arm64(settings: Settings) -> CheckResult:
    native = platform.machine() == "arm64"
    translated = False
    if sys.platform == "darwin":
        translated = _run(["sysctl", "-n", "sysctl.proc_translated"]).strip() == "1"
        native = native or _run(["sysctl", "-n", "hw.optional.arm64"]).strip() == "1"
    ok = native and not translated
    return _result(
        "arm64",
        ok,
        "blocking",
        "Apple Silicon (arm64), native"
        if ok
        else f"Not a native arm64 process ({platform.machine()})",
        "Use an Apple Silicon Mac and a native arm64 Python (not Rosetta).",
    )


def check_binaries_native(settings: Settings) -> CheckResult:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        return _result(
            "binaries_native", False, "blocking", "ffmpeg not found on PATH", "brew install ffmpeg"
        )
    out = _run(["file", str(Path(ffmpeg).resolve())])
    ok = "arm64" in out
    return _result(
        "binaries_native",
        ok,
        "blocking",
        "ffmpeg is a native arm64 binary" if ok else f"ffmpeg is not arm64: {out.strip()[:120]}",
        "Install an arm64 ffmpeg with the native Homebrew in /opt/homebrew.",
    )


def check_ffmpeg_filters(settings: Settings) -> CheckResult:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        return _result(
            "ffmpeg_filters", False, "blocking", "ffmpeg not found on PATH", "brew install ffmpeg"
        )
    version_line = _run([ffmpeg, "-hide_banner", "-version"]).splitlines()[:1]
    match = re.search(r"version (\S+)", version_line[0]) if version_line else None
    version = match.group(1) if match else "unknown"
    filters = _run([ffmpeg, "-hide_banner", "-filters"])
    names = {parts[1] for ln in filters.splitlines() if len(parts := ln.split()) > 2}
    missing = [f for f in REQUIRED_FILTERS if f not in names]
    return _result(
        "ffmpeg_filters",
        not missing,
        "blocking",
        f"ffmpeg {version}"
        if not missing
        else f"ffmpeg {version} lacks filters: {', '.join(missing)}",
        "Install a full ffmpeg build: brew reinstall ffmpeg",
    )


def check_ltx(settings: Settings) -> CheckResult:
    rep = LtxAdapter(settings.ltx_path).check()
    return _result(
        "ltx",
        rep.ok,
        "blocking",
        rep.detail,
        "Install ltx-2-mlx and set [tools.ltx] project_path in config.toml "
        "(or REELFORGE_LTX_PATH).",
    )


def _voice_model_id(settings: Settings) -> str | None:
    try:
        registry = load_models(settings.models_path)
        key = VOICE_MODELS[settings.voice_model]
        return registry.get(key).id if key in registry.keys() else None
    except (OSError, ValueError, KeyError):
        return None


def check_mlx_audio(settings: Settings) -> CheckResult:
    fix = (
        "Install mlx-audio in an arm64 uv environment (uv python install "
        "cpython-3.12-macos-aarch64-none, then uv sync in the mlx-audio project) and set "
        "[tools.mlx_audio] project_path in config.toml (or REELFORGE_MLX_AUDIO_PATH)."
    )
    adapter = MlxAudioAdapter(settings.mlx_audio_path)
    rep = adapter.check()
    if not rep.ok:
        return _result("mlx_audio", False, "blocking", rep.detail, fix)
    test = adapter.selftest(model_id=_voice_model_id(settings))
    if not test.ok:
        return _result("mlx_audio", False, "blocking", test.detail, fix)
    return _result("mlx_audio", True, "blocking", "mlx-audio ready (selftest passed)")


def check_draw_things(settings: Settings) -> CheckResult:
    model_id: str | None = None
    try:
        registry = load_models(settings.models_path)
        if "image" in registry.keys():
            model_id = registry.get("image").id
    except (OSError, ValueError):
        model_id = None
    rep = DrawThingsAdapter(settings.drawthings_url, model_id=model_id).check()
    return _result(
        "draw_things",
        rep.ok,
        "blocking",
        rep.detail,
        rep.fix
        or "Open Draw Things and enable its HTTP API server (Settings > Advanced > API Server).",
    )


def check_ollama(settings: Settings) -> CheckResult:
    rep = OllamaAdapter(settings.ollama_url).check()
    return _result("ollama", rep.ok, "warning", rep.detail, "Start Ollama: ollama serve")


_serving_ports: set[int] = set()


def mark_serving(ports: set[int]) -> None:
    """Ports this process (or its UI dev server) legitimately holds once running."""
    _serving_ports.update(ports)


def _port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


def _next_free_port(start: int) -> int:
    for port in range(start + 1, min(start + 200, 65535)):
        if _port_free(port):
            return port
    return start + 1


def _port_holder(port: int) -> str:
    try:
        out = _run(["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN"], timeout=5)
    except (OSError, subprocess.SubprocessError):
        return "unknown process"
    rows = out.splitlines()[1:]
    if not rows:
        return "unknown process"
    cols = rows[0].split()
    return f"{cols[0]} (pid {cols[1]})" if len(cols) > 1 else "unknown process"


def check_ports(settings: Settings) -> CheckResult:
    for port in (settings.api_port, settings.ui_port):
        if port in _serving_ports or _port_free(port):
            continue
        holder = _port_holder(port)
        return _result(
            "ports",
            False,
            "blocking",
            f"Port {port} is used by another process.",
            f"Held by {holder}. Stop it, or choose another port, e.g. --api-port "
            f"{_next_free_port(port)}.",
        )
    return _result(
        "ports", True, "blocking", f"Ports {settings.api_port} and {settings.ui_port} are free"
    )


def check_disk(settings: Settings) -> CheckResult:
    probe = settings.data_root
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    free_gb = psutil.disk_usage(str(probe)).free / GB
    detail = f"{free_gb:.1f} GB free at {probe}"
    if free_gb >= DISK_OK_GB:
        return _result("disk", True, "warning", detail)
    severity: Severity = "blocking" if free_gb < DISK_BLOCKING_GB else "warning"
    return _result(
        "disk",
        False,
        severity,
        detail,
        f"Free up disk space; at least {DISK_OK_GB} GB is recommended for renders.",
    )


def check_memory(settings: Settings) -> CheckResult:
    vm = psutil.virtual_memory()
    total = vm.total / GB
    detail = f"{total:.0f} GB total, {vm.available / GB:.1f} GB available"
    return _result(
        "memory",
        total >= MEMORY_MIN_GB,
        "warning",
        detail,
        f"{MEMORY_MIN_GB} GB or more unified memory is recommended; "
        "close other apps before rendering.",
    )


def check_licenses(settings: Settings) -> CheckResult:
    try:
        missing = load_models(settings.models_path).missing_license()
    except (OSError, ValueError) as exc:
        return _result(
            "licenses", False, "warning", f"cannot read models.toml: {exc}", "Fix models.toml."
        )
    if not missing:
        return _result("licenses", True, "warning", "Every model has a license recorded")
    return _result(
        "licenses",
        False,
        "warning",
        f"Missing license for: {', '.join(missing)}",
        "Fill in license and license_url for these models in models.toml.",
    )


CHECKS: dict[str, Callable[[Settings], CheckResult]] = {
    "arm64": check_arm64,
    "binaries_native": check_binaries_native,
    "ffmpeg_filters": check_ffmpeg_filters,
    "ltx": check_ltx,
    "mlx_audio": check_mlx_audio,
    "draw_things": check_draw_things,
    "ollama": check_ollama,
    "ports": check_ports,
    "disk": check_disk,
    "memory": check_memory,
    "licenses": check_licenses,
}

_WARNING_CHECKS = {"ollama", "memory", "licenses", "disk"}


def run_doctor(settings: Settings) -> DoctorReport:
    results: list[CheckResult] = []
    for name, fn in CHECKS.items():
        try:
            results.append(fn(settings))
        except Exception as exc:  # noqa: BLE001
            results.append(
                CheckResult(
                    name=name,
                    status="fail",
                    severity="warning" if name in _WARNING_CHECKS else "blocking",
                    detail=f"check crashed: {exc}",
                    fix="Check the logs, then re-run `reelforge doctor`.",
                )
            )
    return DoctorReport(checks=results)
