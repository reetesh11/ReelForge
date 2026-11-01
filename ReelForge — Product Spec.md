# ReelForge — Product Spec

Nov 1, 2026 · @Reetesh

## Product overview

ReelForge is a local Mac app where you write a short story, approve a cast, approve the voices, approve the shots, and get a finished, captioned 9:16 reel — with no subscriptions and nothing leaving your laptop.

**Who it is for**

- **Primary:** a small-brand owner (BihariPakwan) who wants frequent, character-driven Instagram Reels with the product woven into the story.
- **Secondary:** any creator on an Apple Silicon Mac who wants local, repeatable story videos with recurring characters.

**The promise**

1. **Recurring characters.** Build a cast once (a talking tomato, a moustached potato) and reuse them in every reel.
2. **Human in control.** Nothing expensive happens without an approval; anything can be re-done on its own.
3. **Free to run.** Open models on your own Mac; the only cost is time.

**The flow in one line:** Story → `story.yaml` → Cast ✓ → Key frames ✓ → Voices ✓ → Shots ✓ → Assembled reel → Export. Each ✓ is a gate the user approves.

## Core concepts

The user sees nine nouns; the cast library outlives any single project, everything else belongs to one project.

| Concept | What it is | Lives in | Example |
| --- | --- | --- | --- |
| Project | One reel being made, with its own folder and history | Projects list | “Wedding thekua reel #3” |
| Story | The structured script (`story.yaml`): characters, scenes, lines | Project | 5 scenes, 2 characters |
| Cast library | Reusable approved characters, shared across projects | Global library | Tomato, Potato |
| Character | A master image + look text + voice + metadata | Cast library | Tomato in gold sherwani |
| Voice | A preset, designed or cloned voice attached to a character | Character | “Cheeky tomato” voice clip |
| Scene | One beat of the story: setting, action, optional line | Story | Potato bursts into mandap |
| Shot | The rendered video for a scene (usually one shot per scene) | Project | 3 s, 320×576, 24 fps |
| Take | One attempt at an image, line or shot; many takes, one active | Shot / line / frame | Take 3 of line 2 |
| Reel | The assembled, captioned, exportable final video, versioned | Project | v2, 13.4 s |

A **character in the library is never edited in place by a project**. If a project changes a character’s outfit, it creates a project-level variant (“Tomato — wedding outfit”) linked to the original, so older reels stay reproducible.

## User journey

The user moves through six stages in a fixed order, and each stage unlocks only after the previous one is approved.

&#91;embedded content: user journey · 6 stages, 5 approval gates\]

Voices come before any image-to-video work because line lengths set shot lengths. Going back is always allowed: an upstream edit marks only the dependent items stale, so one change never forces a full re-render.

## Stage 1 — Story input

The user writes the story the way they think about it; ReelForge turns it into `story.yaml` and shows exactly what it understood before anything is generated.

**Input screen**

- One large “Storyline” box (required), plus optional collapsible boxes: Characters, Backgrounds/locations, Product placement, Dialogue, Style (e.g. “3D Pixar-style cartoon”), Language (Hindi / English / Hinglish), Target length (default 12 s).
- “Use characters from library” picker: chosen characters are inserted with their saved looks and voices, and the LLM is told not to redesign them.
- “Start from template” menu: Two-character banter, Product reveal, Festival scene, Before/after.
- Primary button: **Structure my story**.

**What “Structure my story” does**

1. The local LLM splits the story into 4–8 scenes sized to the target length, assigns speakers, and writes each character’s look in a fixed, reusable form.
2. It flags gaps as questions rather than guessing (“What is the potato wearing?”), shown inline for the user to answer or skip.
3. The result is validated against the schema; anything invalid is highlighted, never silently dropped.

**Story editor** (two synced views)

- **Form view:** cards for each character and scene; drag to reorder scenes; add/delete scenes; per-scene fields for setting, action, camera, speaker, line, duration, product-in-shot toggle.
- **YAML view:** the raw `story.yaml` with syntax highlighting and live validation errors.
- A running estimate shows total reel length from scene durations.
- **Approve story** locks the story for downstream stages; editing it later marks dependent artifacts as stale (see States).

