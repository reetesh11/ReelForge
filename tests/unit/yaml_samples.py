"""Shared story YAML for unit tests."""

STORY = """\
# a tale
version: 1
title: "Wedding"
language: english
style: "3D cartoon"
aspect: "9:16"
fps: 24
target_seconds: 12
characters:
  tomato:
    name: "Tamatar"   # grumpy
    look: "round red tomato, big eyes"
    voice: { mode: designed, ref: v1, speed: 1.05 }
scenes:
  - id: s1
    action: "enters"
    duration: 2.0
  - id: s2
    speaker: tomato
    line: "Hello"
    action: "talks"
    duration: 2.0
"""
