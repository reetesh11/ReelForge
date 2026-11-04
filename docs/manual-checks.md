# Manual checks

These checks need the reference Mac and the real tools. The reviewer records pass or fail
and the date next to each item. Automated tests run on the mock backend only.

## M3 Cast (AC-13): real Draw Things on the reference Mac

Setup: Draw Things is installed, its HTTP API server is on, port 7860, and the pinned image
model from `models.toml` is loaded. Run `reelforge up --backend real`.

Image memory: an image job waits until `image_mem_gb` GB are free (default 6.0). Set it with
`image_mem_gb = 6.0` under `[limits]` in config.toml, the `REELFORGE_IMAGE_MEM_GB` environment
variable, or `--image-mem-gb` on `reelforge up` / `reelforge doctor`. If memory stays short the job
fails with "Only X GB free, job needs Y GB. Close other apps, or lower image_mem_gb in
config.toml."; close other apps or lower the value, then click Retry. Restart `reelforge up`
after changing it.

Voice memory: a voice job waits until `voice_mem_gb` GB are free (default 4.0). Set it with
`voice_mem_gb = 4.0` under `[limits]` in config.toml, the `REELFORGE_VOICE_MEM_GB` environment
variable, or `--voice-mem-gb` on `reelforge up` / `reelforge doctor`. The voice model (OmniVoice
by default, Kokoro as the fallback) is set with `voice_model` under `[runtime]`,
`REELFORGE_VOICE_MODEL`, `--voice-model`, or the Settings page.

| # | Step | Expect | Result |
| --- | --- | --- | --- |
| 1 | `reelforge doctor` | The `draw_things` check passes and names no missing model. | |
| 2 | Open Settings and status | The amber "Image model licence" row is expected with the default Kontext model (non-commercial) and shows the warning. | |
| 3 | Create a project, approve a story with two characters | Stage is `STORY_APPROVED`; the Cast section appears. | |
| 4 | Click "Generate candidates" for the first character | Text reads "Generating image n of 4 - s s elapsed"; four portrait (9:16) images appear. Expect about 1 minute per image at 20 steps; images must be sharp. | |
| 5 | Check each image visually | Front-facing, plain background, matches the bible line. | |
| 6 | Click "Regenerate 4 more" | Four more images with new seeds are appended. | |
| 7 | Select an image, type a small change, click "Refine selected (img2img)" | One new image appears, based on the selected one. | |
| 8 | Generate again and click "Cancel" after image 2 | The text reads "Stopped after 2 of 4 images"; the two images stay. | |
| 9 | Quit Draw Things and click "Retry" | The panel reads "Draw Things isn't reachable on port 7860" with the four setup steps. | |
| 10 | Start Draw Things again and click "Retry" | The panel disappears. | |
| 11 | Approve one image per character | The licence warning is expected and an "Approve anyway" confirmation dialog appears; confirming it works. The stage becomes `CAST_APPROVED`. | |
| 12 | Open Library | Both characters are listed with their master images. | |
| 13 | New project, "Use from library" | The master image is copied without any generation. | |
| 14 | With about 8 GB available, generate candidates; then restart with `REELFORGE_IMAGE_MEM_GB=20` and generate again | First run renders 4 images. Second run fails with "Only X GB free, job needs 20.0 GB. Close other apps, or lower image_mem_gb in config.toml."; Retry is offered. | |

## M4 Voice (AC-13): real OmniVoice and Kokoro on the reference Mac

Setup: the mlx-audio uv project is arm64 (`uv python install cpython-3.12-macos-aarch64-none`), `[tools.mlx_audio] project_path`
points at it, and the models from `models.toml` (OmniVoice, Kokoro fallback) are downloaded. Run `reelforge up --backend real`.
`voice_mem_gb` (default 4.0) is the memory a voice job needs; the voice model is chosen on the Settings page or with `voice_model`.

Known limitation to record here: the exact OmniVoice call arguments for the voice description and for cloning (`ref_audio`,
`ref_text`) cannot be tested without the model; note any cloning quirk below.