**Edge cases**

- No dialogue given: the LLM may propose lines, clearly marked “suggested” until accepted.
- Story too long for the target: the LLM proposes cuts; the user can raise the target length up to 60 s.
- Imported `story.yaml`: skips the LLM and opens straight in the editor.

## Stage 2 — Cast

Each character gets a master image and a voice that the user approves once; approved characters go into the cast library and can be reused in any later project.

**For each character in the story, the Cast screen shows one row:**

- If the character came from the library: its saved master image and voice, marked **From library**, already approved. Options: Use as-is · Create project variant (e.g. new outfit) · Swap for a different library character.
- If the character is new: a **Generate** button that produces 4 candidates from its look text.

**Candidate grid (new characters)**

- 4 images shown side by side, 9:16, on a plain background, front-facing.
- Click to enlarge; compare two side by side.
- Actions per grid: **Approve this one** · Regenerate 4 more · Edit look text and regenerate · Refine selected (small edit, e.g. “bigger eyes”) · Upload my own image.
- Seed and prompt are kept for every candidate, so “more like this one” works.

**After approval**

- Optional: generate a 3-view character sheet (front, side, back) to improve consistency in later shots.
- The character is saved to the library with: name, aliases, look text (the “character bible line”), master image, sheet, seed, model used, created date, tags (e.g. “BihariPakwan”, “vegetables”).
- Voice selection happens here too, so the character is complete in the library (see Stage 4 for voice details).

**Reusing an old cast**

- From the Story input screen (“Use characters from library”) or from the Cast screen (“Swap for library character”).
- Library cards show the master image, a play button for the voice, the projects that used it, and tags.
- A whole saved **ensemble** (e.g. “Veggie gang: Tomato + Potato + Onion”) can be added in one click.

**Gate:** all characters approved → **Continue to voice-overs** unlocks.

## Stage 3 — Voice-overs

All dialogue is voiced and approved scene by scene before any video is rendered, because each approved line’s length decides its shot’s length and drives lip sync.

**Character voices** (set once, saved in the library)

- **Preset:** pick from the TTS model’s built-in voices, filtered by language (Hindi, English).
- **Designed:** describe it (“squeaky, cheeky, fast-talking cartoon tomato”) and audition 3 generated options.
- **Cloned:** upload or record a 5–10 s reference clip (e.g. your own voice acting the potato) and clone from it.
- **Recorded lines (fallback):** upload real recordings per line, bypassing TTS entirely.
- Each voice stores: model, voice ID or reference clip, default speed, default language.

**Voice board** (one column per scene, top to bottom)

- Each line shows: speaker avatar, line text, language, duration, waveform, play button, take count.
- **Generate all lines** renders every line in story order; progress shows per line.
- Per line: ▶ Play · ✓ Approve · ↻ New take (different seed) · ✎ Edit text and re-take · Speed slider (0.8–1.25×) · Pause before/after (0–1 s) · Emotion hint where the model supports it (e.g. excited, whisper).
- All takes are kept in a dropdown; one is marked **active**.
- **Play scene** and **Play all** stitch active takes with pauses for a quick radio-play preview.
- Lines over the scene’s duration budget are flagged with a suggestion: speed up, shorten text, or extend the scene.

**Gate:** every line has an approved active take → **Continue to key frames** unlocks. Approved durations are written back into each scene as its shot length (rounded to valid frame counts).

## Stage 4 — Key frames

Every scene gets one approved opening frame built by editing the approved character masters into the scene — this is what keeps characters identical from shot to shot.

**Storyboard grid** (one card per scene, in order)

