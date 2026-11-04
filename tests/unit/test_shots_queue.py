from __future__ import annotations

from reelforge.shots.service import estimate_s, minutes_text
from reelforge.shots.state import DEFAULT_ESTIMATE_S


def test_estimate_uses_history_for_same_type_and_size_only():
    history = {("talking", 320, 576): 95.4}
    assert estimate_s(history, "talking", "draft", 320, 576) == 95
    assert (
        estimate_s(history, "action", "draft", 320, 576) == DEFAULT_ESTIMATE_S[("action", "draft")]
    )
    assert (
        estimate_s(history, "talking", "final", 448, 768)
        == DEFAULT_ESTIMATE_S[("talking", "final")]
    )
    assert estimate_s({("action", 320, 576): 0.2}, "action", "draft", 320, 576) == 1


def test_minutes_round_up_and_never_below_one():
    assert minutes_text(1) == "about 1 min"
    assert minutes_text(60) == "about 1 min"
    assert minutes_text(61) == "about 2 min"
    assert minutes_text(330) == "about 6 min"
