"""Helpers for the M2 story acceptance tests. Public surfaces only."""

from __future__ import annotations

import copy
import json
from typing import Any

from rf_helpers import create_project, make_client, make_settings, passing_report, wait_job

STORY_YAML = """\
# Tomato tale
version: 1
title: "Wedding thekua rescue"
language: hinglish            # hindi | english | hinglish
style: "3D Pixar-style cartoon, warm festive lighting"
aspect: "9:16"
fps: 24
target_seconds: 12
characters:
  tomato:
    name: "Tamatar"   # the grumpy one
    look: "round glossy red tomato, big expressive eyes, tiny green leaf hat, gold sherwani"
    voice: { mode: designed, ref: voice_tomato_01, speed: 1.05 }
  potato:
    name: "Aloo"
    look: "chubby brown potato, bushy black moustache, pink turban, white kurta"
scenes:
  - id: s1
    setting: "Indian wedding mandap at night"
    action: "Aloo bursts in through the crowd, panting"
    framing: wide
    duration: 2.0
  - id: s2
    speaker: tomato
    line: "Arre Aloo, itni der kyun?"
    action: "Tamatar crosses his arms, annoyed"
    framing: closeup
    duration: 2.0
  - id: s3
    speaker: potato
    line: "Mithai ke bina shaadi?"
    action: "Aloo proudly lifts the box"
    framing: closeup
    duration: 2.0
  - id: s4
    action: "Guests rush toward the box, cheering"
    framing: medium
    continue_from: s3
    duration: 2.5
  - id: s5
    action: "Both characters wink at camera"
    framing: medium
    duration: 2.0
    end_card: true
music: { mode: library, track: festive_dhol_01, duck_under_speech: true }
captions: { style: bold_pop, script: latin }
"""


def story_dict(n_scenes: int = 5, **over: Any) -> dict[str, Any]:
    scenes = [
        {
            "id": f"s{i}",
            "setting": f"Place {i}",
            "action": f"Something happens {i}",
            "framing": "medium",
            "duration": 2.0,
        }
        for i in range(1, n_scenes + 1)
    ]
    scenes[1]["speaker"] = "tomato"
    scenes[1]["line"] = "Arre Aloo!"
    d: dict[str, Any] = {
        "version": 1,
        "title": "Tale",
        "language": "english",
        "style": "3D cartoon",
        "aspect": "9:16",
        "fps": 24,
        "target_seconds": 12,
        "characters": {
            "tomato": {"name": "Tamatar", "look": "round red tomato, big eyes, leaf hat, gold sherwani"},
            "potato": {"name": "Aloo", "look": "chubby brown potato, moustache, pink turban, white kurta"},
        },
        "scenes": scenes,
    }
    d.update(over)
    return copy.deepcopy(d)


def reply(story: dict[str, Any] | None, questions: list[dict[str, str]] | None = None) -> str:
    return json.dumps({"story": story, "questions": questions or []})


def new_ctx(tmp_path, *, llm=None, **settings_over: Any):
    from reelforge.context import AppContext

    async def _unload() -> None:
        return None

    return AppContext.create(
        make_settings(tmp_path, **settings_over),
        available_gb=lambda: 64.0,
        ollama_unload=_unload,
        doctor=lambda: passing_report(),
        llm=llm,
    )


def put(client, pid: str, text: str):
    return client.put(
        f"/api/v1/projects/{pid}/story", content=text.encode(), headers={"Content-Type": "text/plain"}
    )


def import_(client, pid: str, text: str):
    return client.post(
        f"/api/v1/projects/{pid}/story:import",
        content=text.encode(),
        headers={"Content-Type": "text/plain"},
    )


def versions(client, pid: str) -> list[dict[str, Any]]:
    r = client.get(f"/api/v1/projects/{pid}/story/versions")
    assert r.status_code == 200, r.text
    return r.json()


def structure(client, ctx, pid: str, **body: Any):
    body.setdefault("storyline", "A tomato and a potato at a wedding, five scenes")
    r = client.post(f"/api/v1/projects/{pid}/story:structure", json=body)
    assert r.status_code == 202, r.text
    job = r.json()
    return wait_job(ctx, job["id"], {"succeeded", "failed", "cancelled"}, timeout=30)


__all__ = ["create_project", "make_client"]
