"""Programmatic Alembic upgrade using the migrations packaged with the library."""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


def upgrade(db_path: Path | str, revision: str = "head") -> None:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
    cfg.set_main_option("db_path", str(path))
    command.upgrade(cfg, revision)
