"""Standalone word-timing worker (Whisper through mlx-audio).

Runs inside the mlx-audio uv environment, so it must not import `reelforge`.

    python align_worker.py --audio A.wav --text "..." --language hi --model ID

Prints one JSON line: [{"text", "start_s", "end_s"}, ...].
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from pathlib import Path
from typing import Any


def _unshadow() -> None:
    here = Path(__file__).resolve().parent
    sys.path[:] = [p for p in sys.path if Path(p or ".").resolve() != here]
    loaded = sys.modules.get("mlx_audio")
    if (
        loaded is not None
        and Path(getattr(loaded, "__file__", None) or "").resolve().parent == here
    ):
        del sys.modules["mlx_audio"]


def _words(result: Any) -> list[dict[str, Any]]:
    """Pull word timestamps out of an mlx-audio speech-to-text result."""
    out: list[dict[str, Any]] = []
    segments = getattr(result, "segments", None)
    if segments is None and isinstance(result, dict):
        segments = result.get("segments")
    for seg in segments or []:
        words = seg.get("words") if isinstance(seg, dict) else getattr(seg, "words", None)
        for w in words or []:
            get = w.get if isinstance(w, dict) else lambda k, d=None, _w=w: getattr(_w, k, d)
            text = str(get("word", get("text", ""))).strip()
            start, end = get("start"), get("end")
            if text and start is not None and end is not None:
                out.append({"text": text, "start_s": float(start), "end_s": float(end)})
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--audio", required=True)
    ap.add_argument("--text", default="")
    ap.add_argument("--language", default="en")
    ap.add_argument("--model", required=True)
    args = ap.parse_args()
    _unshadow()
    try:
        utils: Any = importlib.import_module("mlx_audio.stt.utils")
        model: Any = utils.load_model(args.model)
        result: Any = model.generate(args.audio, word_timestamps=True, language=args.language)
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(f"{type(exc).__name__}: {exc}\n")
        return 1
    words = _words(result)
    if not words:
        sys.stderr.write("no word timestamps in the result\n")
        return 1
    sys.stdout.write(json.dumps(words, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
