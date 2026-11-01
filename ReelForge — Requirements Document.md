# ReelForge — Requirements Document

Nov 1, 2026 · @Reetesh

## Purpose and scope

ReelForge turns a written storyline into a finished 10–15 second vertical reel, with every model and service running locally on one MacBook Pro and no paid API keys. ReelForge is the working name. The first user is BihariPakwan, which needs branded, character-driven Instagram Reels.

**Goals**

1. Convert a storyline, characters, backgrounds and dialogue into a structured story file (YAML).
2. Generate a reusable cast of consistent characters, approved by a human before use.
3. Generate per-line voice-overs, approved by a human before video work starts.
4. Generate 2–4 second shots with the cast, lip-synced where a character speaks.
5. Stitch shots, voices, music and captions into one 9:16 MP4 ready for Instagram.
6. Allow manual edits and re-rolls at every stage without redoing earlier stages.

**Non-goals for v1**

- Cloud rendering, paid APIs or remote GPUs (a later optional backend).
- Videos longer than 60 seconds or landscape-first formats.
- Auto-posting to Instagram or any social network.
- Multi-user collaboration, accounts or remote access.
- Training custom LoRAs (manual, out-of-band only).

## Hardware requirements

The reference machine is a 14-inch MacBook Pro with an Apple M5 Pro and 24 GB unified memory; 24 GB is the binding constraint, so only one heavy model may be resident at a time.

| Item | Minimum | Recommended | Why |
| --- | --- | --- | --- |
| Chip | Apple Silicon M1 Pro | M5 Pro or newer | MLX and Metal only; Intel Macs are unsupported |
| Unified memory | 24 GB | 32 GB+ | LTX-2.3 q4 with low-RAM streaming fits in about 16 GB; a full 1280×704, 5 s render needs about 30 GB |
| Free disk | 150 GB | 250 GB | Model weights (60–90 GB across LTX, image, TTS, LLM) plus per-project renders and caches |
| Disk type | Internal SSD | Internal SSD | Model block streaming reads weights from disk during generation |
| Power | Plugged in | Plugged in | Renders run 2–10 minutes each at sustained GPU load |

**Memory budget per stage (24 GB machine)**

| Stage | Resident model | Target peak memory |
| --- | --- | --- |
| Script structuring | Local LLM, 7–8B at 4-bit | ≤ 6 GB |
| Cast and key frames | Draw Things (FLUX.1 schnell / Kontext) | ≤ 14 GB |
| Voice | mlx-audio TTS model | ≤ 6 GB |
| Video | ltx-2-mlx, q4, `--low-ram` | ≤ 18 GB |
| Assembly | ffmpeg only | ≤ 2 GB |

**Operating rules**

- Stages run strictly one at a time; the app unloads or idles each model before the next stage starts.
- Heavy apps (Chrome with many tabs, Docker, IDE indexing) should be closed during video renders.
- macOS memory pressure must stay out of red; the app warns when free memory before a render is under 18 GB.
- Sustained renders heat the machine; expect thermal throttling on long batches and allow for it in time estimates.

## OS and system software

Everything must be native arm64; one Intel (x86\_64) binary in the chain breaks MLX installs, as the first setup attempt showed when Intel Homebrew supplied an x86\_64 Python.

| Component | Version | Install | Check |
| --- | --- | --- | --- |
| macOS | 14 Sonoma or later (tested on Tahoe 26.5.1) | System | `sw_vers` |
| Terminal | Not running under Rosetta | Finder → Get Info → untick “Open using Rosetta” | `uname -m` prints `arm64` |
| Xcode Command Line Tools | Current | `xcode-select --install` | `xcode-select -p` |
| Homebrew | Native, in `/opt/homebrew` | Official installer | `which brew` prints `/opt/homebrew/bin/brew` |
| uv | 0.5+ native | Astral installer | `file "$(which uv)"` shows arm64 |
| Python | 3.11 or 3.12, uv-managed, arm64 | `uv python install cpython-3.11-macos-aarch64-none` | `python -c "import platform; print(platform.machine())"` prints `arm64` |
| Node.js | 20 LTS or 22 LTS | `brew install node@22` | `node -v` |
| pnpm | 9+ | `corepack enable` | `pnpm -v` |
| ffmpeg / ffprobe | 7.x, native build | `brew install ffmpeg` | `ffmpeg -version` and `file "$(which ffmpeg)"` |
| git, git-lfs | Current | `brew install git git-lfs` | `git lfs version` |
| Hugging Face CLI | Current | `uv tool install huggingface_hub` | `hf --version` |

**Environment rules**

