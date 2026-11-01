"""Command line entry point (commands are added in a later task)."""

from __future__ import annotations

import typer

from reelforge import __version__

app = typer.Typer(name="reelforge", help="ReelForge command line.", no_args_is_help=True)


def _version(value: bool) -> None:
    if value:
        typer.echo(__version__)
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False, "--version", callback=_version, is_eager=True, help="Show version and exit."
    ),
) -> None:
    """ReelForge: local-first reel production."""
