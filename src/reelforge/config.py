"""Settings resolution: CLI > REELFORGE_* env > config.toml > defaults."""

from __future__ import annotations

import os
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

LOOPBACK_HOST = "127.0.0.1"
PACKAGED_MODELS = Path(__file__).resolve().parent / "models.toml"
PACKAGED_EMOTIONS = Path(__file__).resolve().parent / "voice" / "emotions.toml"


class ConfigError(ValueError):
    """Invalid configuration. `key` names the offending setting when known."""

    def __init__(self, message: str, key: str | None = None) -> None:
        self.key = key
        self.message = message
        super().__init__(f"{key}: {message}" if key else message)


def _default_data_root() -> Path:
    return Path.home() / "ReelForge"


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    host: str = LOOPBACK_HOST
    api_port: int = Field(default=7400, ge=1, le=65535)
    ui_port: int = Field(default=7401, ge=1, le=65535)
    data_root: Path = Field(default_factory=_default_data_root)
    backend: Literal["mock", "real"] = "mock"
    llm_backend: Literal["mock", "ollama"] = "mock"
    models_path: Path = PACKAGED_MODELS
    emotion_mapping_path: Path = PACKAGED_EMOTIONS
    ollama_url: str = "http://127.0.0.1:11434"
    drawthings_url: str = "http://127.0.0.1:7860"
    ltx_path: Path | None = None
    mlx_audio_path: Path | None = None
    command_timeout_s: float = 600.0
    preflight_wait_s: float = 120.0
    sample_interval_s: float = 2.0
    health_poll_s: float = 15.0
    worker_poll_s: float = 0.2
    max_light_jobs: int = Field(default=4, ge=1)
    image_fallback: Literal["none", "mflux"] = "none"
    mflux_command: Path | None = None
    max_upload_mb: int = Field(default=10, ge=1)
    image_mem_gb: float = Field(default=6.0, gt=0, allow_inf_nan=False)
    voice_model: Literal["omnivoice", "kokoro"] = "omnivoice"
    voice_mem_gb: float = Field(default=4.0, gt=0, allow_inf_nan=False)
    shot_mem_gb: float = Field(default=16.0, gt=0, allow_inf_nan=False)
    audio_mem_gb: float = Field(default=8.0, gt=0, allow_inf_nan=False)
    shot_quality: Literal["draft", "final"] = "draft"
    shot_draft_size: str = "320x576"
    shot_final_size: str = "448x768"
    shot_timeout_s: float = Field(default=1800.0, gt=0, allow_inf_nan=False)
    max_clip_mb: int = Field(default=100, ge=1)
    preview_debounce_s: float = Field(default=1.0, ge=0, allow_inf_nan=False)
    devanagari_font: Path = Path("/System/Library/Fonts/Kohinoor.ttc")
    devanagari_font_family: str = "Kohinoor Devanagari"

    @field_validator("host")
    @classmethod
    def _loopback_only(cls, value: str) -> str:
        if value != LOOPBACK_HOST:
            raise ValueError(f"must be exactly {LOOPBACK_HOST} (loopback only), got {value!r}")
        return value

    @field_validator("shot_draft_size", "shot_final_size")
    @classmethod
    def _shot_size(cls, value: str) -> str:
        parts = value.lower().split("x")
        if len(parts) != 2 or not all(p.isdigit() for p in parts):
            raise ValueError(f"must look like WxH, got {value!r}")
        if any(int(p) <= 0 or int(p) % 32 for p in parts):
            raise ValueError(f"both sides must be a multiple of 32, got {value!r}")
        return value.lower()

    @field_validator(
        "data_root",
        "models_path",
        "emotion_mapping_path",
        "ltx_path",
        "mlx_audio_path",
        "mflux_command",
        "devanagari_font",
    )
    @classmethod
    def _expand(cls, value: Path | None) -> Path | None:
        return value.expanduser() if value is not None else None

    @property
    def db_path(self) -> Path:
        return self.data_root / "reelforge.db"

    @property
    def cache_tmp(self) -> Path:
        return self.data_root / "cache" / "tmp"

    @property
    def api_url(self) -> str:
        return f"http://{self.host}:{self.api_port}"


