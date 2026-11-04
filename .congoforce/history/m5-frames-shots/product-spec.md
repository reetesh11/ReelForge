# Product spec: Key frames and shots (M5)

## User-facing behaviour

M5 adds two screens to the project page, after Voices: **Key frames** (Stage 4) and **Shots** (Stage 5). Both follow the layout already used by the Voices board (`web/src/voice/VoiceBoard.tsx`, `LineCard.tsx`): a header with bulk actions and a count, a job status line with Cancel, a list of one card per scene (`role="group"`, `aria-label="Scene <id>"`), and a footer button that unlocks the next stage. Badge style is the existing one (`badge`, `badge amber`, `badge green`). The stage stepper already has "Key frames" and "Shots" entries and the stages `FRAMES_APPROVED` and `SHOTS_APPROVED`.

The Voices footer button "Continue to key frames" becomes live (it is already enabled at `VOICES_APPROVED`) and opens the Key frames screen. Key frames and Shots remain locked until the previous stage is approved, as the stepper already does.

### Key frames screen

Header actions:
- "Generate all frames": queues one job per scene that has no active frame, in story order. Progress is per frame: "Generating frame 2 of 5 - 40 s elapsed", with Cancel.
- "Regenerate stale items": shown only when at least one frame is stale (see Staleness).
- Count: "N of M frames approved".
- Footer button "Continue to shots", disabled until stage is `FRAMES_APPROVED`.

Frame card (one per scene), top to bottom:
- Header: scene id, character name(s), framing label (Wide, Medium, Closeup), take count ("2 takes"), state badge.
- State badges: "No frame yet", "Queued", "Rendering", "Ready", "Approved", "Needs update" (amber), "Continue from previous" (neutral).
- The 9:16 image of the active take.
- Framing selector (Wide / Medium / Closeup). Default is the scene's `framing`; for a dialogue scene with no explicit framing it is Closeup. Changing it rewrites the prompt and marks the frame as needing regeneration only for this scene.
- Editable frame prompt (textarea), written by the LLM. It always contains the character's look text verbatim. Buttons "Save prompt" and "Save and regenerate".
- Takes selector ("Take 2 - Active"), all takes kept, exactly one active.
- Buttons: "Generate" (when no take), "Regenerate" (new seed, same prompt), "Approve", "Upload replacement" (file input, images only), "Continue from previous" (toggle).
- Notes shown when relevant:
  - Two characters in the scene: "Built from <master character>'s master. <Other character> is described in the prompt, not copied. Use Upload replacement if the second character looks wrong."
  - `product_in_shot` on and asset usable: "Product pack included" (neutral note).
  - `product_in_shot` on and asset missing: amber note "Product image missing"; the Generate button still works.
  - "Continue from previous" while the previous scene's shot has no extracted last frame: the card shows "Waiting for the previous shot to be rendered" and its state stays "Continue from previous"; no job is queued.
  - No approved master for the needed character: card shows "Approve a master for <name> in Cast first" and Generate is disabled.
- Failed job: "Couldn't generate this frame." plus the reason and "Retry".

### Shots screen

Header actions:
- "Render all": opens/updates the queue panel for every shot with no active take.
- "Regenerate stale items" when any shot is stale.
- Count: "N of M shots approved".
- Footer button "Continue to assembly", disabled until stage is `SHOTS_APPROVED` (assembly itself is Phase 3; the button only reflects the gate).

