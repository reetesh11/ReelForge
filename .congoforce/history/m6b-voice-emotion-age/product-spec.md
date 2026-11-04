# Product spec — Add voice emotion, character age and working speed to OmniVoice takes

Binding voice behaviour: `docs/voice-levers.md`. Existing surface: voice screen `web/src/voice/` (`VoiceBoard.tsx`, `LineCard.tsx`, `VoiceSetup.tsx`), cast screen `web/src/cast/`, story schema `src/reelforge/story/schema.py` (`Character` has `name`, `look`, `voice`; `Voice` has `speed`). Mapping values are NOT part of this spec: they live in one table and are set by the spike (R11). Wherever this spec quotes a value (for example 150 ms), it is a default or a seed.

## User-facing behaviour

### 1. Speed slider works (R1)
- The existing "Speed" slider on each line card (`Speed value` output, e.g. `1.25x`) now changes the take length for OmniVoice voices. Speed above 1.0 gives a shorter take, below 1.0 a longer one. At 1.00x nothing changes from today.
- The take's recorded params include the effective duration in seconds that was requested.
- Changing speed behaves as today (marks the take stale, no automatic regeneration).

### 2. Emotion on a line (R2, R3, R4, R9)
- Each line card gets an **Emotion** picker with five options: `None`, `Happy`, `Sad`, `Fear`, `Anger`. Default `None`. Changing it saves immediately and marks that line's take stale (see R8 below). It does not regenerate.
- A user can also mark a phrase inside the line text with markup, for example `Tum kahan ho? <sad>Mujhe akela chhod diya.</sad>`. The line edit box accepts this markup. Allowed names: `happy`, `sad`, `fear`, `anger`.
- Rules for combining:
  - No markup and picker `None`: no emotion, behaves exactly as before.
  - Picker set, no markup: the whole line has that emotion; one model call.
  - Markup present: each marked phrase uses its own emotion; unmarked text in the same line uses the picker emotion (or none if the picker is `None`). Adjacent segments are split into phrases, each synthesised separately, then joined with a silence (default 150 ms) into one take.
  - A line with a single resulting emotion, even if written as markup around the whole line, is one model call.
- The line text shown on the voice screen (card text, edit box when not editing), in the shot and assembly screens, and in captions never shows `<sad>` / `</sad>` markup or any `[...]` nonverbal tag. In the edit box only, the markup the user typed stays visible so it can be edited.
- Nonverbal tags added by the mapping (for example `[sigh]`) are added only to the text sent to the model. They are never stored in the displayed text.

### 3. "How this will sound" panel (R9)
- Each line card has a collapsible panel titled **How this will sound**, collapsed by default.
- It shows the effective settings that the next take will use, per phrase when there are several: emotion, nonverbal tag and position, pitch value, speed and resulting duration target, generation settings, post-processing (semitones, gain dB, pause), age band (if the character has an age), and which reference clip is used (`Neutral reference` or `Sad reference clip`, etc.).
- For a line whose take already exists, the panel shows the values recorded in that take, and a note `Settings changed since this take` if the current effective settings differ.
- With emotion `None` and speed 1.00x the panel says `Default delivery. No emotion settings applied.`
- Play, Approve and Re-take work as before.

### 4. Character age (R6, R7, R9)
- Cast screen: character creation and edit get an optional **Age (years)** field, whole number 1 to 120. Empty means no age.
- Story schema: a character may carry `age` (integer 1 to 120). When the story gives no age, the story-structuring step proposes one from the `look` text (for example "late 60s" gives about 65); the proposal is shown as a normal editable value in the story and cast, not hidden.
- The derived band is shown next to the age: `child` (0-12), `teenager` (13-19), `young adult` (20-39), `middle-aged` (40-59), `elderly` (60+). Example: `Age 67 (elderly)`.
- Character voice setup (`VoiceSetup`) shows the age and band read-only with a link or control to edit the age.
- Effect of age by voice type:
  - OmniVoice preset or designed voice: the band is sent as the `instruct` age value.
  - OmniVoice cloned voice: the band is sent only when the project setting (recorded by the spike result) says age has an effect on cloned voices; default is off. When off, the setup shows: `A cloned voice follows its reference clip. Age is not applied.`
  - Kokoro: age picks among preset voices and applies a small post shift; the setup shows an `Experimental` badge next to it.
- Changing age marks that character's takes stale and does not regenerate.