- `UV_PYTHON_PREFERENCE=only-managed` is set in `~/.zshrc` so uv never picks up a stray system or Intel Python.
- Intel Homebrew in `/usr/local` is removed or kept off `PATH`; `/opt/homebrew/bin` comes first.
- `HF_HOME` points at one shared cache (default `~/.cache/huggingface`) so models download once.
- Each Python tool (ltx-2-mlx, mlx-audio, the app backend) gets its own uv virtual environment; none share a venv.

## Local services

Seven local components must be installed and healthy before a render starts; every port is configurable and only bound to `127.0.0.1`.

| Service | Role | Interface | Default port | Health check |
| --- | --- | --- | --- | --- |
| ReelForge API | Orchestrator, job queue, metadata | HTTP + WebSocket | 7400 | `GET /health` returns all dependency statuses |
| ReelForge UI | Web app with video player and editors | HTTP (static + dev server) | 7401 | Page loads and connects to API |
| Draw Things | Character masters and key frames (txt2img, img2img, edit) | HTTP API server, enabled in app settings | 7860 | `GET /` responds; a 64×64 test generation succeeds |
| ltx-2-mlx | Shot video generation (t2v, i2v, a2v, extend, keyframe) | CLI in its own uv venv | n/a | `ltx-2-mlx info --model <model>` exits 0 |
| mlx-audio | Text-to-speech and voice cloning | CLI or its local server | 8000 (if server) | One-word test synthesis produces a WAV |
| Local LLM | Script to YAML, prompt enhancement, caption timing help | Ollama HTTP API | 11434 | `GET /api/tags` lists the configured model |
| ffmpeg / ffprobe | Frame extraction, concat, audio mix, captions, export | CLI | n/a | `ffmpeg -version` exits 0 |

**Service requirements**

- Draw Things must be running with its HTTP API server switched on before the cast or key-frame stages; the app checks this and shows how to enable it if not.
- Draw Things must have the required models already downloaded; the API cannot download models on its own.
- ltx-2-mlx is pinned to a known-good git commit; upgrades happen only through the app’s update check.
- The local LLM must not stay loaded during video renders (`keep_alive: 0` after each call).
- All services accept a configurable host and port through one config file and CLI flags; a port already in use is reported with the process holding it.
- No service may call the internet during rendering; network is used only for first-time model downloads.

## Model requirements

Each model is chosen to fit the 24 GB budget at its stated quantization, and every license must be re-checked on its model card before commercial use.

| Stage | Model | Variant | Approx. size | Runs in | License (verify) |
| --- | --- | --- | --- | --- | --- |
| Video | LTX-2.3 (Lightricks) | `dgrauet/ltx-2.3-mlx-q4` (q8 optional) | \~16 GB working set | ltx-2-mlx | LTX-2 Community License: free under $10M revenue, non-compete clause |
| Video (later) | LTX-2.5 | `dgrauet/ltx-2.5-mlx-q4` | similar | ltx-2-mlx, once supported | LTX-2 Community License |
| Character masters | FLUX.1 \[schnell\] or Z-Image Turbo | Draw Things built-in | 6–12 GB | Draw Things | Apache 2.0 (schnell) |
| Consistent edits | FLUX.1 Kontext \[dev\] | Draw Things built-in | 6–12 GB | Draw Things | Non-commercial weights; outputs reportedly usable commercially — confirm |
| Multi-image edits (optional) | Qwen Image Edit 2509 | Smallest quantized | large; may not fit | Draw Things | Believed Apache 2.0 — confirm |
| Hindi / Indian-English voice | Voxtral TTS | mlx-audio build | small | mlx-audio | Unverified — must confirm before brand use |
| Expressive English voice | Chatterbox | `mlx-community/Chatterbox-bf16` | small | mlx-audio | MIT |
| Voice design | Qwen3-TTS VoiceDesign | 1.7B, 8-bit | small | mlx-audio | Unverified — confirm |
| Fast draft voice | Kokoro-82M | bf16 | < 1 GB | mlx-audio | Apache 2.0 (verify) |
| Script structuring | Qwen3 8B Instruct or similar | 4-bit | \~5 GB | Ollama | Model-specific |

**Model rules**

- Model IDs, revisions and local paths live in one registry file; the app never hard-codes a model name in pipeline code.
- The registry records each model’s license and source URL, and every rendered reel stores which models made it.
- First run downloads models with progress shown; partial downloads resume.
- FP8 checkpoints are not allowed: Metal has no FP8 type, so FP8 weights fail on Apple Silicon.

## Functional requirements

IDs are referenced by the product and tech specs; “must” items gate v1, “should” items may slip to v1.1.

**Story input**

- FR-1 (must): Accept a storyline as free text, with optional sections for characters, backgrounds, product and dialogue.
- FR-2 (must): Convert the input into a validated `story.yaml` using the local LLM, then show it for review.
- FR-3 (must): Let the user edit `story.yaml` in a form view and a raw YAML view, with schema validation on save.
- FR-4 (must): Import and export `story.yaml` files directly, bypassing the LLM.

