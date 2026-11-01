"""Story validation errors with field paths."""

from __future__ import annotations

from pydantic import BaseModel


class StoryError(BaseModel):
    """One problem in story.yaml. `path` is empty for root-level problems."""

    path: str
    message: str
    line: int | None = None
    column: int | None = None

    def __str__(self) -> str:
        return f"{self.path}: {self.message}" if self.path else self.message


class StoryInvalid(Exception):
    """story.yaml failed to load or validate; `errors` lists every problem found."""

    def __init__(self, errors: list[StoryError]) -> None:
        self.errors = errors
        super().__init__("; ".join(str(e) for e in errors))