### 5. Per-emotion reference clips for cloned voices (R12)
- In the character voice setup for a cloned voice, below the neutral reference, a section **Emotion reference clips** lists `Happy`, `Sad`, `Fear`, `Anger`. Each row shows: empty state `No clip. The neutral reference and emotion settings are used.`, or the clip with an audio player, its transcript, and a Remove button.
- Each row offers two ways to add a clip:
  - **Upload clip**, with a required transcript field. Content and size are checked exactly as for the neutral reference.
  - **Use a take**: on a line card, a take of that voice has an action `Use this take as the <emotion> reference` (one entry per emotion; the take's own text is used as the transcript, editable before saving).
- When a line's emotion has a clip, that clip and its transcript are the reference audio and text for the take, and the panel says so. Other emotions and the neutral line keep the neutral reference. The lever mapping still applies on top.
- Replacing or removing a clip marks stale only the takes that were made with it.
- Not shown for preset voices (they have no reference).

### 6. Stale and regeneration (R8)
- Changing a line's emotion, markup, a character's age, a clip, or the mapping table marks only the takes that depend on it as `Stale`, using the existing stale label and chain: the scene's talking shot is also marked stale, and the shot's frame count follows the new take length when the take is regenerated (as in M4 and M5). Nothing regenerates automatically.
- Mapping change: takes whose recorded mapping values differ from the current mapping for their emotion are stale; takes with no emotion are not.

### 7. Mock backend (R10)
- The mock voice backend honours the requested duration (WAV length follows `duration_s`) and the mapping; post-processing runs on its WAV. The whole path works offline.

### 8. Measurement spike (R11)
- A script under `tools/` (or `docs/`) sweeps one lever at a time on the cloned uncle voice and prints/writes a table with columns: lever, value, duration (s), median pitch (Hz), pitch spread, loudness, brightness. It runs only on the reference Mac with the real model. Results go into `docs/voice-levers.md` (Status column and experiment log), and the mapping table and the cloned-age setting are set from it. The spike runs early, before mapping values are frozen.

## Acceptance criteria

- AC-1: For the same line, speed 0.8 gives a take at about 1/0.8 = 1.25x the length of the speed 1.0 take, and speed 1.25 about 0.8x the length, each within 10 percent of that ratio. The 1.25 take is shorter than the 1.0 take, which is shorter than the 0.8 take. Speed 1.0 produces the same take length as before this change (no `duration_s` is passed beyond what was passed before). The take params record the effective duration.
- AC-2: Generating a take for a line with `<sad>` stores in the take params: the sad tag(s) and position, the pitch value, the duration scale, generation settings and post-processing (semitones, gain dB, pause) as given by the mapping table at that moment. After the mapping table is edited, the next take records the new values; existing takes keep their recorded values (and show as stale per section 6).
- AC-3: No displayed line text (voice cards, shot and assembly views, API text meant for display) and no caption text contains `<happy>`, `<sad>`, `<fear>`, `<anger>` or their closing forms, or any `[...]` tag. Only the line edit box shows the user's own markup.
- AC-4: A line with two phrases of different emotions makes exactly two model calls and one joined take. The silence between phrases equals the configured value (default 150 ms) within 20 ms, measured on the joined WAV.
- AC-5: On a test tone, pitch shift with a positive semitone value raises the measured median pitch and a negative value lowers it. If the ffmpeg build lacks `rubberband`, the take fails with the message `ffmpeg is missing the "rubberband" filter, needed for pitch and tempo changes. Install ffmpeg-full.` and the take is not produced; the step is never skipped silently. Post-processing runs without a shell.
- AC-6: An unknown emotion value, whether as the per-line value or in markup (for example `<joy>`), is rejected with `Unknown emotion "joy". Use one of: happy, sad, fear, anger.` and nothing is saved. A line with no emotion and no markup produces the same params and audio path as before this change.
- AC-7: A character can be created (cast screen and story schema) and edited with an integer age from 1 to 120. Ages 0, 121, negative, non-integer or non-numeric are rejected with `Age must be a whole number from 1 to 120.` Empty age is allowed. The band is `child` at 12, `teenager` at 13 and 19, `young adult` at 20 and 39, `middle-aged` at 40 and 59, `elderly` at 60. When the story has no age, the structuring step proposes one from the look text; an explicit story age is never overwritten.
- AC-8: For an OmniVoice preset voice with an age, the generation call's `instruct` contains the band (for example `elderly`), combined with any emotion pitch value, one value per category. For a cloned voice the band appears in `instruct` only when the cloned-age setting is on; the default is off, and the setting records which way the spike decided. A character with no age sends no age value.
- AC-9: Changing one line's emotion marks that line's voice take and its scene's talking shot stale, and no other scene's take or shot. Changing a character's age marks all and only that character's takes stale. Nothing is regenerated automatically in either case; no job is started.
- AC-10: Each line card shows the Emotion picker (None, Happy, Sad, Fear, Anger) and the collapsible "How this will sound" panel with effective settings. The character voice setup shows age and band, or `No age set` when empty, and the cloned-voice message from section 4 when applicable.
- AC-11: With the mock backend, a project with emotion lines and characters with ages goes through the full voice path (generate, play, approve, re-take) with no outbound network connection.
- AC-12: All existing M1 to M6 tests pass unchanged. Existing `GET` responses keep their keys; new fields (emotion, age, band, clips, effective settings) are omitted when empty.
- AC-13: The spike has been run on the reference Mac; its table is in `docs/voice-levers.md` with the Status column and experiment log updated. The mapping is consistent with the measured direction: measured median pitch for happy is higher than for sad, and the take for fear is shorter than for sad. Tests assert direction only, never specific mapping values.
- AC-14: Manual, on the reference Mac: the owner regenerates the Grumpy Uncle lines with an emotion and age set, listens, and records in `docs/manual-checks.md` whether delivery is audibly different and acceptable.
- AC-15: With a sad clip on a cloned voice, a take for a `sad` line is generated with that clip as `ref_audio` and its transcript as `ref_text`; a `happy` line on the same voice still gets the neutral reference. A voice with no per-emotion clips generates exactly as before. The clip's artifact is recorded among the take's inputs.
- AC-16: A per-emotion clip can be uploaded (with transcript) or created from an existing take of that voice. A non-audio upload (judged by content, not file name) is rejected with the same message and size limit the neutral reference uses. Removing a clip marks stale only the takes made with that clip; takes made with other clips or the neutral reference are not stale. The clip is stored as an artifact with its inputs recorded.

## Edge cases and errors
- Markup that is unclosed (`<sad>text`), nested, or has an empty phrase (`<sad></sad>`): rejected on save with `Emotion markup is not valid: close every <emotion> tag and do not nest them.`; nothing saved.
- Phrase text that becomes empty after markup removal is not sent to the model; the line is rejected if no speakable text remains.
- A user-typed `[sigh]` style tag in a line is stripped from displayed text and captions (AC-3). Whether it is still sent to the model is an open question.
- Speed with emotion duration scale: both apply (the computed duration is the estimate times the emotion scale divided by speed). The panel shows the final target.
- Speed far from 1.0 and extreme age/emotion combinations: existing speed range checks stay. If `duration_s` would be outside what the model accepts, the take fails with a clear message rather than clipping silently.
- Kokoro voices: speed behaves as today; emotion picker is shown but the panel says `Emotion is not applied for this voice.`; age is the experimental mapping only.
- Emotion with per-emotion clip but the clip file is missing: take fails with a clear message naming the emotion; the neutral reference is not silently substituted.
- Character with no voice: line card keeps its existing `no_voice` state; the picker still works.
- Age edit on a character whose voice is a cloned voice with the cloned-age setting off: takes are still marked stale only if the age is actually sent to the model. [Interpretation: see open question 3.]
- Removing a clip, editing the mapping, or changing age while a voice job is running: the running job finishes; the result records the values it used and is marked stale if they no longer match.
- Existing projects with no age, emotion or clips load unchanged.

## Out of scope
- Music and any assembly change beyond picking up new takes.
- Other TTS models or engines (OmniVoice only).
- Per-word control inside a phrase; emotion for Kokoro beyond the experimental age mapping.
- Voice design from scratch.
- M7 hardening.
- A UI for editing the mapping table (it is a config/table edited outside the app).

## Open questions
1. Precedence when both a picker emotion and phrase markup exist: this spec has unmarked text fall back to the picker emotion and marked phrases override it. Confirm, or should markup replace the picker entirely?
2. Should a nonverbal tag typed by the user in a line (for example `[sigh]`) still be sent to the model while hidden from display and captions, or be removed everywhere?
3. If age does not change cloned-voice output (setting off), should an age edit still mark takes stale? This spec says no, because age is not sent; AC-9 says "marks that character's takes stale" without that condition.
4. Which of the owner's wording to use for the "Use this take" transcript: take text with markup and tags removed (assumed here).
5. Silence between phrases: default 150 ms. Should it be user-editable per project, or only a config value alongside the mapping?
