# ReelForge Phase 3 / M6b — Voice emotion and character age

Binding inputs: `docs/voice-levers.md` (every lever, its status, the draft emotion mapping and the age section; it wins on voice behaviour), `ReelForge — Product Spec.md` (Stage 3 Voice: "Emotion hint where the model supports it"), `ReelForge — Technical Spec.md` (voice stage, `gen_voice_take`, staleness). Parent: `phases/phase-3-assembly-player-hardening.md`. Requires M1 to M6 merged. Order agreed with the owner: M6 assembly (done), **M6b emotion and age (this)**, then music. Out of scope here: music, other TTS models (decided: OmniVoice only), M7 hardening.

## Inputs already decided
- OmniVoice has no emotion input. `<happy>`, `<sad>`, `<fear>` and `<anger>` are ReelForge markup that the pipeline translates into OmniVoice levers: inline nonverbal tags, `instruct` (pitch, age, whisper), `duration_s` for pace, generation settings, and ffmpeg post-processing (pitch shift, tempo, gain, pauses).
- The owner listened to the tag spike (`~/reelforge-spikes/uncle_emotion_tags/`): **the tag versions sound right**; go with tags. The `instruct` effect on a cloned voice is unclear and must be measured before relying on it.
- Known defect to fix here: the `speed` argument is ignored by the MLX OmniVoice build (it vanishes into `**kwargs`), so the speed slider does nothing. Convert speed to `duration_s`.
- The mapping from emotion to levers lives in one place (a table or config), seeded from section 9 of `docs/voice-levers.md`, and is changed by measurement, not by editing code in several places.
- Age is defined when a character is created and used when its voice is created. Today a character has only `name`, `look` and `voice`; age exists only as free text in `look`.