| # | Step | Expect | Result |
| --- | --- | --- | --- |
| 1 | `reelforge doctor` | `mlx_audio` passes with "mlx-audio ready (selftest passed)". | |
| 2 | Open Settings | The line "Voice model: OmniVoice (mlx-community/OmniVoice-bfloat16)" shows; no licence warning for either model. | |
| 3 | In a cast row, pick the Asha preset and click Preview | A short Hindi sample plays in a female voice. Repeat with Ravi (male). | |
| 4 | Generate all lines for a five-line story | Each line sounds like clear Hindi, trimmed (no long silences), at an even level. | |
| 5 | Upload a clean 6 s reference clip with its transcript, set the voice to Cloned, make a new take | The take resembles the clip's voice. Record any limitation. | |
| 6 | Change the Voice model to Kokoro (fallback), pick a Kokoro preset, make a new take | A Hindi take is made; the cast row shows "Voice made with OmniVoice." for characters set earlier. | |
| 7 | Drag Speed to 0.8 and 1.25 and make new takes | Takes are slower and faster without pitch change. | |
| 8 | Set Pause before and Pause after to 0.5 and click Play scene | The pauses are audible. | |
| 9 | Approve every line | The stage becomes `VOICES_APPROVED`; each approved line shows "Shot length: N frames (X s)" with N = 8k + 1. | |
| 10 | Edit one approved line's text | Only that line becomes "Needs update"; the other lines stay approved. | |
| 11 | With about 3 GB available, generate lines | The job fails with "Not enough free memory for voice: need 4.0 GB, have X GB. Lower voice_mem_gb or close other apps." | |

## M5 Key frames and shots (AC-15): real Draw Things and ltx-2-mlx on the reference Mac

Setup: Draw Things is running with the pinned image model, ltx-2-mlx is installed and `[tools.ltx] project_path` in config.toml points at it
(the executable is `<project_path>/.venv/bin/ltx-2-mlx`, run directly). Run `reelforge up --backend real`. Use a project with the cast and voices
approved.

Memory: `shot_mem_gb` (default 16.0) is the memory a shot job needs; a shortfall fails with "Not enough free memory for a shot: need 16.0 GB (shot_mem_gb), have X GB".
Record the measured peak for a Draft and a Final shot here and set `shot_mem_gb` to match.

| Quality | Size | Peak memory (GB) | Render time (s) |
| --- | --- | --- | --- |
| Draft | 320x576 | | |
| Final | 448x768 | | |

Known limitation to record here: Draw Things receives only the master as `init_images`. The product pack is a second input recorded on the job
and artifact and described in the prompt, but its pixels are not sent. Note whether the real pack comes out right.

| # | Step | Expect | Result |
| --- | --- | --- | --- |
| 1 | `reelforge doctor` | The `ltx` check passes (all required options of `a2v`, `generate` and `extend` are present). | |
| 2 | Generate one key frame from a real master | The frame keeps the character's look, in the chosen framing. | |
| 3 | Generate a frame for a scene with two characters | Only the master is copied; the second character is described in the prompt. Record how close it is. | |
| 4 | Render one talking shot at Draft | A 9:16 clip with the voice take as audio; the lips follow the speech. | |
| 5 | Render one action shot at Draft | A silent 9:16 clip that moves as described. | |
| 6 | Compare the frame, talking shot and action shot of the same character | The character reads as the same one. | |
| 7 | Render a Continue shot after its previous shot | It starts from the previous shot's last frame. | |
| 8 | Run the real `LtxAdapter` once and open the job log | The log shows the `ltx-2-mlx a2v` or `generate` command with `--distilled` and `--low-ram`. | |
| 9 | Set the quality of one shot to Final and render | A larger clip; fill in the memory table above. | |
| 10 | With about 8 GB available, render a shot | The job fails with "Not enough free memory for a shot: need 16.0 GB (shot_mem_gb), have X GB". | |
| 11 | Close other apps, render a Final shot and quit other apps' memory use until it is killed | The card reads "Killed, likely out of memory." with "Retry at Draft size". | |
| 12 | Click Render all and watch the queue | The panel shows the shot count, minutes and "keep the Mac plugged in"; rows can be moved, paused and cancelled. | |
| 13 | Upload an own 9:16 clip of up to 20 s | It becomes a new take and its last frame is cut. | |

Reviewer: ________  Date: ________

## M6 Assembly (2026-11-04)

