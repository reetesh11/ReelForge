# Audio levers: what we can control in music, effects and ambience

Status: **pending reference-Mac run.** Fill the sections below after running the spike.

## How to run the spike

On the reference Mac, with the candidate models installed (see `[candidates.*]` in `src/reelforge/models.toml`):

```
python tools/audio_spike.py --out ~/reelforge-spikes/audio --table ~/reelforge-spikes/audio/table.md
python tools/audio_spike.py --out /tmp/audio-spike --backend mock   # tones only, no model
```

Each candidate renders the nine reference cues (three music descriptions, five screenplay effects, the wedding ambience) at three durations. Paste the table into section 1.

## 1. Measurement table

Pending reference-Mac run.

## 2. Per-file verdicts

Pending reference-Mac run. For each file record: right length, usable sound, loudness, and whether it would pass for the reel.

## 3. Chosen model per kind

Pending reference-Mac run. Music: ___. Sound effects: ___. Ambience: ___. If no model reaches the music tracks, music uses the owner's own files and generation stays for effects and ambience.

## 4. Default prompts

Pending reference-Mac run.

## 5. Candidates and what was checked

| Candidate | Licence (from `license_url`) | Mac support | Checked |
| --- | --- | --- | --- |
| ACE-Step 1.5 | Apache-2.0 | to confirm on the reference Mac | licence and Mac support not yet verified |
| MOSS-SoundEffect v2.0 | Apache-2.0 | to confirm on the reference Mac | licence and Mac support not yet verified |
