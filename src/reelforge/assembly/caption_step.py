"""The "Burning captions" step: align, build `captions.ass`, decide whether to burn."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from reelforge.assembly.edl import Edl

if TYPE_CHECKING:
    from reelforge.context import AppContext


async def prepare_captions(ctx: AppContext, edl: Edl, out_dir: Path, ass: Path) -> bool:
    """Write `captions.ass`; True when the encode step must burn it in."""
    del ctx, edl, out_dir
    ass.write_text("[Script Info]\n", encoding="utf-8")
    return False