- Card shows: scene number, setting, action, speaker, duration, and the generated frame (9:16).
- **Generate all frames** builds each frame from: character masters + scene setting + action + style, using an image-edit model, never text alone.
- Per card: ✓ Approve · ↻ Regenerate · ✎ Edit prompt · ⬆ Upload replacement · 🔗 Continue from previous shot (frame chosen later from the previous shot’s last frame, see Stage 5).
- Framing preset per card: Wide · Medium · Close-up. Dialogue scenes default to front-facing close-up for better lip sync.

**Product placement**

- Scenes with “Product in shot” on show the brand kit’s pack shots to pick from.
- Mode A — **AI placement:** the edit model places the real pack in a character’s hands or on a table; the user checks the logo is intact.
- Mode B — **Manual overlay:** drag, scale and rotate the real pack PNG onto the frame in a simple canvas; always pixel-perfect.
- The app recommends Mode B when the pack has fine text.

**Gate:** all frames approved (or marked “continue from previous”) → **Continue to shots** unlocks.

## Stage 5 — Shots

Each scene becomes a short video clip: dialogue scenes are lip-synced to their approved line, other scenes are animated from their key frame, and any single shot can be re-done without touching the rest.

**Shot board** (same card layout as the storyboard, now with video)

- Card shows the key frame until rendered, then an inline player that loops the shot.
- Shot type is set automatically and can be overridden:
  - **Talking:** key frame + the line’s audio → lip-synced shot.
  - **Action:** key frame + motion prompt → silent shot.
  - **Continue:** previous shot’s last frame → seamless continuation.
  - **Transition:** start frame + end frame → in-between motion.
- **Render all shots** queues every unrendered shot; the queue shows order, estimated time per shot, and lets the user reorder, pause or cancel.
- A clear estimate before starting: “5 shots · about 35 min · keep the Mac plugged in.”

**Per shot actions**

- ▶ Play · ✓ Approve · ↻ Re-roll (new seed, same prompt) · ✎ Edit motion prompt · 🎚 Quality: Draft (fast, small) / Final (slower, larger).
- ✂ Trim in/out points with frame-accurate scrubbing.
- Compare takes side by side and pick the active one.
- “Render draft first” mode: render all shots small and fast, approve the motion, then re-render approved shots at final quality with the same seeds.

**Overnight mode:** queue several projects’ shots and let them render unattended; results wait for approval in the morning, with a summary notification.

**Gate:** every shot has an approved active take → **Assemble reel** unlocks.

## Stage 6 — Assembly, editor and player

The final screen is a simple vertical-video editor: a phone-shaped player on the left, a four-track timeline below, and an export button — enough to fix most issues without leaving the app.

**Player**

- 9:16 player framed like a phone, with an optional Instagram UI overlay to check captions stay in the safe zone.
- Play/pause, frame step (← →), loop, playback speed, scrub, full screen, mute toggle (to check the reel works without sound).
- The same player component is used everywhere: candidate previews, shot cards, takes comparison, final reel.

**Timeline (4 tracks)**

| Track | Content | Edits allowed |
| --- | --- | --- |
| Video | Approved shots in scene order | Reorder, trim, swap take, set cut or crossfade (0–0.5 s) |
| Dialogue | Active line takes, aligned to their shots | Nudge timing, volume, swap take |
| Music & ambience | Optional bed track and sound effects | Pick from library or upload, volume, fade in/out, auto-duck under speech |
| Captions | One caption per line, from the script | Edit text, timing, position, style preset |

**Assemble**

- **Assemble reel** builds a preview at low quality in seconds; every timeline edit re-renders the preview automatically.
- Optional end card from the brand kit: logo, tagline, website (biharipakwan.in), 1.5 s.
- Caption style presets: Bold pop (word-by-word highlight), Clean subtitle, Hindi Devanagari.

**Export**

- **Export final** renders 1080×1920, 24 fps, H.264 + AAC, loudness-normalised, and saves it as a new reel version (v1, v2…).
- Export panel offers: Reveal in Finder · Copy to a chosen folder · Generate cover frame (pick any frame) · Copy suggested caption and hashtags (local LLM, editable).
- Each version keeps its full edit decision list, so any version can be reopened and changed.

