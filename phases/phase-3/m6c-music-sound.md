# ReelForge Phase 3 / M6c — Music, background score and sound effects

Binding inputs: `ReelForge — Product Spec.md` (music and mix), `ReelForge — Technical Spec.md` (assembly, EDL), `docs/voice-levers.md` (pattern for a lever table plus measurement spike), the Gujiya screenplay used in the first full test (below). Parent: `phases/phase-3-assembly-player-hardening.md`. Requires M1 to M6b merged. Order agreed with the owner: M6 assembly (done), M6b voice emotion and age (done), **M6c music and sound (this)**, then screenplay import and product composite (planned next). Out of scope: M7 hardening, screenplay import, product-image compositing.

## Why
The first full reel (Gujiya, 40.7 s) was judged "okay" mainly because it has no background music, no sound effects and no designed silence. The EDL already has `music.tracks` and `music.duck` slots, but `build_mix_graph` mixes dialogue only and `story.music` is a free-text placeholder (`mode`, `track`). The screenplay defines three music tracks, stingers and effects (drum roll, gong, ceramic crash, packaging crinkle, crunch), a hard silence on the tasting close-up, and wedding ambience.

## Decided by the owner (2026-11-05)
- **Both sources:** local generation plus per-cue upload of the owner's own file. A measurement spike runs on the reference Mac before the design is fixed.
- **Commercial use:** plan for it. Only models whose weights are MIT, Apache-2.0 or similarly commercial-friendly are allowed in `models.toml`; each model's licence appears in `credits.json` and in the export licence check. Non-commercial weights (for example MusicGen and AudioGen as far as known; verify) are excluded.
- **Scope:** a cue list tied to scenes; ducking and silence; stingers and sound effects; an ambient bed.

## Inputs already decided
- Candidate models, to be confirmed by the spike (licence and Mac support verified at the time of use, never from memory): ACE-Step 1.5 (MIT, community MLX builds, early) for music and score; OpenMOSS MOSS-SoundEffect v2.0 (Apache-2.0, MLX conversion, up to 30 s) for effects and ambience. Model IDs live only in `models.toml` and their adapters.
- All generation runs on the Mac, no outbound calls at render time; tests use the mock backend.
- Loudness stays at about -14 LUFS for the final mix (existing two-pass loudnorm).

## Requirements
- R1. **Cue list in the story:** `story.yaml` gains an ordered `audio` list. Each cue has `id`, `kind` (`music`, `sfx`, `ambience`, `silence`), `start` (a scene id plus an offset in seconds, or `scene_start`/`scene_end`), `end` or `duration`, `prompt` (text used for generation), `source` (`generate` or `file`), optional `gain_db`, `fade_in_s`, `fade_out_s`, and for music `duck` (true/false). The old free-text `music` block is read for existing stories and ignored when `audio` is present. Invalid cues (unknown scene, negative times, end before start, unknown kind) are rejected with a message that names the cue.
- R2. **Cue generation:** a job generates a cue's audio from its `prompt` and duration with the configured model, stores it as an artifact (inputs recorded: prompt, duration, seed, model), and keeps versioned takes like voice takes. Long music is made by generating up to the model's limit and extending or looping with a crossfade; the result is exactly the cue's length.
- R3. **Own files:** a cue with `source: file` takes an uploaded audio clip (checked by content and size, like voice reference clips), trimmed or looped to the cue length.
- R4. **Mix in the EDL:** the EDL carries each cue with resolved absolute start and end times, gains and fades; the filter graph mixes dialogue, music, sfx and ambience with per-cue fades. Rendering stays an ffmpeg argument-list pipeline; no shell.
- R5. **Ducking:** a music cue with `duck: true` drops by a set amount (default 9 dB, editable per project) while any dialogue is speaking, with attack and release (defaults 150 ms and 400 ms), driven by the dialogue timing already in the EDL.
- R6. **Silence cue:** a `silence` cue forces every music, sfx and ambience cue to zero for its span with short fades (default 80 ms); dialogue is unaffected.
- R7. **Stale and versions:** changing a cue, its prompt, or its audio file marks only that cue's take stale and the assembly stale; nothing regenerates automatically; the reel keeps its versioned exports (`v001`, `v002`).
- R8. **Cues screen:** a Sound screen (after Shots, before Assembly) lists cues on a timeline per scene, lets the owner add, edit, delete, reorder cues, play each generated take, re-take, pick a take, upload a file, and preview the full mix. It shows each cue's source, duration and model licence.
- R9. **Seeding from a screenplay:** the structuring step may propose cues from music and sound directions in the storyline text (for example "TRACK 2 kicks in", "gong slam", "complete silence"); proposed cues are marked `suggested` and never generated until approved.
- R10. **Credits and licence:** every generated or uploaded cue appears in `credits.json` with model, version and licence (uploads record the file name and an owner-supplied licence note); the export licence check lists non-commercial models and files.
- R11. **Mock backend:** everything runs on the mock backend in tests and CI; the mock returns deterministic tones of the requested length.
- R12. **Measurement spike (before the model choice and defaults are fixed):** a script in `tools/` generates, on the reference Mac, each of the owner's three music descriptions (shehnai and dholak festive; tabla and brass tension; sarangi and flute melody), each screenplay effect (drum roll, gong slam, ceramic crash and splash, packaging crinkle, crunch), and a wedding ambience, at 3 durations each, with each candidate model. It writes a table of generation time, peak memory, loudness, duration accuracy and a note per file, and the owner listens and records a verdict per file in `docs/audio-levers.md`. Models that fail the licence or Mac requirement are dropped before listening.

