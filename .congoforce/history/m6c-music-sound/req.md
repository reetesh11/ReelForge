---
class: feature
size: large
title: Add music, sound effects, ambience and silence cues to the reel mix
---
# Requirements — Add music, sound effects, ambience and silence cues to the reel mix

## Problem
The first full reel (Gujiya, 40.7 s) was judged only "okay" because it has no background music, sound effects, ambience or designed silence. Today `build_mix_graph` (`src/reelforge/assembly/filtergraph.py`) mixes dialogue only, `story.music` (`Music` in `story/schema.py`) is a free-text placeholder, and the EDL (`assembly/edl.py`, `EdlMusic`) has unused music slots. The owner needs a scene-tied cue list that can be generated locally or taken from their own files, mixed with ducking and silence, and licence-tracked for commercial use.

## Requirements
- R1. When a story has an ordered `audio` list, the system shall validate each cue (`id`, `kind` in music/sfx/ambience/silence, `start` as scene id plus offset or `scene_start`/`scene_end`, `end` or `duration`, `prompt`, `source` generate/file, optional `gain_db`, `fade_in_s`, `fade_out_s`, music-only `duck`).
- R2. If a cue has an unknown scene, negative time, end before start or unknown kind, then the system shall reject it with a message naming the cue and the problem.
- R3. While `audio` is present, the system shall ignore the old `music` block; while only `music` exists, the story shall still load.
- R4. When a `generate` cue is generated, the system shall create a job that produces audio of exactly the cue length from its prompt, store it as a versioned take (prompt, duration, seed, model recorded), and keep earlier takes. Music longer than the model limit is extended or looped with a crossfade.
- R5. When a cue has `source: file`, the system shall accept an uploaded clip checked by content and size (as voice reference clips are), and trim or loop it to the cue length.
- R6. When the EDL is built, the system shall carry each cue with absolute start and end, gain and fades, and the filter graph shall mix dialogue, music, sfx and ambience with per-cue fades, as an ffmpeg argument-list pipeline with no shell.
- R7. While dialogue is speaking and a music cue has `duck: true`, the system shall lower that music by the ducking amount (default 9 dB, editable per project) with attack 150 ms and release 400 ms, driven by EDL dialogue timing.
- R8. While a `silence` cue spans a time range, the system shall force all music, sfx and ambience to zero there with short fades (default 80 ms) and leave dialogue unaffected.
- R9. When a cue, its prompt or its audio file changes, the system shall mark only that cue's take and the assembly stale, start no job, and keep earlier reel exports (`v001`, `v002`).
- R10. The system shall provide a Sound screen (after Shots, before Assembly) that lists cues on a per-scene timeline with source, duration and model licence, and supports add, edit, delete, reorder, play a take, re-take, pick a take, upload a file and preview the full mix.
- R11. When the structuring step finds music or sound directions in the storyline text, the system shall propose cues marked `suggested` and shall not generate any until approved.
- R12. When a cue is generated or uploaded, the system shall record it in `credits.json` with model, version and licence (uploads: file name and owner-supplied licence note), and the export licence check shall list non-commercial models and uploads without a licence note.
- R13. The system shall allow only commercially-friendly licences (MIT, Apache-2.0 or similar) for audio models in `models.toml`; model IDs appear only there and in adapters.
- R14. The system shall run all of this on the mock backend (deterministic tones of the requested length) in tests and CI, with no outbound network calls at render time, and keep final loudness at about -14 LUFS via the existing two-pass loudnorm.
- R15. Before the model choice and defaults are fixed, a script in `tools/` shall generate on the reference Mac the three music descriptions, the screenplay effects and a wedding ambience at 3 durations each per candidate model, and write a table of generation time, peak memory, loudness, duration accuracy and a note per file.

## Acceptance criteria
- AC-1: A story with an `audio` list validates; unknown scene, negative time, end before start and unknown kind are each rejected with a message naming the cue and the problem; a story with only the old `music` block still loads.
- AC-2: Generating a music cue and an sfx cue on the mock backend yields takes within 50 ms of the requested length, recorded with prompt, duration, seed and model; a second take is a new version and the first is kept.
- AC-3: Uploading a non-audio file as a cue file is rejected by content check; a valid clip shorter than the cue is looped and a longer one trimmed to the exact cue length.
- AC-4: In an exported test reel with known tones, the level in each music, sfx and ambience cue's window is above the level just outside it, and each cue starts within 50 ms of its resolved time.
- AC-5: With `duck: true`, music level during a dialogue line is lower than before and after it by the configured amount within 1.5 dB, with attack and release applied; with `duck: false` it is unchanged.
- AC-6: In a `silence` cue's span, music, sfx and ambience measure below -60 dBFS after fades while dialogue still plays; outside the span they are audible.
- AC-7: Editing a cue's prompt marks only that cue's take and the assembly stale and starts no job; unchanged cues are not stale; the earlier reel version still exists.
- AC-8: The Sound screen lists cues in order with source, duration and licence, and add, edit, delete, play, re-take and upload work (vitest, mock backend).
- AC-9: Suggested cues from the structuring step are marked `suggested`, and no generation job starts until a cue is approved.
- AC-10: `credits.json` lists every cue with model, version and licence; a non-commercial model, or an upload with no licence note, triggers the export licence check.
- AC-11: The full path (cues, generation, mix, export) completes on the mock backend with no outbound network connection.
- AC-12: Existing frozen M1 to M6b tests pass unchanged.
- AC-13: (Manual) The spike has been run on the reference Mac; its table, the owner's per-file verdicts, the chosen model per cue kind and the default prompts are in `docs/audio-levers.md`. Models failing licence or Mac support are dropped before listening.
- AC-14: (Manual) The owner re-exports the Gujiya reel with the ten reference cues (three music tracks, effects, silence over s14, ambience), listens, and records in `docs/manual-checks.md` whether levels, ducking and silence are acceptable.

## Out of scope
- Screenplay import and product-image compositing (planned next).
- Voice changes.
- Stem separation, music editing tools, beat-matching to cuts.
- Cloud music or sound services.
- M7 hardening.

## Assumptions
- The spike (R15) runs first; model IDs, defaults and the real adapters follow its result. Mock-backed work does not depend on it.
- Frozen M1 API shapes are kept: new fields on existing responses are omitted when empty.
- Ducking and silence defaults are stored per project; the 150 ms, 400 ms and 80 ms values are defaults only.
- Candidate models (ACE-Step 1.5, MOSS-SoundEffect v2.0) have licence and Mac support verified at time of use, not from memory.

## Suggested split
1. **Cue schema and data model (m6c-1):** R1-R3, R9 and stale handling; `audio` list, validation, staleness, and mock cue generation (R4, R5 with R14 mock). AC-1, 2, 3, 7, 11 (partly).
2. **Mix in EDL and filter graph (m6c-2):** R6-R8: EDL cues, per-cue fades, ducking, silence. AC-4, 5, 6.
3. **Sound screen and seeding (m6c-3):** R10, R11. AC-8, 9.
4. **Credits, licence check, real adapters (m6c-4):** R12, R13, models.toml entries and adapters for the chosen models; AC-10, 12.
5. **Measurement spike (m6c-0, do first):** R15, AC-13; then AC-14 after the others land.

## Open questions
- Whether the chosen music model can reach the three tracks' character; the spike decides, and if none can, music falls back to the owner's own files and generation is kept for effects only. Confirm that fallback is acceptable.
- Should the split above be adopted (spike first, then four slices), or should the owner prefer another order?