## Requirements
- R1. **Speed works:** the voice `speed` setting changes the length of an OmniVoice take (speed above 1.0 shorter, below 1.0 longer) by passing a computed `duration_s`; with speed 1.0 behaviour is unchanged. The take records the effective duration.
- R2. **Emotion markup in a line:** a voice line can carry an emotion (`happy`, `sad`, `fear`, `anger`) as a per-line hint and optionally on a phrase inside the line (for example `<sad>...</sad>`). Unknown emotions are rejected with a clear message. The line text shown on screen and in captions never contains the markup or the nonverbal tags.
- R3. **Emotion to levers:** one mapping table gives, per emotion: nonverbal tag(s) and position, `instruct` pitch value, duration scale, generation settings, and post-processing (semitones, gain dB, pause). The generation step applies it; the applied values are stored in the take's params so a take can be reproduced.
- R4. **Phrase splitting:** a line with phrase-level emotions is split, each phrase is synthesised separately with its own levers, then joined with short silences (default 150 ms) into one take. A line with a single emotion is one model call.
- R5. **Post-processing:** pitch shift and tempo use ffmpeg `rubberband`, gain uses a volume filter, run as argument lists, never through a shell. If ffmpeg lacks the filter the take fails with a clear message instead of silently skipping it.
- R6. **Character age:** a character has an `age` in years (optional integer, 1 to 120) set when the character is created (cast screen and story schema) and editable. The story-structuring step proposes an age from the look text when the story does not give one. A derived band (child 0-12, teenager 13-19, young adult 20-39, middle-aged 40-59, elderly 60+) is available from the age.
- R7. **Age in voice creation:** for OmniVoice preset or designed voices the age band is passed as the `instruct` age value. For a cloned voice the age is passed only when the measured spike shows it changes the output; otherwise the UI says that a cloned voice follows its reference clip. For Kokoro (no age control) the age picks among preset voices and applies a small post shift; this is marked experimental.
- R8. **Staleness:** changing a line's emotion, a character's age, or the mapping marks only the affected voice takes stale (and, through the existing chain, that scene's talking shot); nothing regenerates automatically. Because tags change take length, the shot frame count follows the new take as in M4 and M5.
- R9. **Voice screen:** each line card has an emotion picker (none, happy, sad, fear, anger) and shows the effective settings in a collapsible "How this will sound" panel; the character voice setup shows the age and the band. Play, approve and re-take work as before.
- R10. **Mock backend:** everything runs on the mock backend in tests and CI; the mock honours duration and the mapping, and post-processing runs on its WAV.
- R11. **Measurement spike (before the mapping is frozen):** a script in `docs/` or `tools/` sweeps each lever alone on the cloned uncle voice (instruct pitch values, duration scale, guidance, temperatures, per-emotion reference clip) and writes a table of duration, median pitch, pitch spread, loudness and brightness; results are recorded in `docs/voice-levers.md` (Status column and experiment log).
- R12. **Per-emotion reference clips:** for a cloned voice, each emotion may have its own reference clip (with its transcript) in addition to the neutral reference. When a line has an emotion that has a reference clip, that clip and its transcript are the `ref_audio` and `ref_text` for the take; otherwise the neutral reference is used and the lever mapping applies as usual. A clip can be uploaded (checked by content and size like the neutral reference) or created from an existing take of that voice ("Use this take as the sad reference"). Per-emotion clips belong to the voice, are shown on the character's voice setup, and are stored as artifacts with their inputs recorded. Changing or removing a clip marks only the takes made with it stale. Whether a reference clip beats the lever mapping is measured in R11 and recorded; the mapping and clips can be combined.

## Acceptance criteria
- AC-1: With speed 0.8 and 1.25 on the same line, take lengths differ in the right direction by within 10 percent of the requested ratio; speed 1.0 gives the same length as before this change.
- AC-2: A line with `<sad>` produces a take whose recorded params include the sad tag, pitch value, duration scale and post-processing values from the mapping table; changing the table changes the next take but not existing takes.
- AC-3: Displayed line text and captions contain no emotion markup and no `[...]` tags.
- AC-4: A line with two phrase-level emotions makes two model calls and one joined take, with the silence between phrases within 20 ms of the setting.
- AC-5: Pitch shift raises the measured median pitch for a positive semitone value and lowers it for a negative one on a test tone; a missing `rubberband` filter fails the take with a message.
- AC-6: An unknown emotion value is rejected; a line with no emotion behaves exactly as before.
- AC-7: A character can be created and edited with an age; an age outside 1 to 120 is rejected; the band is derived correctly at each boundary (12/13, 19/20, 39/40, 59/60).
- AC-8: For an OmniVoice preset voice the generation call receives the age band in `instruct`; for a cloned voice the call receives it only when the spike result enables it (a setting records which).
- AC-9: Changing one line's emotion marks only that line's voice take and its scene's shot stale; changing a character's age marks that character's takes stale; other scenes are not stale; nothing regenerates automatically.
- AC-10: The voice screen shows the emotion picker and the effective settings, and the character setup shows age and band.
- AC-11: The full voice path with emotion and age completes on the mock backend with no outbound network connection.
- AC-12: Existing frozen M1 to M6 tests pass unchanged.
- AC-13: The measurement spike has been run and its table is in `docs/voice-levers.md`; the emotion mapping values match the measured direction (higher pitch measured for happy than for sad, shorter for fear than for sad).
- AC-15: With a sad reference clip set on a cloned voice, a take for a `sad` line receives that clip and its transcript as the reference inputs and a `happy` line still receives the neutral reference; a voice with no per-emotion clips behaves exactly as before.
- AC-16: A per-emotion clip can be uploaded or created from an existing take; a non-audio upload is rejected by content check; removing the clip marks only the takes made with it stale.
- AC-14: Manual check on the reference Mac, recorded in `docs/manual-checks.md`: the owner regenerates the Grumpy Uncle lines with an emotion and age set, listens, and records whether the delivery is audibly different and acceptable.

## Out of scope
- Music (the next milestone) and any change to assembly beyond picking up new takes.
- Other TTS models or engines (Chatterbox, Parler, svara, Qwen3-TTS were set aside).
- Per-word control inside a phrase; emotion for Kokoro beyond the experimental age mapping.
- Voice design from scratch (creating a voice only from a description).

## Decided by the owner (2026-11-04)
- Four emotions: `happy`, `sad`, `fear`, `anger`.
- Age is a number of years (the band is derived from it), not a list pick.
- Per-emotion reference clips are **in this milestone** (R12).

## Open questions
- None.