## Acceptance criteria
- AC-1: A story with an `audio` list validates; each invalid case in R1 is rejected with a message naming the cue and the problem; an existing story with only the old `music` block still loads.
- AC-2: Generating a music cue and an sfx cue on the mock backend produces takes of the requested length (within 50 ms), recorded with prompt, duration, seed and model; a second take is a new version and the first is kept.
- AC-3: Uploading a non-audio file as a cue file is rejected by content check; a valid clip shorter than the cue is looped, and longer is trimmed, to the exact cue length.
- AC-4: The exported reel contains the music, sfx and ambience at the resolved times: for a test story with known tones, the measured level in each cue's window is above the level just outside it, and each cue's start is within 50 ms of its resolved time.
- AC-5: With `duck: true`, music level during a dialogue line is lower than before and after it by the configured amount within 1.5 dB, with the attack and release applied; with `duck: false` it is unchanged.
- AC-6: In a `silence` cue's span, music, sfx and ambience measure below -60 dBFS (after fades) while dialogue still plays; outside the span they are audible.
- AC-7: Editing a cue's prompt marks only that cue's take and the assembly stale and starts no job; unchanged cues are not stale; the earlier reel version still exists.
- AC-8: The Sound screen lists cues in order with source, duration and licence, and add, edit, delete, play, re-take and upload work (vitest, mock backend).
- AC-9: Suggested cues from the structuring step are marked suggested and no generation job starts until a cue is approved.
- AC-10: `credits.json` lists every cue with model, version and licence; a non-commercial model or an upload with no licence note triggers the export licence check.
- AC-11: The full path (cues, generation, mix, export) completes on the mock backend with no outbound network connection.
- AC-12: Existing frozen M1 to M6b tests pass unchanged.
- AC-13: The spike has been run on the reference Mac and its table and the owner's verdicts are in `docs/audio-levers.md`; the chosen model per cue kind and the default prompts are recorded there. Manual.
- AC-14: Manual check on the reference Mac, recorded in `docs/manual-checks.md`: the owner re-exports the Gujiya reel with the three music tracks, the effects, the silence on the tasting and the ambience, listens, and records whether the mix is acceptable (levels, ducking, silence).

## Out of scope
- Screenplay import and the product-image composite (planned next).
- Voice changes (the owner's voice comments are a separate item).
- Stem separation, music editing tools, beat-matching to video cuts.
- Cloud music or sound services.

## The Gujiya cue list (reference case for tests and the manual check)
1. Music, shehnai and dholak festive, scenes s1 to s2, soft, building then cutting to a low drum roll at s2.
2. Sfx, gong slam, at the end of s3 (after "मज़ा नहीं आया!").
3. Sfx, plate clatter, s4; ambience, wedding chatter, whole reel, low.
4. Music, tabla and brass tension, from s6 to s9, ducked under speech, crescendo then abrupt stop at the end of s9.
5. Sfx, ceramic crash and splash, s7.
6. Music, calm solo violin stinger, s10.
7. Sfx, packaging crinkle, s12.
8. Sfx, loud crisp crunch, s14; silence cue over s14 for all music and ambience.
9. Music, sarangi and flute melody sweeping in at s15; shehnai swelling back at s16.
10. Music, dhol celebratory beat on the s16 line; the closing shot s17 keeps it.

## Open questions
- Whether the chosen music model can reach the three tracks' character; the spike (R12) decides, and if none can, fall back to the owner's own files for music and keep generation for effects only.
