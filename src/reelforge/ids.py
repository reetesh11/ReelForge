"""ULID helpers: every primary key is a 26-character Crockford base32 ULID."""

from __future__ import annotations

import re

from ulid import ULID

_ULID_RE = re.compile(r"^[0-7][0-9A-HJKMNP-TV-Z]{25}$")


def new_id() -> str:
    return str(ULID())


def is_ulid(value: str) -> bool:
    return bool(_ULID_RE.match(value))