**Cast**

- FR-5 (must): Generate 4 candidate master images per character from its look description.
- FR-6 (must): Let the user approve one candidate, regenerate all, regenerate with an edited prompt, or upload their own image.
- FR-7 (must): Save approved characters to a reusable cast library (image, prompt, seed, voice, metadata).
- FR-8 (must): Let a new story reuse characters from the library instead of generating new ones.
- FR-9 (should): Generate a 3-view character sheet (front, side, back) for each approved character.

**Key frames**

- FR-10 (must): Generate one opening frame per scene by editing approved masters into the scene’s setting.
- FR-11 (must): Place the brand product into frames marked for it, using either an image edit or a manual overlay.
- FR-12 (must): Approve, regenerate or replace each key frame individually.

**Voice**

- FR-13 (must): Assign each character a voice (preset, designed, or cloned from a reference clip) stored in the cast library.
- FR-14 (must): Render one audio file per dialogue line, scene by scene.
- FR-15 (must): Play, approve, re-take, or edit the text of each line; keep all takes and mark one active.
- FR-16 (should): Adjust per-line speed, pause before/after, and volume.
- FR-17 (must): Use each approved line’s duration to set its shot length.

**Video**

- FR-18 (must): Render dialogue shots with audio-to-video lip sync from the key frame and the line’s audio.
- FR-19 (must): Render non-dialogue shots with image-to-video, without generated audio by default.
- FR-20 (must): Support continuing a shot from the previous shot’s last frame.
- FR-21 (must): Approve, re-roll (new seed), or re-prompt each shot without re-rendering others.
- FR-22 (should): Trim each shot’s in and out points before assembly.

**Assembly and export**

- FR-23 (must): Stitch approved shots in scene order with ffmpeg.
- FR-24 (must): Mix dialogue, optional background music and ambience into one track with ducking under speech.
- FR-25 (must): Burn captions from the dialogue text, timed to each line.
- FR-26 (must): Export a 1080×1920 H.264 MP4 suitable for Instagram Reels.
- FR-27 (should): Add an end card with logo and call-to-action.

**Review and control**

- FR-28 (must): Provide an in-app video player for every shot and the final reel.
- FR-29 (must): Show job progress live, with cancel and retry per job.
- FR-30 (must): Resume a project after an app restart or crash from the last completed step.
- FR-31 (should): Keep a version history of the final reel so earlier cuts can be compared.

## Non-functional requirements

The system must favour reliability and resumability over speed: a 15-second reel may take an hour to render, but no failure should cost more than the one step that failed.

| ID | Area | Requirement | Target |
| --- | --- | --- | --- |
| NFR-1 | Performance | Script to `story.yaml` | ≤ 60 s |
| NFR-2 | Performance | One character candidate image | ≤ 60 s |
| NFR-3 | Performance | One dialogue line of voice | ≤ 15 s |
| NFR-4 | Performance | One 3 s shot at 320×576 (q4, distilled) | ≤ 8 min, to be measured on first renders |
| NFR-5 | Performance | Final assembly of a 15 s reel | ≤ 60 s |
| NFR-6 | Reliability | A failed step retries once automatically, then waits for the user | 100% of steps |
| NFR-7 | Resumability | State is written to disk after every step; restart resumes from the last completed step | 100% |
| NFR-8 | Idempotency | Re-running a step with the same inputs and seed reuses the cached output | Content-hash cache |
| NFR-9 | Memory safety | Only one heavy model loaded at a time; pre-flight free-memory check before each render | Never two concurrently |
| NFR-10 | Privacy | No data leaves the machine; all services bind to `127.0.0.1` | Zero outbound calls during renders |
| NFR-11 | Offline | After models are downloaded, the full pipeline works with Wi-Fi off | Verified in acceptance test |
| NFR-12 | Observability | Structured logs per job with the exact command line, duration, peak memory and exit code | Every job |
| NFR-13 | Reproducibility | Every artifact records its prompt, seed, model and version | Every artifact |
| NFR-14 | Usability | A non-engineer can make a reel from the UI without the terminal | After setup |
| NFR-15 | Maintainability | Swapping a model or tool means changing one adapter and the model registry, not the pipeline | Per adapter |
| NFR-16 | Storage | Project folders are self-contained and can be zipped, moved or archived | Per project |

## Content and brand requirements

Every export must be a vertical reel that reads on mute, keeps the brand product legible, and holds one consistent look per character across all shots.

**Output format** (verify against Instagram’s current Reels spec before launch)

| Property | Value |
| --- | --- |
| Aspect ratio | 9:16 |
| Resolution | 1080×1920 final; shots may render smaller and be upscaled |
| Frame rate | 24 fps throughout (best for LTX lip sync) |
| Codec | H.264 High profile, yuv420p, AAC 48 kHz stereo |
| Length | 10–15 s target; 60 s hard limit in v1 |
| Loudness | About −14 LUFS integrated, true peak ≤ −1 dBTP |

