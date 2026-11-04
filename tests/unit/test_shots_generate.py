from __future__ import annotations

from reelforge.config import Settings
from reelforge.shots.prompts import TALKING_SUFFIX, compose_motion_prompt
from reelforge.shots.state import SHOT_OOM_MESSAGE, is_oom, size_for


def test_sizes_come_from_settings():
    s = Settings(shot_draft_size="352x640", shot_final_size="480x832")
    assert size_for(s, "draft") == (352, 640)
    assert size_for(s, "final") == (480, 832)


def test_oom_is_detected_case_insensitively():
    assert is_oom(SHOT_OOM_MESSAGE) and is_oom("killed, likely out of memory")
    assert not is_oom("ltx-2-mlx failed: bad frames")


def test_motion_prompt_has_look_verbatim_and_talking_suffix_only_for_talking():
    look = "round  red tomato"
    talking = compose_motion_prompt(motion="slow push in", look=look, shot_type="talking")
    action = compose_motion_prompt(motion="slow push in", look=look, shot_type="action")
    assert look in talking and look in action
    assert TALKING_SUFFIX in talking and TALKING_SUFFIX not in action
