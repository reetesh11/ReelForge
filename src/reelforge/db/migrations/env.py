"""Alembic environment: runs against the SQLite file named by the `db_path` option."""

from __future__ import annotations

from pathlib import Path

from alembic import context

from reelforge.db.models import Base
from reelforge.db.session import make_engine

config = context.config
target_metadata = Base.metadata


def run_migrations_online() -> None:
    engine = make_engine(Path(config.get_main_option("db_path") or ""))
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


run_migrations_online()