**Brand and story rules**

- The first 2 seconds must contain a visual hook; the story template prompts for one.
- Captions are on by default, placed inside a safe zone that avoids Instagram’s top and bottom UI overlays.
- The product must appear in at least one shot; its real packaging is used, never an AI-redrawn logo.
- Brand assets (logo, pack shots, fonts, colours) live in a brand kit folder reused by every project.
- Each character keeps one look description, one master image and one voice for its whole life in the cast library.
- Dialogue may be Hindi, English or Hinglish; captions use the script text as written, in Latin or Devanagari script.
- Caption fonts must support Devanagari when Hindi script is used.
- No real people’s faces or voices, copyrighted characters, music or logos other than the brand’s own.

## Licensing and compliance

ReelForge is used to make marketing content, not to resell models, so the key question for each model is whether its outputs may be used commercially; that must be confirmed on each model card before any reel is published.

- LC-1: The model registry stores, per model, the code license, the weights license and the stated rule on outputs, with a link to the license text.
- LC-2: Every exported reel writes a `credits.json` listing each model, version and license used to make it.
- LC-3: The app warns when a project uses a model whose weights license is non-commercial or unverified.
- LC-4: LTX-2 Community License terms are tracked: free below $10M annual revenue, and no use in a product competing with Lightricks.
- LC-5: Background music must be original, generated by a model whose outputs are licensed for commercial use, or royalty-free with a stored license file.
- LC-6: ReelForge’s own code license is decided before any public release (MIT proposed).
- LC-7: These notes are not legal advice; a lawyer reviews licenses if BihariPakwan nears the LTX revenue threshold or ReelForge becomes a paid product.

## Setup checklist, acceptance and risks

The project is “up and running” when the acceptance reel below renders end to end, offline, on the reference Mac.

**Setup checklist**

- [ ] Terminal runs native arm64; Intel Homebrew removed from `PATH`
- [ ] Native Homebrew, uv, Node 22, pnpm, ffmpeg installed
- [ ] `UV_PYTHON_PREFERENCE=only-managed` set
- [ ] ltx-2-mlx cloned, pinned, synced; q4 weights downloaded; test clip renders
- [ ] mlx-audio installed in its own venv; Kokoro and Voxtral test lines render
- [ ] Draw Things installed; FLUX.1 schnell and Kontext \[dev\] downloaded; HTTP API server enabled
- [ ] Ollama installed; structuring model pulled
- [ ] ReelForge `doctor` command reports every dependency green
- [ ] Brand kit folder filled: logo, pack shots, fonts
- [ ] License fields confirmed for every model in the registry

**Acceptance criteria**

1. A storyline with 2 characters and 5 scenes becomes a valid `story.yaml` that the user can edit.
2. A cast is generated, approved, saved, and reused unchanged in a second project.
3. Five dialogue lines render, one is re-taken, and the active take is used downstream.
4. Five shots render; one is re-rolled without touching the other four.
5. The final reel is 10–15 s, 1080×1920, 24 fps, captioned, with mixed audio, and plays in the in-app player.
6. The app is killed mid-render; on restart it resumes from the last completed step.
7. Steps 1–5 complete with Wi-Fi off.
8. Two shots of the same character are judged “clearly the same character” by the user.

**Risks and mitigations**

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Out-of-memory during video renders | Job killed | Sequential stages, q4 + `--low-ram`, pre-flight memory check, smaller frames |
| Character drift between shots | Breaks continuity | Image-first workflow: masters → Kontext edits → i2v; fixed character bible text |
| Weak lip sync on side views or busy backgrounds | Unconvincing dialogue | Front-facing close-ups for dialogue shots; plain backgrounds |
| Upstream tool changes CLI flags (already seen with `--frame-rate`) | Pipeline breaks | Pin versions; adapter layer; `doctor` validates flags against `--help` |
| Hindi TTS quality below expectation | Off-brand voice | Compare Voxtral, Kokoro and cloned voices early; allow a recorded human voice as input |
| Draw Things API changes or app not running | Cast stage blocked | Health check, clear setup prompt; fallback adapter using mflux CLI |
| Model license unsuitable for commercial use | Legal exposure | License registry, warnings, `credits.json` |
| Render time too long for frequent posting | Low output | Batch overnight queue; optional cloud GPU backend later |

**Open questions**

- Which TTS model gives the best Hindi voices for cartoon characters? To be decided after a listening test.
- Does Draw Things’ HTTP API expose Kontext edit mode with reference images, or is mflux needed for edits?
- Does ltx-2-mlx support LTX-2.5 weights yet, and is it better at this resolution?
- Which background music source fits the licensing rules?
