---
class: feature
size: large
title: Add voice emotion, character age and working speed to OmniVoice takes
---
# Requirements — Add voice emotion, character age and working speed to OmniVoice takes

## Problem
The voice speed slider does nothing on the MLX OmniVoice build, because `speed` is dropped into `**kwargs`. Lines cannot carry an emotion, and a character has no age (only free text in `look`). The owner wants lines to carry `happy`, `sad`, `fear` or `anger`, translated by one mapping into OmniVoice levers (tags, `instruct`, `duration_s`, generation settings, ffmpeg post-processing). The owner also wants a numeric character age that feeds voice creation, and optional per-emotion reference clips for cloned voices. Binding detail is in `docs/voice-levers.md`. The code touched is mainly `src/reelforge/voice/` (`generate.py`, `service.py`, `slots.py`, `uploads.py`), `src/reelforge/cast/`, the story schema and the voice and cast screens in `web/src/`.

## Requirements
- R1. When a voice `speed` is set, the system shall pass a computed `duration_s` to OmniVoice so that speed above 1.0 gives a shorter take and below 1.0 a longer one. At speed 1.0 behaviour is unchanged. The take records its effective duration.
- R2. When a voice line carries an emotion (`happy`, `sad`, `fear`, `anger`) as a per-line hint, or on a phrase such as `<sad>...</sad>`, the system shall accept it. If the emotion is unknown, then the system shall reject it with a clear message. On-screen text and captions shall never contain the markup or nonverbal tags.
- R3. The system shall keep one mapping table from emotion to nonverbal tag(s) and position, `instruct` pitch, duration scale, generation settings, and post-processing (semitones, gain dB, pause), seeded from section 9 of `docs/voice-levers.md`. Generation shall apply it and store the applied values in the take params.
- R4. When a line has phrase-level emotions, the system shall synthesise each phrase separately with its own levers and join them with a silence (default 150 ms) into one take. A line with a single emotion is one model call.
- R5. The system shall run pitch shift and tempo with ffmpeg `rubberband` and gain with a volume filter, as argument lists with no shell. If ffmpeg lacks the filter, then the take shall fail with a clear message and not skip the step.
- R6. A character shall have an optional integer `age` (1 to 120) set at creation (cast screen and story schema) and editable. When the story gives no age, the story-structuring step shall propose one from the look text. A band is derived from age: child 0-12, teenager 13-19, young adult 20-39, middle-aged 40-59, elderly 60+.
- R7. When a voice is created, the system shall pass the age band as the `instruct` age value for OmniVoice preset or designed voices. For a cloned voice it shall pass the age only when the measured spike shows an effect (a setting records which); otherwise the UI shall say a cloned voice follows its reference clip. For Kokoro, age shall pick among preset voices with a small post shift, marked experimental.
- R8. When a line's emotion, a character's age, or the mapping changes, the system shall mark only the affected voice takes stale (and, through the existing chain, that scene's talking shot) and shall not regenerate anything automatically. Shot frame count follows the new take length as in M4 and M5.
- R9. The voice screen shall show, on each line card, an emotion picker (none, happy, sad, fear, anger) and a collapsible "How this will sound" panel with the effective settings. The character voice setup shall show age and band. Play, approve and re-take shall work as before.
- R10. The mock backend shall honour duration and the mapping, and post-processing shall run on its WAV, so everything runs in tests and CI.
- R11. Before the mapping is frozen, a script in `docs/` or `tools/` shall sweep each lever alone on the cloned uncle voice and write a table of duration, median pitch, pitch spread, loudness and brightness. Results shall be recorded in `docs/voice-levers.md` (Status column and experiment log).
- R12. For a cloned voice, each emotion may have its own reference clip with transcript. When a line's emotion has a clip, the take shall use that clip and transcript as `ref_audio` and `ref_text`; otherwise the neutral reference and the lever mapping apply. A clip can be uploaded (content and size checked like the neutral reference) or created from an existing take of that voice. Clips belong to the voice, are shown in the character voice setup, and are stored as artifacts with inputs recorded. Changing or removing a clip marks only the takes made with it stale.

## Acceptance criteria
- AC-1: With speed 0.8 and 1.25 on the same line, take lengths differ in the right direction within 10 percent of the requested ratio; speed 1.0 gives the same length as before this change.
- AC-2: A line with `<sad>` produces a take whose recorded params include the sad tag, pitch value, duration scale and post-processing values from the mapping table. Changing the table changes the next take but not existing takes.
- AC-3: Displayed line text and captions contain no emotion markup and no `[...]` tags.
- AC-4: A line with two phrase-level emotions makes two model calls and one joined take, with the silence between phrases within 20 ms of the setting.
- AC-5: Pitch shift raises the measured median pitch for a positive semitone value and lowers it for a negative one on a test tone. A missing `rubberband` filter fails the take with a message.
- AC-6: An unknown emotion value is rejected. A line with no emotion behaves exactly as before.
- AC-7: A character can be created and edited with an age; an age outside 1 to 120 is rejected; the band is correct at 12/13, 19/20, 39/40 and 59/60.
- AC-8: For an OmniVoice preset voice the generation call receives the age band in `instruct`. For a cloned voice it receives it only when the spike result enables it (a setting records which).
- AC-9: Changing one line's emotion marks only that line's voice take and its scene's shot stale. Changing a character's age marks that character's takes stale. Other scenes are not stale and nothing regenerates automatically.
- AC-10: The voice screen shows the emotion picker and the effective settings; the character setup shows age and band.
- AC-11: The full voice path with emotion and age completes on the mock backend with no outbound network connection.
- AC-12: Existing frozen M1 to M6 tests pass unchanged.
- AC-13: The measurement spike has been run and its table is in `docs/voice-levers.md`. Mapping values match the measured direction (higher median pitch for happy than sad, shorter take for fear than sad).
- AC-14: Manual check on the reference Mac, recorded in `docs/manual-checks.md`: the owner regenerates the Grumpy Uncle lines with an emotion and age set, listens, and records whether delivery is audibly different and acceptable.
- AC-15: With a sad reference clip on a cloned voice, a take for a `sad` line receives that clip and transcript as reference inputs, and a `happy` line still receives the neutral reference. A voice with no per-emotion clips behaves exactly as before.
- AC-16: A per-emotion clip can be uploaded or created from an existing take; a non-audio upload is rejected by content check; removing the clip marks only the takes made with it stale.

## Out of scope
- Music and any assembly change beyond picking up new takes.
- Other TTS models or engines (OmniVoice only).
- Per-word control inside a phrase; emotion for Kokoro beyond the experimental age mapping.
- Voice design from scratch.
- M7 hardening.

## Assumptions
- Emotion is stored per line in the existing line model; the exact field and markup parsing are design choices for the spec stage.
- Mapping values are seeded from `docs/voice-levers.md` section 9 and may be revised by the spike (R11) without code changes elsewhere.
- AC-13 and AC-14 need the real model on the reference Mac and are manual. All other criteria run on the mock backend.
- AC-8 for cloned voices defaults to "age not passed" until the spike shows an effect.
- The frozen `GET` response shapes from M1 to M6 keep their keys; new fields are omitted when empty.

## Suggested split
Too big for one implement/verify loop. Suggested order, each shippable alone:
1. Speed and mapping core (R1, R3, R5, R10 plus mock): `duration_s` from speed, mapping table, ffmpeg post-processing, params recorded. Covers AC-1, AC-5, AC-11 (partial), AC-12.
2. Emotion markup and phrase splitting (R2, R4, R8 for emotion, R9 line cards): parsing, rejection, caption stripping, joined takes, staleness, emotion picker. Covers AC-2, AC-3, AC-4, AC-6, AC-9 (emotion part), AC-10 (picker).
3. Character age (R6, R7, R8 for age, R9 setup): model field, migration, story schema and structuring proposal, band, `instruct` age, staleness. Covers AC-7, AC-8, AC-9 (age part), AC-10 (age).
4. Measurement spike (R11): script and `docs/voice-levers.md` results. Covers AC-13. Should run before the mapping values and the cloned-voice age setting are frozen, so it may go first.
5. Per-emotion reference clips (R12): upload, create from take, selection, staleness. Covers AC-15, AC-16. Manual AC-14 closes the milestone.

## Open questions
- none
