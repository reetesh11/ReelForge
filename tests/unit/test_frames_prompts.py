from __future__ import annotations

from reelforge.frames.prompts import FRAMING_PHRASES, PRODUCT_PHRASE, compose_frame_prompt
from reelforge.frames.service import characters_in_scene
from reelforge.story.schema import Character, Scene, Story


def _story(**scene: object) -> tuple[Story, Scene]:
    sc = Scene(id="s1", action="Something happens", **scene)  # type: ignore[arg-type]
    story = Story(
        version=1,
        title="t",
        language="english",
        style="3D",
        aspect="9:16",
        fps=24,
        target_seconds=10,
        characters={
            "tomato": Character(name="Tamatar", look="red tomato"),
            "potato": Character(name="Aloo", look="brown potato"),
        },
        scenes=[sc],
    )
    return story, sc


def test_look_is_verbatim_and_product_only_when_asked():
    look = "round  red tomato,  big eyes"

    def make(product: bool) -> str:
        return compose_frame_prompt(
            scene_sentence="Tamatar waves",
            look=look,
            framing="wide",
            style="",
            other_looks=[("Aloo", "brown potato")],
            product=product,
        )

    on = make(True)
    off = make(False)
    assert look in on and "brown potato" in on and FRAMING_PHRASES["wide"] in on
    assert PRODUCT_PHRASE in on and PRODUCT_PHRASE not in off


def test_speaker_first_then_mention_order_then_first_character():
    story, scene = _story(speaker="potato", line="hi Tamatar")
    assert characters_in_scene(story, scene) == ["potato"]  # a line only addresses Tamatar
    story, scene = _story(line="hi Tamatar")
    assert characters_in_scene(story, scene) == ["tomato"]
    story, scene = _story(setting="Aloo meets Tamatar")
    assert characters_in_scene(story, scene) == ["potato", "tomato"]
    story, scene = _story()
    assert characters_in_scene(story, scene) == ["tomato"]
