import pytest

from reelforge.story.markup import (
    BAD_MARKUP,
    Segment,
    check_emotion,
    display_text,
    parse_segments,
    speech_text,
)


def test_segments_in_order():
    assert parse_segments("a <sad>b</sad> c <fear>d</fear>") == [
        Segment("a", None),
        Segment("b", "sad"),
        Segment("c", None),
        Segment("d", "fear"),
    ]


def test_whitespace_only_segments_dropped():
    assert parse_segments("<happy>x</happy>   ") == [Segment("x", "happy")]


def test_unknown_tag_names_the_value():
    with pytest.raises(ValueError, match='Unknown emotion "joy"'):
        parse_segments("<joy>x</joy>")
    with pytest.raises(ValueError, match='Unknown emotion "joy"'):
        parse_segments("x</joy>")


@pytest.mark.parametrize(
    "raw", ["<sad>x", "<sad>a<fear>b</fear></sad>", "<sad></sad>", "x</sad>", "<sad>a</fear>"]
)
def test_malformed_markup(raw):
    with pytest.raises(ValueError) as ei:
        parse_segments(raw)
    assert str(ei.value) == BAD_MARKUP


def test_plain_angle_brackets_are_not_markup():
    assert parse_segments("2 < 3 and 5 > 4") == [Segment("2 < 3 and 5 > 4", None)]


def test_sigh_kept_for_speech_and_stripped_for_display():
    raw = "<sad>[sigh]  Haan</sad> theek"
    assert speech_text(raw) == "[sigh] Haan theek"
    assert display_text(raw) == "Haan theek"


def test_check_emotion_none_and_value():
    assert check_emotion(None) is None and check_emotion("fear") == "fear"
