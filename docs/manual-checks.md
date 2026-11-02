# Manual checks

These checks need the reference Mac and the real tools. The reviewer records pass or fail
and the date next to each item. Automated tests run on the mock backend only.

## M3 Cast (AC-13): real Draw Things on the reference Mac

Setup: Draw Things is installed, its HTTP API server is on, port 7860, and the pinned image
model from `models.toml` is loaded. Run `reelforge up --backend real`.

| # | Step | Expect | Result |
| --- | --- | --- | --- |
| 1 | `reelforge doctor` | The `draw_things` check passes and names no missing model. | |
| 2 | Open Settings and status | If the image model is non-commercial, an amber "Image model licence" row shows the warning. | |
| 3 | Create a project, approve a story with two characters | Stage is `STORY_APPROVED`; the Cast section appears. | |
| 4 | Click "Generate candidates" for the first character | Text reads "Generating image n of 4 - s s elapsed"; four portrait (9:16) images appear. | |
| 5 | Check each image visually | Front-facing, plain background, matches the bible line. | |
| 6 | Click "Regenerate 4 more" | Four more images with new seeds are appended. | |
| 7 | Select an image, type a small change, click "Refine selected (img2img)" | One new image appears, based on the selected one. | |
| 8 | Generate again and click "Cancel" after image 2 | The text reads "Stopped after 2 of 4 images"; the two images stay. | |
| 9 | Quit Draw Things and click "Retry" | The panel reads "Draw Things isn't reachable on port 7860" with the four setup steps. | |
| 10 | Start Draw Things again and click "Retry" | The panel disappears. | |
| 11 | Approve one image per character | If a licence warning shows, the dialog repeats it; "Approve anyway" works. The stage becomes `CAST_APPROVED`. | |
| 12 | Open Library | Both characters are listed with their master images. | |
| 13 | New project, "Use from library" | The master image is copied without any generation. | |

Reviewer: ________  Date: ________
