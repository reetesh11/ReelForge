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
from typing import Any, cast


def _unshadow() -> None:
    here = Path(__file__).resolve().parent
    sys.path[:] = [p for p in sys.path if Path(p or ".").resolve() != here]
    loaded = sys.modules.get("mlx_audio")
    if (
        loaded is not None
        and Path(getattr(loaded, "__file__", None) or "").resolve().parent == here
    ):
        del sys.modules["mlx_audio"]


def _attr(obj: Any, name: str) -> Any:
    if isinstance(obj, dict):
        return cast("dict[str, Any]", obj).get(name)
    return getattr(obj, name, None)


def _words(result: Any) -> list[dict[str, Any]]:
    """Pull word timestamps out of an mlx-audio speech-to-text result."""
    out: list[dict[str, Any]] = []
    segments: Any = _attr(result, "segments")
    for seg in cast("list[Any]", segments or []):
        words: Any = _attr(seg, "words")
        for w in cast("list[Any]", words or []):
            word: Any = _attr(w, "word")
            text = str(word if word is not None else _attr(w, "text") or "").strip()
            start: Any = _attr(w, "start")
            end: Any = _attr(w, "end")
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
