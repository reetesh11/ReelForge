"""Command line entry point: `reelforge doctor` and `reelforge up`."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any

import typer

from reelforge import __version__
from reelforge.config import ConfigError, Settings, load_settings
from reelforge.doctor import run_doctor
from reelforge.startup import format_report, run_up

app = typer.Typer(name="reelforge", help="ReelForge command line.", no_args_is_help=True)

Host = Annotated[str | None, typer.Option("--host", help="Bind host (loopback only).")]
ImageMemGb = Annotated[
    float | None,
    typer.Option("--image-mem-gb", help="Memory (GB) an image job needs free before it starts."),
]
VoiceMemGb = Annotated[
    float | None,
    typer.Option("--voice-mem-gb", help="Memory (GB) a voice job needs free before it starts."),
]
ShotMemGb = Annotated[
    float | None,
    typer.Option("--shot-mem-gb", help="Memory (GB) a shot job needs free before it starts."),
]
VoiceModel = Annotated[
    str | None,
    typer.Option("--voice-model", help="Voice model (omnivoice or kokoro)."),
]
ApiPort = Annotated[int | None, typer.Option("--api-port", help="API port.")]
UiPort = Annotated[int | None, typer.Option("--ui-port", help="UI dev server port.")]
DataRoot = Annotated[Path | None, typer.Option("--data-root", help="Data root folder.")]
Backend = Annotated[str | None, typer.Option("--backend", help="Backend (mock or real).")]
ModelsPath = Annotated[Path | None, typer.Option("--models-path", help="Path to models.toml.")]
OllamaUrl = Annotated[str | None, typer.Option("--ollama-url", help="Ollama URL.")]
DrawThingsUrl = Annotated[str | None, typer.Option("--drawthings-url", help="Draw Things URL.")]
ConfigFile = Annotated[Path | None, typer.Option("--config", help="Path to config.toml.")]


def _version(value: bool) -> None:
    if value:
        typer.echo(__version__)
        raise typer.Exit()


def _settings(**cli: Any) -> Settings:
    config = cli.pop("config")
    try:
        return load_settings(cli=cli, config_path=config)
    except ConfigError as exc:
        typer.echo(f"config error: {exc}", err=True)
        raise typer.Exit(2) from None


@app.callback()
def main(
    version: bool = typer.Option(
        False, "--version", callback=_version, is_eager=True, help="Show version and exit."
    ),
) -> None:
    """ReelForge: local-first reel production."""


@app.command()
def doctor(
    host: Host = None,
    api_port: ApiPort = None,
    ui_port: UiPort = None,
    data_root: DataRoot = None,
    backend: Backend = None,
    models_path: ModelsPath = None,
    ollama_url: OllamaUrl = None,
    drawthings_url: DrawThingsUrl = None,
    image_mem_gb: ImageMemGb = None,
    voice_mem_gb: VoiceMemGb = None,
    shot_mem_gb: ShotMemGb = None,
    voice_model: VoiceModel = None,
    config: ConfigFile = None,
) -> None:
    """Check that this machine can run ReelForge."""
    settings = _settings(
        host=host,
        api_port=api_port,
        ui_port=ui_port,
        data_root=data_root,
        backend=backend,
        models_path=models_path,
        ollama_url=ollama_url,
        drawthings_url=drawthings_url,
        image_mem_gb=image_mem_gb,
        voice_mem_gb=voice_mem_gb,
        shot_mem_gb=shot_mem_gb,
        voice_model=voice_model,
        config=config,
    )
    report = run_doctor(settings)
    for line in format_report(report):
        typer.echo(line)
    raise typer.Exit(0 if report.ok else 1)


@app.command()
def up(
    allow_degraded: Annotated[
        bool, typer.Option("--allow-degraded", help="Start even if blocking checks fail.")
    ] = False,
    host: Host = None,
    api_port: ApiPort = None,
    ui_port: UiPort = None,
    data_root: DataRoot = None,
    backend: Backend = None,
    models_path: ModelsPath = None,
    ollama_url: OllamaUrl = None,
    drawthings_url: DrawThingsUrl = None,
    image_mem_gb: ImageMemGb = None,
    voice_mem_gb: VoiceMemGb = None,
    shot_mem_gb: ShotMemGb = None,
    voice_model: VoiceModel = None,
    config: ConfigFile = None,
) -> None:
    """Run doctor, migrate, recover interrupted jobs, then serve the API and worker."""
    settings = _settings(
        host=host,
        api_port=api_port,
        ui_port=ui_port,
        data_root=data_root,
        backend=backend,
        models_path=models_path,
        ollama_url=ollama_url,
        drawthings_url=drawthings_url,
        image_mem_gb=image_mem_gb,
        voice_mem_gb=voice_mem_gb,
        shot_mem_gb=shot_mem_gb,
        voice_model=voice_model,
        config=config,
    )
    raise typer.Exit(run_up(settings, allow_degraded=allow_degraded))
