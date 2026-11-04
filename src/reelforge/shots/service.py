"""Shots stage operations (filled in by the shots service task)."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from reelforge.context import AppContext


def shots_complete(ctx: AppContext, project_id: str) -> bool:
    return False