_TOML_MAP: dict[str, dict[str, str]] = {
    "server": {"host": "host", "api_port": "api_port", "ui_port": "ui_port"},
    "paths": {
        "data_root": "data_root",
        "models_path": "models_path",
        "emotion_mapping_path": "emotion_mapping_path",
    },
    "runtime": {
        "command_timeout_s": "command_timeout_s",
        "preflight_wait_s": "preflight_wait_s",
        "sample_interval_s": "sample_interval_s",
        "health_poll_s": "health_poll_s",
        "worker_poll_s": "worker_poll_s",
        "max_light_jobs": "max_light_jobs",
        "llm_backend": "llm_backend",
        "image_fallback": "image_fallback",
        "max_upload_mb": "max_upload_mb",
        "voice_model": "voice_model",
        "shot_quality": "shot_quality",
        "shot_draft_size": "shot_draft_size",
        "shot_final_size": "shot_final_size",
        "shot_timeout_s": "shot_timeout_s",
        "max_clip_mb": "max_clip_mb",
        "preview_debounce_s": "preview_debounce_s",
        "devanagari_font": "devanagari_font",
        "devanagari_font_family": "devanagari_font_family",
    },
    "limits": {
        "image_mem_gb": "image_mem_gb",
        "voice_mem_gb": "voice_mem_gb",
        "shot_mem_gb": "shot_mem_gb",
        "audio_mem_gb": "audio_mem_gb",
    },
}
_TOML_NESTED: dict[tuple[str, str], dict[str, str]] = {
    ("services", "ollama"): {"url": "ollama_url"},
    ("services", "drawthings"): {"url": "drawthings_url"},
    ("tools", "ltx"): {"project_path": "ltx_path"},
    ("tools", "mlx_audio"): {"project_path": "mlx_audio_path"},
    ("tools", "mflux"): {"command": "mflux_command"},
}


def _read_toml(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"cannot read config.toml at {path}: {exc}") from exc
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"malformed config.toml at {path}: {exc}") from exc
    out: dict[str, Any] = {}
    for section, body in data.items():
        if section in _TOML_MAP:
            if not isinstance(body, dict):
                raise ConfigError(f"[{section}] must be a table in {path}", key=section)
            for key, value in body.items():  # type: ignore[reportUnknownVariableType]
                field = _TOML_MAP[section].get(str(key))  # type: ignore[reportUnknownArgumentType]
                if field is None:
                    raise ConfigError(f"unknown key in config.toml [{section}]", key=str(key))  # type: ignore[reportUnknownArgumentType]
                out[field] = value
        elif section in {"services", "tools"}:
            if not isinstance(body, dict):
                raise ConfigError(f"[{section}] must be a table in {path}", key=section)
            for sub, subbody in body.items():  # type: ignore[reportUnknownVariableType]
                mapping = _TOML_NESTED.get((section, str(sub)))  # type: ignore[reportUnknownArgumentType]
                if mapping is None or not isinstance(subbody, dict):
                    raise ConfigError(
                        f"unknown table in config.toml [{section}.{sub}]",
                        key=f"{section}.{sub}",
                    )
                for key, value in subbody.items():  # type: ignore[reportUnknownVariableType]
                    field = mapping.get(str(key))  # type: ignore[reportUnknownArgumentType]
                    if field is None:
                        raise ConfigError(
                            f"unknown key in config.toml [{section}.{sub}]",
                            key=str(key),  # type: ignore[reportUnknownArgumentType]
                        )
                    out[field] = value
        else:
            raise ConfigError("unknown section in config.toml", key=section)
    return out


def load_settings(
    *,
    cli: Mapping[str, object] | None = None,
    env: Mapping[str, str] | None = None,
    config_path: Path | None = None,
) -> Settings:
    env_map = os.environ if env is None else env
    fields = Settings.model_fields.keys()
    from_env: dict[str, Any] = {
        name: env_map[f"REELFORGE_{name.upper()}"]
        for name in fields
        if f"REELFORGE_{name.upper()}" in env_map
    }
    from_cli: dict[str, Any] = {k: v for k, v in (cli or {}).items() if v is not None}

    toml_values: dict[str, Any] = {}
    if config_path is not None:
        if not config_path.is_file():
            raise ConfigError(f"config.toml not found at {config_path}")
        toml_values = _read_toml(config_path)
    else:
        root = from_cli.get("data_root", from_env.get("data_root"))
        base = Path(str(root)).expanduser() if root is not None else _default_data_root()
        candidate = base / "config.toml"
        if candidate.is_file():
            toml_values = _read_toml(candidate)

    merged = {**toml_values, **from_env, **from_cli}
    try:
        return Settings(**merged)
    except ValidationError as exc:
        err = exc.errors()[0]
        loc = ".".join(str(p) for p in err["loc"])
        msg = str(err["msg"]).removeprefix("Value error, ")
        raise ConfigError(msg, key=loc or None) from exc
