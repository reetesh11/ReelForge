import pytest

from reelforge.story.age import AGE_ERROR, age_band, check_age


@pytest.mark.parametrize(
    ("age", "band"),
    [(12, "child"), (13, "teenager"), (19, "teenager"), (20, "young adult"), (39, "young adult"),
     (40, "middle-aged"), (59, "middle-aged"), (60, "elderly")],
)  # fmt: skip
def test_band_boundaries(age, band):
    assert age_band(age) == band


@pytest.mark.parametrize("bad", [0, 121, -1, 1.5, "7", True, [3]])
def test_bad_ages(bad):
    with pytest.raises(ValueError) as ei:
        check_age(bad)
    assert str(ei.value) == AGE_ERROR


def test_good_ages():
    assert check_age(None) is None and check_age(1) == 1 and check_age(120) == 120