Run on the reference Mac with the Grumpy Uncle project, all shots approved. The reference Mac now uses ffmpeg-full (`brew unlink ffmpeg; brew install ffmpeg-full; brew link --force ffmpeg-full`), which has the `subtitles`, `ass` and `drawtext` filters, so real caption burn-in runs there. The plain Homebrew ffmpeg has no libass: on it the mock backend skips burn-in and the real backend refuses to export.

| # | Step | Expect | Result |
| --- | --- | --- | --- |
| 1 | `ffmpeg -filters \| grep -E 'subtitles\|ass\|drawtext'` | `subtitles`, `ass` and `drawtext` lines are listed (ffmpeg-full). | |
| 2 | Open Assembly from Shots ("Continue to assembly") | The EDL is built and a preview appears and plays in the phone-shaped player. | |
| 3 | Step with Previous frame / Next frame and the arrow keys | The picture moves by exactly one frame; the safe-zone overlay toggles. | |
| 4 | Read the captions on the preview (real alignment with Whisper) | Words highlight in time with the voice; no "Word timing unavailable" notes. | |
| 5 | Set the caption style to Hindi Devanagari on a Hindi line | The line is drawn in the Devanagari font (Kohinoor Devanagari by default) with no missing glyphs. | |
| 6 | Move a shot, trim another, add a crossfade, nudge a dialogue clip | After about 1 s a new preview builds; dialogue stays in sync with its shot. | |
| 7 | Edit a caption's text | The preview shows the new text; no new voice take appears. | |
| 8 | Export final | A licence check appears for non-commercial models; after "Export anyway" the progress shows ten steps and "Exported reel v1". | |
| 9 | Play the exported reel in the app and in QuickTime | 1080x1920, 24 fps, captions burned in, loudness around -14 LUFS, dialogue in sync. | |
| 9a | Extract and look at a burned caption frame (e.g. `ffmpeg -ss 2 -i final.mp4 -frames:v 1 frame.png`), once for a Latin line and once for a Devanagari line | The caption text is visible inside the safe zone, correctly shaped, with no missing glyphs (Latin and Devanagari). | |
| 10 | Edit and export again | "Reel v2" appears; "Reel v1" still opens and plays unchanged. | |

Reviewer: ________  Date: ________


## M6b Voice emotion, age and speed (2026-11-05)

Run on the reference Mac with the real OmniVoice model and the Grumpy Uncle project (cloned uncle voice). Run `tools/voice_sweep.py` first (see `docs/voice-levers.md`, "How to run the sweep"), paste the results into the Status column and edit `src/reelforge/voice/emotions.toml` until the mapping sounds right. Then regenerate the lines below. The take must also show in the job log: `duration_s` is passed for OmniVoice rows (`duration_requested_s` on the progress line) and `generate(..., duration_s=...)` is accepted by the installed model.

| # | Step | Expect | Result |
| --- | --- | --- | --- |
| 1 | Set one line to speed 0.8, make a take, then set 1.25 and make another | The 0.8 take is audibly slower and about 1.25 times as long; the 1.25 take is faster and about 0.8 times as long. Speech stays natural. | |
| 2 | Set the uncle's age to 67 and regenerate his lines | The take records `age_band` elderly; note whether the cloned voice audibly changes (the age is always sent). | |
| 3 | Pick Sad on a line and make a take | Slower, lower, quieter, with a sigh; "How this will sound" lists the mapping values. | |
| 4 | Do the same for Happy, Fear and Anger | Each is audibly different from neutral and from the others; the delivery is acceptable. Record anything that sounds artificial (large pitch shifts). | |
| 5 | Write `Tum kahan ho? <sad>Mujhe akela chhod diya.</sad>` and make a take | Two phrases joined with a short silence; the seam is not jarring. The screen text and captions show no tags. | |
| 6 | Edit `emotions.toml` (for example make sad slower) and reopen the voice board | The sad take shows "Needs update"; the next take uses the new values and the old take keeps the old ones. | |
| 7 | Use a sad take as the Sad reference, then make a new sad take | The new take's reference is the Sad clip (see "How this will sound": Sad reference clip) and the voice is closer to the sad delivery. | |
| 8 | Switch to Kokoro and pick Sad | "Emotion is not applied for this voice." appears and the take is plain; the age shows an Experimental badge. | |
| 9 | Run `reelforge doctor` on a machine with plain ffmpeg | Pitch and tempo changes fail with the "Install ffmpeg-full" message instead of being skipped. | |

Reviewer: ________  Date: ________
