"""Inputs fingerprint: SHA-256 over canonical JSON of everything that shapes an artifact."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence


def compute_inputs_fp(
    *,
    adapter: str,
    adapter_version: str,
    model_key: str,
    model_revision: str,
    prompt: str,
    seed: int,
    params: Mapping[str, object],
    input_sha256: Sequence[str],
) -> str:
    payload = {
        "adapter": adapter,
        "adapter_version": adapter_version,
        "model_key": model_key,
        "model_revision": model_revision,
        "prompt": prompt,
        "seed": seed,
        "params": dict(params),
        "input_sha256": list(input_sha256),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