## Manual edit options

Every AI output can be overridden by hand, and every stage accepts an uploaded file in place of a generated one; edits only invalidate what depends on them.

| Stage | Manual edits | Upload instead of generate | What becomes stale after an edit |
| --- | --- | --- | --- |
| Story | Form and YAML editing, reorder/add/delete scenes, edit lines | Import `story.yaml` | Depends on field: a line edit → that line’s voice + shot; a look edit → that character |
| Cast | Edit look text, refine selected image, choose seed | Own character image | Key frames and shots with that character |
| Voice | Edit text, speed, pauses, emotion, choose take | Recorded line WAV, reference clip | That scene’s shot (duration and lip sync) |
| Key frames | Edit prompt, framing, manual product overlay | Own frame image | That scene’s shot |
| Shots | Motion prompt, seed, quality, trim, choose take | Own video clip | Assembly only |
| Assembly | Order, cuts, crossfades, volumes, music, captions, end card | Music/SFX files | Nothing (final render only) |

**Staleness rules shown to the user**

- Stale items get an amber “needs update” badge and a one-click **Regenerate stale items**.
- Nothing is regenerated automatically; the user decides, because renders are slow.
- Undo/redo works across the story editor and timeline; generated takes are never deleted by undo.

## Library, projects, settings and status

Four supporting screens sit in a left sidebar alongside the active project: Projects, Cast library, Brand kit, and Settings & status.

**Projects**

- Grid of projects with cover frame, title, stage progress (e.g. “Voices 4/5 approved”), last edited, reel versions.
- New project · Duplicate (copies story and cast links, not renders) · Archive · Reveal folder in Finder.
- Search by title, character or tag.

**Cast library**

- Character cards with master image, voice play button, tags, projects used in, variants.
- Character detail: look text, sheet views, all approved images, voice settings, usage history.
- Create a character directly in the library (without a project) · Group characters into ensembles · Export/import a character as a zip.

**Brand kit**

- Logos, pack shots (transparent PNGs), fonts (incl. Devanagari), colours, end-card template, default caption style, default music.
- Multiple kits supported (one per brand).

**Settings & system status**

- **Status panel:** a row per dependency (Draw Things, ltx-2-mlx, mlx-audio, local LLM, ffmpeg) with green/amber/red state, version, port, and a “Fix” hint for anything not green.
- **Ports and hosts:** editable for the app and every service, validated on save.
- **Models:** chosen model per role (video, image, edit, TTS, LLM), quality presets, download status, license note.
- **Storage:** data folder location, disk used per project, clean caches.
- **Render defaults:** draft and final resolutions, frame rate, seed policy, overnight mode.

## story.yaml format

`story.yaml` is the single source of truth for a project’s creative intent; generated files are referenced by ID, never embedded.

```yaml
version: 1
title: "Wedding thekua rescue"
language: hinglish            # hindi | english | hinglish
style: "3D Pixar-style cartoon, warm festive lighting"
aspect: "9:16"
fps: 24
target_seconds: 12
brand_kit: biharipakwan

characters:
  tomato:
    library_id: chr_tomato_01     # set when reused from the cast library
    name: "Tamatar"
    look: "round glossy red tomato, big expressive eyes, tiny green leaf hat, gold sherwani"
    voice: { mode: designed, ref: voice_tomato_01, speed: 1.05 }
  potato:
    name: "Aloo"
    look: "chubby brown potato, bushy black moustache, pink turban, white kurta"
    voice: { mode: cloned, reference_clip: assets/voices/potato_ref.wav }

product:
  name: "Thekua box"
  asset: brand/pack_thekua_front.png

scenes:
  - id: s1
    setting: "Indian wedding mandap at night, marigold garlands, fairy lights"
    action: "Aloo bursts in through the crowd, panting"
    framing: wide
    duration: 2.0
  - id: s2
    speaker: tomato
    line: "Arre Aloo, itni der kyun?"
    action: "Tamatar crosses his arms, annoyed"
    framing: closeup
  - id: s3
    speaker: potato
    line: "Mithai ke bina shaadi? Main thekua laaya hoon!"
    action: "Aloo proudly lifts the thekua box"
    framing: closeup
    product_in_shot: true
  - id: s4
    action: "Guests rush toward the thekua box, cheering"
    framing: medium
    continue_from: s3
    duration: 2.5
  - id: s5
    action: "Both characters wink at camera, logo appears"
    framing: medium
    duration: 2.0
    end_card: true

music: { mode: library, track: festive_dhol_01, duck_under_speech: true }
captions: { style: bold_pop, script: latin }
```