Queue panel (shown while a Render all queue exists):
- Ordered list, one row per queued shot: position, scene id, type, quality, estimate ("about 1 min").
- Total line: "N shots - about N min - keep the Mac plugged in" (N min is the sum of the estimates, rounded up to whole minutes; "1 shot" in the singular).
- Controls: move up / move down per queued row, "Pause" (the running shot finishes; no new shot starts; the button becomes "Resume"), "Cancel" (cancels the queue and stops the running shot's subprocess), and per-row "Remove".
- Status line while running: "Rendering shot 2 of 5 - 31 s elapsed".

Shot card (one per scene):
- Header: scene id, shot type (Talking, Action, Continue), quality (Draft, Final), duration and frame count ("81 frames (3.38 s)", from the M4 written-back value), take count, state badge ("No shot yet", "Queued", "Rendering", "Ready", "Approved", "Needs update" amber).
- Until rendered: the active key frame. After rendering: a looping, muted-by-default-off inline video player of the active take (the talking take keeps its audio).
- Shot type selector (Talking / Action / Continue). Default: Talking when the scene has an approved voice take, Continue when `continue_from` is set, otherwise Action. A user override persists for that shot.
- Quality selector: Draft (320x576) or Final (448x768). Defaults come from settings.
- Editable motion prompt (textarea). Talking shots get an appearance-only prompt; Action and Continue get a motion prompt; each includes the character bible line. "Save prompt" and "Save and re-render".
- Buttons: "Render", "Play", "Approve", "Re-roll" (new seed, same prompt, new take), "Upload own clip" (file input, video only), "Compare takes".
- "Compare takes" opens two takes side by side, each with a looping player and a "Make active" button.
- Takes selector as on frames; all takes kept, one active.
- A shot cannot be rendered when its scene has no approved key frame: Render is disabled with "Approve the key frame first". A talking shot with no approved voice take shows "Approve the voice take first" and offers switching the type to Action.
- A Continue shot whose previous shot has no last frame yet shows "Waiting for the previous shot" and cannot be started.
- Out-of-memory failure: "Killed, likely out of memory." with a button "Retry at Draft size" (shown when the shot was Final or otherwise larger than Draft; when already Draft the message shows without the retry button, plus the hint to close other apps).
- Other failure: "Couldn't render this shot." plus reason and "Retry".

### Doctor and Settings

- The `ltx` check in doctor (key unchanged: `ltx`) now also runs `a2v --help`, `generate --help` and `extend --help` of `<ltx_path>/.venv/bin/ltx-2-mlx` and compares against the required flag lists below. On failure, the check message reads: "ltx-2-mlx is missing required options: a2v: --frame-rate; extend: --image" (subcommand then its missing flags, subcommands separated by semicolons). While it fails, Render and Render all are disabled with "Video engine check failed - see Settings & status".
- Required flags (from answers.md):
  - `a2v`: --prompt --output --audio --image --frame-rate --frames --width --height --model --seed --distilled --low-ram
  - `generate`: --prompt --output --image --frame-rate --frames --width --height --model --seed --distilled --low-ram --no-audio
  - `extend`: --prompt --output --video --extend-frames --distilled --low-ram --image
- New setting `shot_mem_gb` (default 16.0) appears wherever `image_mem_gb` appears (config file `[limits]`, environment, validation). Draft and Final sizes are settings with the defaults 320x576 and 448x768.

### Staleness and gates

- Changing a scene's action marks only that scene's frame and shot "Needs update".
- A new active voice take for a scene marks only that scene's Talking shot "Needs update".
- Changing (re-approving a different take of, or replacing) an approved frame marks that scene's shot "Needs update", and re-opens only that frame (and its shot); other scenes are untouched.
- Stale items show the amber "Needs update" badge. "Regenerate stale items" queues only stale items, one click. Nothing regenerates without a click.
- `FRAMES_APPROVED` is reached when every scene has an approved frame or is "Continue from previous". `SHOTS_APPROVED` is reached when every shot has an approved active take. Un-approving or invalidating any item drops the stage back to the previous approved stage.

### Mock backend

On the `mock` backend, frame jobs return a deterministic PNG (9:16) and shot jobs a deterministic MP4 (ffmpeg, requested size and frame count, the given audio for Talking). No network is used. Behaviour and copy above are identical.

## Acceptance criteria

- AC-1: Generating a frame for a scene runs an img2img edit whose input artifacts are the approved master image of the speaker (else the first named character). The frame prompt contains that character's look text verbatim (exact string, unmodified) and the framing phrase for the card's framing. The prompt is never sent without the master image. The job record lists the master as an input.
- AC-2: With `product_in_shot` on and `product.asset` an existing image under the data root, the frame job also lists the pack image as an input, and the prompt asks for the real pack in hand or on the table. With the asset missing or not a file under the data root, the card shows "Product image missing", the job runs with only the master, the prompt omits the pack request, and the frame is produced normally.
- AC-3: A Talking shot job lists the active key frame (as the start image) and the active approved voice take (as audio) as inputs, and its frame count equals the scene's written-back value (8k+1, for example 81). An Action shot job lists the key frame only and has no audio input and no audio argument; the resulting clip is silent.
- AC-4: With 5 rendered shots, "Re-roll" on one shot adds a take (take number +1, new seed, same prompt) to that shot only. The other four shots keep their active takes, take counts and cache entries unchanged. The previous take of the re-rolled shot is kept and selectable.
- AC-5: `doctor` reports the `ltx` check as failed, with the message format given above, when any required flag from the three lists is absent from the parsed `--help` output of its subcommand, and passes when all are present. The failure happens in `doctor` and at startup, not in the middle of a render; no shot job starts while the check is failing. Tested with a fake `ltx-2-mlx` script whose `--help` output is configurable. The check key stays `ltx`.
- AC-6: A shot subprocess that exits with code 137 or -9 produces the job failure message "Killed, likely out of memory." The shot card shows that message and a "Retry at Draft size" button that re-renders the same shot at 320x576 as a new take; the shot's saved quality becomes Draft on retry.
- AC-7: A shot job starting with less available memory than `shot_mem_gb` fails with a message naming `shot_mem_gb` (for example "Not enough free memory for a shot: need 16.0 GB (shot_mem_gb), have 9.2 GB"; the wording follows the existing `image_mem_gb` message). With enough memory it runs. Only one heavy job (frame or shot) holds the GPU lease at a time; Ollama is unloaded before the job starts. `shot_mem_gb` has the same precedence (environment over config file over default) and the same validation (rejects non-numeric and non-positive values) as `image_mem_gb`. Frame jobs use `image_mem_gb`.
- AC-8: After a shot finishes, its last frame is extracted as a `last_frame` artifact (PNG) linked to that take. A Continue shot uses the previous scene's active-take last frame as its start image (via `extend` or `generate --image`, whichever the parsed `--help` supports). If the previous shot has no last frame, the Continue shot does not start and the card says "Waiting for the previous shot".
- AC-9: The queue estimate per shot is the mean of recorded render times for shots of the same type and size when at least one exists, otherwise a built-in default per type and size. The total line reads "N shots - about N min - keep the Mac plugged in". Queued rows can be moved up or down; "Pause" stops new shots from starting after the running one; "Resume" continues; "Cancel" removes all queued rows and stops the running shot's subprocess (the job ends as cancelled, no take is added).
- AC-10: Changing one scene's action marks only that scene's frame and shot "Needs update". A new active voice take marks only that scene's Talking shot "Needs update" (its frame is not stale). Other scenes show no stale badge. No job is created until the user clicks "Regenerate stale items" or a card's own button.
- AC-11: `FRAMES_APPROVED` is reached only when every scene has an approved frame or is set to "Continue from previous". `SHOTS_APPROVED` is reached only when every shot has an approved active take. Editing and re-approving, or replacing, an approved frame re-opens (state "Needs update") only that frame and that scene's shot; all other scenes keep their approvals. "Continue to shots" and "Continue to assembly" enable exactly at these gates.
- AC-12: An uploaded replacement frame is accepted only if its content is an image (decoded by content, not by extension) and within the size limit; an uploaded clip only if ffprobe finds a video stream, the aspect ratio is 9:16, and the length is at most 20 seconds. Accepted files are stored under a generated name (the original filename is not used on disk) and become a new active take. A non-image or a non-video is rejected with a visible error ("That file is not an image." / "That file is not a video."). A clip that is not 9:16 is rejected with "The clip must be vertical 9:16." and one over the limit with "The clip must be 20 seconds or shorter." An oversize file is rejected with a size message naming the limit.
- AC-13: The steps of AC-1 to AC-4 run end to end on the `mock` backend with no outbound network connection (mock PNG and ffmpeg MP4 via the same subprocess path as the real adapter where practical).
- AC-14: Existing M1 to M4 tests pass unchanged. No new keys are added to existing responses (such as `GET /jobs`) unless a job has a `result`. The `ltx` doctor check keeps its key and its place in the check list.
- AC-15: A manual check on the reference Mac is recorded in `docs/manual-checks.md`: one real key frame from a real master; one real Talking shot and one real Action shot at Draft size; the characters read as the same across shots; the real `LtxAdapter` has been run once before shipping.

Added by implication of req.md:
- AC-16: Approving a frame or shot that is stale is not possible; the Approve button is disabled while the state is "Needs update" until the item is regenerated (same rule as the Voices board).
- AC-17: Generate-all frames queues one job per frame in story order and the screen shows per-frame progress; Cancel stops the running frame and removes the rest.
- AC-18: "Continue from previous" on a frame card uses the previous shot's extracted last frame as that scene's frame once it exists, and counts as approved for `FRAMES_APPROVED`.

## Edge cases and errors

- No approved master for the scene's character: Generate disabled with "Approve a master for <name> in Cast first".
- Scene with no characters: the card says "No character in this scene" and relies on upload or text-only is not allowed; user can upload a replacement or use "Continue from previous". (See open questions.)
- LLM unavailable when writing a prompt: card shows "Couldn't write the prompt" with a Retry; the user may type a prompt by hand.
- Draw Things not running (real backend): frame job fails with the adapter's reason and Retry.
- Edited prompt that no longer contains the character's look text: allowed (the user chose), but the card shows a note "The character description was removed from the prompt."
- Upload: wrong type, empty file, oversize, not 9:16, over 20 s, corrupt video: rejected as in AC-12; no take is created.
- Slow render: elapsed seconds shown; a running job can be cancelled; the subprocess has a timeout and a timeout is reported as "Timed out".
- Cancelled or failed jobs never add a take and never change the active take.
- App restart during a queue: queued rows return as queued; a shot that was running is shown as failed with "Interrupted" and Retry.
- Duplicate click on Render for a queued or running shot is ignored.
- Reordering a row that has already started is not possible (controls disabled).
- Changing quality or type on an approved shot makes it "Needs update" until re-rendered.
- Scene deleted or changed in Story after frames exist: handled by staleness; orphan items are not shown.

## Out of scope

- Transition (start and end frame) shots, guided draft-then-final workflow, trim in/out, overnight queue (v1.1).
- Manual product overlay canvas, visual QA, brand-kit screens (v1.1).
- Assembly, captions, export (Phase 3); the "Continue to assembly" button only reflects the gate.
- Human-like characters (lip sync verified on cartoon only).
- Relying on a second `init_images` entry for two-character scenes.

## Open questions

- Upload size limits: what is the maximum file size for an uploaded replacement frame and for an uploaded clip? (Cast uploads have a limit; the spec assumes frames reuse it and proposes a clip limit be set by tech-spec.)
- Scenes with no characters at all: should frame generation be blocked (spec assumes yes, upload or "Continue from previous" only) or fall back to text-only generation, which R1 forbids?
- Should "Retry at Draft size" overwrite the shot's saved quality to Draft (spec assumes yes) or only apply to that retry?
- Pausing the queue: should Pause also pause the currently running shot (not possible with a subprocess) or let it finish (spec assumes it finishes)?
- Does "Continue to assembly" exist as a disabled placeholder before Phase 3 (spec assumes yes)?
- Built-in default estimates are an implementation choice per req.md; confirm showing "about N min" rounding up to whole minutes is acceptable.