**Field rules**

- `duration` is optional on dialogue scenes; the approved line length sets it (plus pauses).
- `continue_from` makes a scene start from the end of another scene’s shot instead of a fresh key frame.
- `look` text is reused verbatim in every prompt involving that character; it is the character bible line.
- Unknown fields are rejected with a clear message, so typos never pass silently.

## States, errors and notifications

Every generated item shows one of seven states, and every failure tells the user what happened and the one action that fixes it.

| State | Badge | Meaning |
| --- | --- | --- |
| Not started | Grey | Nothing generated yet |
| Queued | Grey, clock | Waiting for a free slot in the render queue |
| Rendering | Blue, progress % | Running now; shows elapsed and estimated time |
| Needs review | Purple | Generated, waiting for approval |
| Approved | Green | Active take locked for downstream use |
| Stale | Amber | An upstream edit changed its inputs |
| Failed | Red | Last attempt failed; message + Retry |

**Error messages (examples)**

| Situation | Message | Action offered |
| --- | --- | --- |
| Draw Things API off | “Draw Things isn’t reachable on port 7860.” | Open setup steps · Retry |
| Model missing | “FLUX.1 Kontext isn’t downloaded in Draw Things.” | Show how to download · Choose another model |
| Low memory before render | “Only 11 GB free — close other apps or render at draft size.” | Render draft · Wait · Render anyway |
| Render killed (out of memory) | “Shot 3 ran out of memory.” | Retry at smaller size · Retry with fewer frames |
| Line too long for scene | “Line 2 is 3.4 s; scene budget is 2.5 s.” | Speed up · Extend scene · Edit text |
| Port in use | “Port 7400 is used by another process.” | Pick next free port · Edit in Settings |

**Notifications**

- macOS notification when a long job finishes or fails while the app is in the background.
- In-app activity panel listing recent jobs with duration and result.
- Overnight summary: “12 shots rendered, 1 failed, 3 projects ready for review.”

## Release scope and success metrics

v1 ships the full six-stage flow with approvals, the cast library and the player; editing depth and convenience features follow in v1.1.

| Capability | v1 | v1.1 | Later |
| --- | --- | --- | --- |
| Story input, LLM structuring, YAML editor | ✓ |  |  |
| Cast generation, approval, library, reuse | ✓ | Character sheets, ensembles | Character LoRA training |
| Voice: presets, cloning, takes, approval | ✓ | Voice design, emotion hints |  |
| Key frames with image edits | ✓ | Manual product overlay canvas |  |
| Shots: talking, action, continue | ✓ | Transition shots, draft-then-final | Cloud GPU backend for final quality |
| Assembly: stitch, captions, music, export | ✓ | 4-track timeline editing |  |
| Built-in player | ✓ | Takes comparison view |  |
| Status panel, ports, doctor | ✓ |  |  |
| Overnight queue |  | ✓ |  |
| Suggested caption and hashtags |  | ✓ |  |
| Auto-posting to Instagram |  |  | Considered |

**Success metrics**

- Time from story to first full reel: under 2 hours on the reference Mac (most of it unattended rendering).
- Hands-on time per reel after the cast exists: under 30 minutes.
- Character consistency: user rates “same character” across shots in at least 4 of 5 reels.
- Re-roll rate: fewer than 2 re-rolls per shot on average.
- Output: at least 3 publishable reels per week for BihariPakwan.
