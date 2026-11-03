# ReelForge — Technical Spec

Nov 1, 2026 · @Reetesh

## Key decisions

ReelForge is a Python (FastAPI) orchestrator with a TypeScript (React) UI, SQLite for metadata, plain folders for media, and every heavy model run as a short-lived subprocess so memory is fully returned between stages.

| Decision | Choice | Main reason |
| --- | --- | --- |
| Backend language | Python 3.12, managed by uv | Every model tool (ltx-2-mlx, mlx-audio, mflux) is Python/MLX; one language for orchestration and model glue |
| Frontend | TypeScript, React, Vite | Rich editors, video player and timeline need a real UI stack |
| API | FastAPI + WebSocket | Async, typed with Pydantic, auto OpenAPI for the UI client |
| Database | SQLite (WAL mode) via SQLAlchemy 2 + Alembic | Single user, single machine, zero ops, transactional, easy backup |
| Media storage | Per-project folders on disk; DB stores paths + content hashes | Files are large, inspectable in Finder, portable as a zip |
| Job queue | Persistent queue in SQLite, in-process async worker, one GPU lane | No Redis or Celery needed locally; survives restarts |
| Model execution | Subprocess per batch, in each tool’s own uv venv | Memory freed on exit; dependency isolation; crash containment |
| Image generation | Draw Things HTTP API (primary), mflux CLI (fallback) | User’s chosen tool; fallback removes a single point of failure |
| Video generation | ltx-2-mlx CLI, LTX-2.3 q4 | Only practical local audio+video model on Apple Silicon today |
| Voice | mlx-audio via a batch worker script | Many TTS models behind one MLX library |
| Local LLM | Ollama with JSON-schema structured output | Simple HTTP, model unload control, structured JSON |
| Assembly | ffmpeg via a filter-graph builder in Python | Deterministic, scriptable, no extra dependencies |
| Config | TOML file + env vars + CLI flags | Ports and paths overridable at every level |

## Architecture

The browser talks only to the ReelForge API; a single worker inside the same Python process owns the job queue and the GPU lease, and reaches every model tool either over local HTTP or as a short-lived subprocess.

&#91;embedded content: system architecture · app, worker, five local tools\]

Draw Things and Ollama are long-running apps the worker calls over HTTP; ltx-2-mlx, mlx-audio and ffmpeg are started per job and exit when done, which is what returns memory between stages.

## Stack choice

The answer is a hybrid split by responsibility: Python owns everything that touches models, files and processes; TypeScript owns only the browser UI.

| Option | Strengths | Weaknesses | Verdict |
| --- | --- | --- | --- |
| All Python (FastAPI + server-rendered or Streamlit UI) | One language; closest to MLX tools | A timeline editor, waveform views and a custom player are painful without a real frontend framework | Rejected for UI |
| All Node/TypeScript (Next.js or Fastify) | Great UI story, one language | Every model step becomes a cross-language subprocess with no shared types; MLX-side helper scripts still need Python | Rejected for backend |
| **Hybrid: Python backend + TypeScript UI** | Each side uses its natural ecosystem; OpenAPI generates a typed TS client from Pydantic models | Two toolchains | **Chosen** |

**Backend libraries**

- FastAPI, Uvicorn, Pydantic v2 (schemas shared by API, `story.yaml` validation and DB models)
- SQLAlchemy 2 + Alembic (migrations), aiosqlite
- httpx (Draw Things, Ollama), anyio subprocess management, psutil (memory and child-process monitoring)
- ruamel.yaml (round-trip YAML that keeps user comments and ordering)
- Typer (the `reelforge` CLI), structlog (JSON logs), tomlkit (config)

**Frontend libraries**

- React 19, Vite, TypeScript strict, TanStack Query (server state), Zustand (editor state)
- Monaco editor (YAML view with schema validation via monaco-yaml)
- wavesurfer.js (waveforms and line trimming)
- A custom timeline built on HTML canvas; native `<video>` with custom controls for the player
- openapi-typescript for a generated, typed API client

## Process and memory model

With 24 GB shared between CPU and GPU, the system treats GPU memory as a single leased resource: exactly one heavy job holds the lease, and it must release every model before the next job starts.

**Processes**

1. `reelforge-api`: FastAPI app, serves REST, WebSocket and the built UI. Never loads a model.
2. `reelforge-worker`: an async loop in the same process that claims jobs from SQLite and runs them. Light jobs (ffmpeg probes, file ops, YAML) run in parallel; heavy jobs go through the GPU lease.
3. Model subprocesses: started per batch, exit when done. ltx-2-mlx and mlx-audio each run from their own uv project (`uv run --project <path> …`).
4. External apps: Draw Things (macOS app with HTTP server) and Ollama (daemon) are long-running and managed, not owned.

**The GPU lease**

- A single `asyncio.Lock` named `gpu` plus a DB row recording the holder job, so a crash can be detected and the lease reclaimed on restart.
- Before acquiring, the worker runs **pre-flight**: free memory from `psutil.virtual_memory().available` must exceed the job’s declared need (e.g. 18 GB for an LTX q4 render); otherwise it tries to free memory, then waits or fails with a clear reason.
- **Freeing memory** in order: (a) tell Ollama to unload (`keep_alive: 0`); (b) if Draw Things is the holder and the next job is not an image job, optionally quit it with `osascript -e 'quit app "Draw Things"'` and relaunch later with `open -a "Draw Things"` — off by default, switchable in Settings; (c) nothing else is touched.

**Batching to load each model once**

- Voices: one mlx-audio subprocess renders all pending lines of a project, then exits.
- Frames: one Draw Things session handles all frames in sequence.
- Shots: one ltx-2-mlx subprocess per shot (the CLI is per-output); weights load from disk each time, which is acceptable at several minutes per render.

**Monitoring**

- The worker samples the child process tree every 2 s (RSS, CPU) and system available memory; peak values are stored on the job.
- If available memory drops under 1.5 GB during a render, the job is flagged “memory pressure” in the log so the user knows why a render slowed or died.
- Exit code `-9`/`137` is classified as “killed, likely out of memory” and offers a smaller retry.

## Data model

SQLite holds metadata and relationships; every generated file is an `artifact` row pointing at a path with its content hash, inputs fingerprint and parameters, which is what makes caching, takes and staleness work.

| Table | Key columns | Notes |
| --- | --- | --- |
| `projects` | id (ULID), slug, title, data\_dir, stage, brand\_kit\_id, created\_at, updated\_at | `stage` = furthest approved stage |
| `story_versions` | id, project\_id, version, yaml\_text, approved\_at | Every saved story kept; one marked current |
| `characters` | id, name, aliases (JSON), look\_text, master\_artifact\_id, sheet\_artifact\_ids (JSON), voice\_id, tags (JSON), parent\_character\_id | Library-level; `parent_character_id` links project variants |
| `ensembles` | id, name, character\_ids (JSON) | Saved groups like “Veggie gang” |
| `voices` | id, mode (preset/designed/cloned/recorded), model\_key, voice\_ref, reference\_artifact\_id, speed, language | Shared by characters |
| `project_characters` | project\_id, story\_key, character\_id | Maps `story.yaml` keys (e.g. `tomato`) to library characters |
| `scenes` | id, project\_id, story\_key (s1…), position, shot\_type, duration\_s, frames, continue\_from | Derived from current story version |
| `lines` | id, scene\_id, character\_id, text, language, speed, pause\_before, pause\_after | One dialogue line per talking scene in v1 |
| `artifacts` | id, project\_id, owner\_type, owner\_id, kind, take\_no, path, sha256, inputs\_fp, params (JSON), model\_key, seed, status, is\_active, duration\_s, width, height, created\_by\_job | Kinds: candidate, master, sheet, voice\_take, frame, shot, last\_frame, preview, final, edl, captions |
| `artifact_inputs` | artifact\_id, input\_artifact\_id | The dependency graph used for staleness |
| `jobs` | id, project\_id, type, status, priority, payload (JSON), heavy (bool), mem\_need\_gb, attempts, pid, command (JSON), log\_path, started\_at, finished\_at, peak\_rss\_mb, exit\_code, error | Persistent queue |
| `approvals` | id, project\_id, stage, owner\_type, owner\_id, artifact\_id, approved\_at, note | Audit trail of every approval |
| `reel_versions` | id, project\_id, version, edl\_artifact\_id, final\_artifact\_id, credits (JSON), created\_at | v1, v2… |
| `brand_kits` | id, name, data\_dir, config (JSON) | Logos, packs, fonts, colours |
| `settings` | key, value (JSON) | UI-editable settings mirrored from config |

**Conventions**

- IDs are ULIDs (sortable, safe in file names).
- `inputs_fp` = SHA-256 of a canonical JSON of: adapter name and version, model key and revision, prompt text, seed, all numeric params, and the `sha256` of every input artifact.
- One `is_active` artifact per owner and kind; switching takes flips the flag in a transaction.
- Files are never deleted by normal flows; a “Clean unused takes” action removes inactive takes older than N days.

## File system layout

One data root (default `~/ReelForge`, configurable) holds the database, the shared cast library, brand kits and one self-contained folder per project; a project folder plus its library characters can be zipped and moved to another Mac.

```
~/ReelForge/
├── reelforge.db                 # SQLite (WAL)
├── config.toml                  # ports, paths, model choices
├── models.toml                  # model registry: keys, revisions, licenses
├── library/
│   ├── characters/
│   │   └── chr_01JBX…_tomato/
│   │       ├── character.json   # look text, tags, seed, model (mirror of DB row)
│   │       ├── master.png
│   │       ├── sheet_front.png  sheet_side.png  sheet_back.png
│   │       └── voice/ reference.wav  voice.json
│   └── ensembles.json
├── brand/
│   └── biharipakwan/ logo.png  packs/  fonts/  music/  kit.json
├── projects/
│   └── 2026-11-01_wedding-thekua_01JBY…/
│       ├── story.yaml           # current story (also versioned in DB)
│       ├── project.json         # snapshot for portability
│       ├── cast/                # candidates and project variants
│       │   └── tomato/ cand_001.png … cand_004.png
│       ├── voices/
│       │   └── s2/ take_001.wav  take_002.wav  take_002.json
│       ├── frames/
│       │   └── s2/ take_001.png  take_001.json
│       ├── shots/
│       │   └── s2/ take_001.mp4  take_001.last.png  take_001.json
│       ├── assembly/
│       │   └── v001/ edl.json  captions.ass  mix.wav  preview.mp4  final.mp4  cover.jpg  credits.json
│       ├── uploads/             # user-provided files
│       └── logs/ <job_id>.log
└── cache/tmp/                   # scratch, safe to delete
```

**Rules**

- Project folder name = date + slug + ULID, so it sorts by date and never collides.
- Every generated file has a sidecar `.json` with prompt, seed, model, params, `inputs_fp` and job id, so the folder is understandable without the database.
- Writes go to `cache/tmp` first, then an atomic `rename` into place, so a crash never leaves half-written takes.
- All paths stored in the DB are relative to the data root; moving the root only changes one config value.
- Model weights are not stored here; they stay in the Hugging Face cache and Draw Things’ own model folder.

## Pipeline engine

The engine is a small DAG of typed tasks over artifacts: each task declares its inputs and parameters, computes a fingerprint, reuses a cached artifact if one matches, and otherwise enqueues a job.

**Stage gates** (project-level state machine)

`DRAFT → STORY_APPROVED → CAST_APPROVED → VOICES_APPROVED → FRAMES_APPROVED → SHOTS_APPROVED → ASSEMBLED → EXPORTED`. A stage’s actions are enabled only when the previous gate is passed; editing an approved stage drops `stage` back to that point for affected items only.

**Task types**

| Task | Inputs | Output artifact | Heavy | Adapter |
| --- | --- | --- | --- | --- |
| `structure_story` | Free-text story, library picks | story version | No (LLM, light) | Ollama |
| `gen_candidates` | Look text, style, seed | 4 × candidate | Yes | Draw Things |
| `gen_sheet` | Master image | 3 × sheet | Yes | Draw Things (edit) |
| `gen_voice_take` | Line text, voice, speed | voice\_take | Yes | mlx-audio |
| `gen_frame` | Masters, setting, action, framing, product | frame | Yes | Draw Things (edit) |
| `gen_shot` | Frame or last\_frame, motion prompt, audio (talking), frames, seed | shot + last\_frame | Yes | ltx-2-mlx |
| `assemble_preview` | Active shots, takes, EDL | preview | No | ffmpeg |
| `export_final` | EDL | final + cover + credits | No (CPU) | ffmpeg |

**Caching and idempotency**

- `inputs_fp` match + file present + sha256 matches → reuse, no job.
- “New take” deliberately changes the seed, so it never hits the cache.

**Staleness**

- An active artifact is stale when any input it was made from is no longer the active artifact for that input slot, or the story field it depends on changed.
- Computed on read by walking `artifact_inputs` (graphs are tiny: tens of nodes per project), so there is no stored flag to get out of sync.

**Shot length and frame math**

- Talking shot: `duration = pause_before + line_audio + pause_after`.
- LTX needs `frames = 8k + 1`: `frames = 8 × ceil((duration × 24 − 1) / 8) + 1`; e.g. 2.9 s → 73 frames (3.04 s). The extra few frames are trimmed at assembly.
- Draft size 320×576; final size 448×768 or larger if memory allows, upscaled to 1080×1920 at export.

**Job lifecycle**

`queued → running → succeeded | failed | cancelled`. One automatic retry for transient failures (service unreachable, process killed under memory pressure with a smaller size). On startup, jobs left `running` with a dead `pid` are reset to `queued` and the GPU lease row is cleared.

## Adapters

Every external tool sits behind one adapter class with the same contract, so swapping a tool or model touches one file and the model registry.

```python
class Adapter(Protocol):
    name: str
    async def health(self) -> HealthReport          # reachable, version, models present
    async def capabilities(self) -> set[str]        # e.g. {"txt2img", "edit"}
    async def run(self, task: TaskSpec, out_dir: Path,
                  progress: ProgressCb, cancel: CancelToken) -> list[ProducedFile]
```

Commands are always built as argument lists (never `shell=True`), logged verbatim, and run with a timeout.

**Draw Things (image generation and edits)**

- Transport: HTTP to the app’s API server on `127.0.0.1:<drawthings_port>` (default 7860), with optional shared secret.
- Endpoints: A1111-style `txt2img` / `img2img` routes with JSON parameters (model, prompt, negative prompt, seed, steps, guidance, width, height, sampler) and base64 init images. **Spike required:** confirm the exact routes, the parameter names it accepts, and how Kontext/Qwen edit mode and reference images are passed.
- Candidates: 4 calls with seeds `s, s+1, s+2, s+3` (or `batch_size` if honoured).
- Edits (sheet, frames): master image as init image + instruction prompt in edit mode.
- Fallback adapter: `mflux` CLI (MLX-native FLUX/Kontext/Qwen edit) run as a subprocess in its own venv, enabled if Draw Things is unavailable or lacks a needed mode.

**ltx-2-mlx (video)**

Run as `uv run --project <ltx_path> ltx-2-mlx <subcommand> …`. Flags confirmed so far from its `--help`:

```bash
# Action shot (image-to-video, silent)
ltx-2-mlx generate -p "<motion prompt + character bible lines>" \
  --image frames/s4/take_001.png ... --distilled --model dgrauet/ltx-2.3-mlx-q4 \
  --frame-rate 24 --frames 57 --width 320 --height 576 --seed 1234 \
  --no-audio --low-ram -o shots/s4/take_001.mp4

# Talking shot (audio-to-video, lip sync)
ltx-2-mlx a2v -p "<appearance only, no motion words>" --audio voices/s2/take_002.wav \
  ... --low-ram -o shots/s2/take_001.mp4

# Continue shot
ltx-2-mlx extend -p "<prompt>" --video shots/s3/take_001.mp4 --extend-frames 2 -o …

# Transition shot
ltx-2-mlx keyframe -p "<prompt>" --start a.png --end b.png -o …
```

- `--frame-rate` is required (learned the hard way); the `--image` argument takes more than a path, and the a2v image-conditioning flags must be confirmed in the spike.
- The adapter parses `--help` at startup and refuses to run if a required flag is missing, so an upstream change fails loudly in `doctor`, not mid-render.
- Progress: parse stdout/stderr step counters; fall back to elapsed time vs. a moving average of past renders at the same size.
- After success: `ffmpeg -sseof -0.1 -i shot.mp4 -frames:v 1 -update 1 shot.last.png` for continuation.

**mlx-audio (voice)**

- A \~100-line `tts_worker.py` lives in the ReelForge repo and runs inside the mlx-audio venv: it reads a JSONL batch (`{id, text, model, voice, ref_audio, speed, lang}`), loads each model once, writes WAVs (24 kHz mono) plus duration, and prints JSON progress lines.
- Supports preset voices, voice design (Qwen3-TTS VoiceDesign) and cloning from a reference clip (model-dependent).
- Post-process with ffmpeg: trim leading/trailing silence, normalise to −16 LUFS, resample to 48 kHz for assembly.

**Ollama (local LLM)**

- `POST /api/chat` with `format` set to the JSON schema of the expected output, `options.temperature` 0.2–0.4, and `keep_alive: 0` when a heavy job is next.
- Every response is validated with Pydantic; one automatic repair round sends the validation errors back; then the user sees the error.

**ffmpeg / ffprobe**

- `ffprobe -show_streams -of json` for every generated media file (duration, size, fps) before it is marked done.
- Filter graphs are built by a small typed builder, then serialised to a `-filter_complex_script` file (avoids shell-length and quoting issues) and stored next to the output for debugging.

## Where local LLMs are used

Local LLMs do the language work that turns loose human input into precise, model-specific instructions; they never decide anything the user hasn’t approved, and every output is schema-checked.

| Use | When | Model | Output | User sees |
| --- | --- | --- | --- | --- |
| Story structuring | “Structure my story” | Text LLM, 7–8B, 4-bit | `story.yaml` (JSON schema) + gap questions | Editable story + questions |
| Look normalisation | Character created | Text LLM | One fixed-format character bible line | Editable look text |
| Frame prompt writing | Before each key frame | Text LLM | Edit instruction for Kontext/Qwen (“keep the same character…”) | Prompt shown, editable |
| Motion prompt writing | Before each shot | Text LLM | LTX prompt: appearance + motion; for a2v, appearance only | Prompt shown, editable |
| Line-length fitting | Line over its scene budget | Text LLM | 2–3 shorter rewrites in the same language and tone | Pick one or ignore |
| Hook check | Story approval | Text LLM | Flags if the first 2 s lack a visual hook, with a suggestion | Advisory note |
| Caption and hashtags | Export | Text LLM | Instagram caption + 10–15 hashtags | Copy button, editable |
| Visual QA (v1.1) | After frames and shots render | Vision LLM (e.g. a 7B VL model, 4-bit) | Scores: same character as master? product visible? artifacts? | Warning badge, never auto-reject |
| Word timing for captions | Before assembly | Forced aligner / Whisper via mlx-audio | Word timestamps | Word-by-word caption highlight |

**Rules**

- Prompts are versioned files in the repo (`prompts/*.md`), with few-shot examples, so behaviour changes are reviewable.
- The LLM never writes outside its schema: unknown keys fail validation; the user always sees a diff before an LLM change is applied to `story.yaml`.
- Every LLM call is light and short; it is unloaded (`keep_alive: 0`) before any heavy job takes the GPU lease.

## Assembly

Assembly is driven entirely by an edit decision list (`edl.json`) produced from the timeline, so a preview and a final export are the same graph rendered at two quality levels.

**EDL shape**

```json
{
  "fps": 24, "width": 1080, "height": 1920,
  "video": [ {"artifact": "art_…", "in": 0.0, "out": 2.9, "transition": {"type": "cut"}} ],
  "dialogue": [ {"artifact": "art_…", "start": 2.0, "gain_db": 0} ],
  "music": {"path": "brand/biharipakwan/music/dhol.mp3", "gain_db": -14, "duck": true, "fade_out": 1.0},
  "captions": [ {"start": 2.0, "end": 4.6, "text": "Arre Aloo, itni der kyun?", "words": […]} ],
  "end_card": {"template": "default", "duration": 1.5}
}
```

**Steps**

1. **Normalise shots:** trim each shot to its `in/out`, scale to 1080×1920 (Lanczos; optional LTX spatial upscaler at final quality), force 24 fps, `yuv420p`, strip shot audio.
2. **Join video:** `concat` filter for cuts; `xfade` for crossfades. Re-encode (shots come from different renders, so stream copy is unsafe).
3. **Build dialogue track:** each active voice take placed with `adelay` at its start time, then `amix`.
4. **Music bed:** loop/trim to length, fade in/out, then `sidechaincompress` keyed by the dialogue track for ducking.
5. **Mix and loudness:** `amix` dialogue + ducked music + ambience, then two-pass `loudnorm` to about −14 LUFS integrated, −1 dBTP.
6. **Captions:** generate an `.ass` file (styles per preset, safe-zone margins, Devanagari-capable font from the brand kit, karaoke tags for word highlight) and burn it with the `subtitles` filter (requires libass; checked by `doctor`).
7. **End card:** render the brand template (logo, tagline, URL) as a short clip and append.
8. **Encode:** preview = `libx264 -preset veryfast -crf 28` at 540×960; final = `libx264 -preset slow -crf 18 -profile:v high -pix_fmt yuv420p -movflags +faststart`, AAC 192 kb/s 48 kHz.
9. **Verify:** ffprobe the output (duration within 50 ms of EDL, 24 fps, 1080×1920, audio present), write `credits.json`, extract `cover.jpg`.

Preview renders in seconds and is regenerated on every timeline edit with a 1 s debounce; the final export is explicit.

## API and realtime events

The API is resource-oriented REST under `/api/v1`, with one WebSocket for live job and status events; all long work returns a job ID immediately.

| Method & path | Purpose |
| --- | --- |
| `GET /health` | Overall status + every dependency’s health |
| `GET /api/v1/projects` · `POST` · `GET /{id}` · `PATCH` · `DELETE` (archive) | Projects |
| `POST /api/v1/projects/{id}/story:structure` | Free text → LLM → new story version (job) |
| `PUT /api/v1/projects/{id}/story` · `POST …/story:approve` | Save YAML (validated) · approve |
| `GET/POST /api/v1/library/characters` · `GET/PATCH /{cid}` | Cast library |
| `POST /api/v1/projects/{id}/cast/{key}:generate` · `:approve` · `:use-library` | Candidates, approval, reuse |
| `POST /api/v1/projects/{id}/voices:generate` · `/lines/{lid}:retake` · `:approve` | Voice takes |
| `POST /api/v1/projects/{id}/frames:generate` · `/scenes/{sid}/frame:approve` | Key frames |
| `POST /api/v1/projects/{id}/shots:render` · `/scenes/{sid}/shot:reroll` · `:approve` · `PATCH …/shot` (trim) | Shots |
| `PUT /api/v1/projects/{id}/edl` · `POST …/assemble:preview` · `POST …/export` | Timeline and export |
| `POST /api/v1/uploads` | User files (multipart) into a project’s `uploads/` |
| `GET /api/v1/jobs?project=` · `POST /jobs/{jid}:cancel` · `:retry` | Queue control |
| `GET /media/{artifact_id}` | Range-request file serving for the player (scoped to the data root) |
| `GET/PUT /api/v1/settings` | Ports, models, render defaults |

**WebSocket `/ws/events`** sends JSON events:

- `job.updated` {job\_id, status, progress 0–1, eta\_s, message}
- `artifact.created` {owner, kind, artifact\_id, take\_no}
- `stage.changed` {project\_id, stage}
- `health.changed` {service, status}
- `memory.sample` {available\_gb, pressure} every 5 s while a heavy job runs

Media is served with HTTP range support so the `<video>` element can seek instantly; files are addressed by artifact ID, never by raw user-supplied paths.

## Frontend

The UI is a single-page React app served by the API in production and by Vite (with an API proxy) in development; the video player, timeline and editors are the only complex components.

**Structure**

```
web/src/
├── api/          # generated OpenAPI client + WebSocket hook
├── routes/       # Projects, Project (stage tabs), Library, BrandKit, Settings
├── stages/       # StoryStage, CastStage, VoiceStage, FramesStage, ShotsStage, AssemblyStage
├── components/
│   ├── Player/       # 9:16 player, frame step, loop, safe-zone overlay
│   ├── Timeline/     # canvas tracks: video, dialogue, music, captions
│   ├── TakePicker/   # compare and switch takes
│   ├── YamlEditor/   # Monaco + monaco-yaml with the story JSON schema
│   ├── Waveform/     # wavesurfer.js wrapper
│   └── OverlayCanvas/ # manual product placement (drag, scale, rotate)
└── state/        # Zustand stores for editor state; TanStack Query for server state
```

**Player**

- Native `<video>` with custom controls; frame stepping uses `currentTime ± 1/24`; `requestVideoFrameCallback` keeps the timeline playhead in sync.
- One component reused for candidates, shots, take comparison (two players with linked playheads) and the final reel.
- Instagram safe-zone overlay as a toggleable SVG layer.

**Timeline**

- HTML canvas rendering for smooth scrubbing; thumbnails per shot from ffmpeg-generated sprite sheets; waveforms from pre-computed peaks JSON.
- Edits produce EDL patches sent with `PUT /edl`; the server responds with a new preview job.

**Live updates**

- One WebSocket connection; events invalidate the matching TanStack Query keys, so cards update without polling.
- Long jobs show progress bars with ETA on their cards and in a global activity drawer.

**Design**

- Dark-first theme suited to video work, keyboard shortcuts (Space play, ←/→ frame, A approve, R re-roll), and a persistent stage stepper at the top of each project.

## Startup, doctor and configuration

`reelforge up` refuses to start rendering until `doctor` passes: it checks every dependency, prints a fix for each failure, and lets every port and path be overridden.

**CLI**

```bash
reelforge doctor                      # check everything, exit non-zero on blocking failures
reelforge up                          # doctor, then start API + worker + UI
reelforge up --api-port 7500 --ui-port 7501 --drawthings-port 7870 \
             --ollama-url http://127.0.0.1:11500 --data-root ~/ReelForgeData
reelforge setup                       # guided install of missing pieces (asks before each step)
reelforge models pull                 # download weights listed in models.toml
```

**Configuration precedence:** CLI flags > environment variables (`REELFORGE_API_PORT`, `REELFORGE_DRAWTHINGS_PORT`, …) > `config.toml` > built-in defaults.

```toml
[server]
host = "127.0.0.1"
api_port = 7400
ui_port = 7401

[services.drawthings]
url = "http://127.0.0.1:7860"
shared_secret = ""
quit_when_idle_for_video = false

[services.ollama]
url = "http://127.0.0.1:11434"
model = "qwen3:8b"

[tools.ltx]
project_path = "~/tools/ltx-2-mlx"
pinned_commit = "<sha>"
model = "dgrauet/ltx-2.3-mlx-q4"

[tools.mlx_audio]
project_path = "~/tools/mlx-audio-env"

[paths]
data_root = "~/ReelForge"
```

**Doctor checks** (blocking = cannot render; warning = degraded)

| Check | How | Severity |
| --- | --- | --- |
| Native arm64 shell | `platform.machine() == "arm64"`, not translated (`sysctl sysctl.proc_translated` = 0) | Blocking |
| Binaries native | `file` on uv, python, ffmpeg resolves to arm64 | Blocking |
| Intel Homebrew on PATH | `/usr/local/bin` before `/opt/homebrew/bin` | Warning |
| ffmpeg features | `ffmpeg -filters` lists `subtitles`, `loudnorm`, `sidechaincompress`, `xfade` | Blocking |
| ltx-2-mlx | venv exists, commit matches pin, `--help` has required flags, model files present | Blocking |
| mlx-audio | venv exists, `tts_worker.py --selftest` renders a 1-word WAV | Blocking |
| Draw Things | HTTP reachable, test 64×64 render, required models listed | Blocking for cast/frames |
| Ollama | `GET /api/tags` lists the configured model | Warning (YAML can be hand-written) |
| Ports | each configured port is bindable; if not, report the holder via `lsof -iTCP:<port> -sTCP:LISTEN` and suggest the next free port | Blocking for app ports |
| Disk | data root has ≥ 30 GB free | Warning under 30 GB, blocking under 5 GB |
| Memory | total ≥ 24 GB; current available shown | Warning |
| Licenses | every model in `models.toml` has a license field filled | Warning |

**Startup sequence**

1. Load config, apply precedence, validate with Pydantic.
2. Run doctor; print a colour table; abort on blocking failures unless `--allow-degraded`.
3. Open SQLite, run Alembic migrations, recover orphaned jobs and the GPU lease.
4. Start Uvicorn (API + static UI) and the worker loop.
5. Begin background health polling every 15 s; changes are pushed as `health.changed` events and shown in the Status panel.
6. Open the browser at the UI URL.

## Observability, testing and security

The system must be debuggable from its files alone, testable without a GPU, and closed to anything outside the machine.

**Observability**

- structlog JSON logs to `~/ReelForge/logs/app.log` (rotated) and one log per job in the project’s `logs/` with the exact command, environment summary, stdout/stderr, duration, peak RSS and exit code.
- A Jobs view in the UI shows the same data, with “Copy command” to reproduce any render in a terminal.
- Render-time history per (model, size, frames) feeds the ETA estimates.

**Testing**

| Layer | What | How |
| --- | --- | --- |
| Unit | Schema validation, frame math, fingerprints, staleness, EDL → filter graph | pytest, property tests for frame math |
| Adapter contract | Each adapter against a fake binary or fake HTTP server that mimics real outputs and failures | pytest + respx + stub executables |
| Mock backend | Whole pipeline with a `mock` backend that emits coloured placeholder images, sine-tone WAVs and test-pattern MP4s | `reelforge up --backend mock`; runs in CI on any machine |
| Golden media | Assembly output checked with ffprobe (duration, fps, size, loudness within tolerance) | pytest fixtures |
| Real smoke | One tiny real render per tool on the Mac (64×64 image, 1-word voice, 9-frame shot) | `reelforge doctor --deep` |
| UI | Critical flows (approve cast, retake line, re-roll shot, export) | Playwright against the mock backend |

**Security and safety**

- All servers bind to `127.0.0.1` only; CORS limited to the UI origin; an optional local token protects the API from other local apps.
- No `shell=True`; arguments are lists; user text never reaches a shell.
- Media serving resolves artifact IDs to paths and rejects anything outside the data root (no path traversal).
- Uploads are type-checked by content (ffprobe / Pillow), size-limited, and stored under `uploads/` with generated names.
- The LLM output is data, never executed; YAML is parsed in safe mode.
- No telemetry; no outbound network during renders (verified in the offline acceptance test).

## Delivery plan

Start with four short spikes that remove the biggest unknowns, then build the backbone on the mock backend so the pipeline works end to end before any real model is wired in.

**Spikes (each a throwaway script and a one-paragraph finding)**

- [x] **S1 Draw Things API:** exact routes and parameters; can it do Kontext edits with a reference image; how to select models; speed per 576×1024 image.
  - **Finding (Nov 1, 2026, Draw Things with `flux_1_kontext_dev_q8p.ckpt`, API server on 127.0.0.1:7860, no secret):** works; Draw Things stays the primary image adapter, mflux stays the fallback.
  - Routes: `POST /sdapi/v1/txt2img` and `POST /sdapi/v1/img2img` (404 on GET); `GET /sdapi/v1/options` and `GET /` return 200 (`GET /` returns the app's current generation config as JSON). No `/docs`, `/openapi.json`, `sd-models` or `progress` routes, so `health()` uses `GET /` and cannot read progress; use elapsed time.
  - Request: JSON with `prompt`, `width`, `height`, `steps`, `seed`, `strength`, `batch_count`, `batch_size`, `model`, `init_images` (base64). Response: `{"images": ["<base64>", …]}`. An unknown `model` returns HTTP 422; a valid model file name is accepted.
  - Kontext edit: master image as `init_images[0]` with an instruction prompt keeps the character identical and changes the scene (verified at 576×1024).
  - Speed on the reference Mac at 576×1024, 20 steps: txt2img about 55–60 s per image; edit about 100 s. `batch_count=4` took 222 s for 4 images and `batch_size=2` took 121 s for 2, so batching gives no speed-up; run candidates as separate calls (progress per image, cancel between images).
  - Open: a second entry in `init_images` is accepted (one image returned, 52 s at 10 steps) but whether it is used as a second reference, for product placement, is not yet checked; Mode B (manual overlay) stays the safe path for packs with fine text.
- [x] **S2 LTX a2v:** a2v with an image + 3 s Hindi line at 320×576; image-conditioning flags; peak memory; render time; lip-sync quality on a cartoon face.
  - **Finding (Nov 3, 2026, ltx-2-mlx 0.18.0 in `~/tools/ltx-2-mlx` (Python 3.11, arm64), weights `dgrauet/ltx-2.3-mlx-q4`, Gemma `mlx-community/gemma-3-12b-it-4bit`):** works; **talking shots use `a2v` with the approved key frame as `--image`, no separate lip-sync pass needed for cartoon characters.** The human reviewer judged the character and the lip movement good (Hindi line from OmniVoice, 3.32 s). Samples: `~/reelforge-spikes/s2/talk_distilled.mp4`.
  - Command: `ltx-2-mlx a2v --prompt "<motion prompt>" --audio line.wav --image still.png 0 1.0 --model dgrauet/ltx-2.3-mlx-q4 --distilled --low-ram --width 320 --height 576 --frames 81 --frame-rate 24 --seed 1 -o out.mp4`. `--image PATH FRAME STRENGTH [auto|replace|guide] [CRF]` is repeatable; `--frames` takes 8k+1 (81 frames for 3.32 s); `--frame-rate` is mandatory; the default `--model` is q8, so pass the q4 id explicitly. `--distilled` is marked experimental in the CLI but gave a good result (8 stage-1 steps, no CFG); the non-distilled path (30 steps, CFG) was not tried.
  - Speed and memory (reference Mac, 24 GB, with `--distilled --low-ram`): render **48 s** wall for 3.4 s of video; `/usr/bin/time -l` peak memory footprint **15.6 GB**, max resident set 5.2 GB; the VAE decode was the peak (about 11.2 GB Metal). Use about 16 GB as the pre-flight requirement for a draft shot until measured at final size.
  - Open: only a cartoon character was tested; **lip sync on human-like characters is unverified** and must be checked before they are promised. The experimental `lipdub` command is the fallback if it is weak. Final-size renders and the non-distilled path are untested.
- [x] **S3 Hindi TTS bake-off:** same 5 lines through Voxtral, Kokoro, Qwen3-TTS and a cloned voice; pick defaults; confirm licenses.
  - **Finding (Nov 3, 2026, mlx-audio 0.6.4 in `~/tools/mlx-audio-env`, arm64 Python 3.12; 5 Hindi lines about 3–5 s each; samples in `~/reelforge-spikes/s3/index.html`):** **default voice model OmniVoice, fallback Kokoro.** The human listener judged OmniVoice's Hindi pronunciation correct.
  - OmniVoice (`mlx-community/OmniVoice-bfloat16`, Apache-2.0, call with `language="hi"`): lists 600+ languages, supports cloning (`ref_audio`, `ref_text`) and voice design (`instruct`); 24 kHz; about 7 s for the 5 lines after load; the first run downloaded the weights (about 3 min).
  - Kokoro (`mlx-community/Kokoro-82M-bf16`, Apache-2.0, `lang_code="h"`, voices `hf_alpha`, `hf_beta`, `hm_omega`, `hm_psi`): preset voices only, no cloning; fast (about 6 s for the 5 lines); needs the extra packages `misaki`, `espeakng-loader`, `phonemizer-fork`, `num2words`, `spacy`.
  - Voxtral (`mlx-community/Voxtral-4B-TTS-2603-mlx-4bit`, voices `hi_female`, `hi_male`): speaks Hindi (about 7 s for the 5 lines) but is **CC-BY-NC-4.0, non-commercial**, so it is not a default; needs `mistral-common[audio]`.
  - Qwen3-TTS (`mlx-community/Qwen3-TTS-12Hz-1.7B-CustomVoice-8bit`, Apache-2.0): its supported languages are Chinese, English, German, Italian, Portuguese, Spanish, Japanese, Korean, French and Russian; **Hindi is not supported**, so it is out for Hindi.
  - Setup gotcha: `uv` can pick an x86_64 (Rosetta) Python and then fail to find MLX wheels; pin an arm64 Python (`uv venv --python cpython-3.12-macos-aarch64-none`).
  - Open: voice cloning was **not** tested (no reference clip); treat cloning in M4 as unverified until a real Hindi clip is tried with OmniVoice. `models.toml` still lists Kokoro as the only `[models.tts]` entry; M4 makes OmniVoice the default and adds Kokoro as the fallback entry.
- [x] **S4 Memory choreography:** Draw Things open + LTX render on 24 GB; does Draw Things release memory when idle, or must it be quit?
  - **Finding (Nov 3, 2026):** the S2 render ran with **Draw Things open (idle, Kontext loaded) and Ollama running**, finishing with **0 swaps** and a 15.6 GB peak footprint. Auto-quitting Draw Things is **not needed** at draft size (320×576, `--low-ram`); keep it off by default. Not tested: a Draw Things generation running at the same time (never needed, the GPU lease allows one heavy job at a time), and final-size renders. Unload Ollama's model before a heavy job as already designed.

**Milestones (in order)**

1. **M1 Backbone:** repo, config, `doctor`, SQLite schema, job queue + GPU lease, mock backend, API skeleton, UI shell with project list and stage stepper.
2. **M2 Story:** story input, Ollama structuring with schema, YAML editor (form + Monaco), story versions and approval.
3. **M3 Cast:** Draw Things adapter, candidate grid, approval, cast library, reuse, mflux fallback.
4. **M4 Voice:** mlx-audio worker, voice setup (preset, clone), voice board with takes and approval, duration → shot length.
5. **M5 Frames and shots:** key frames via edits, product placement (AI mode), ltx-2-mlx adapter for action, talking and continue shots, shot board with re-roll and approval.
6. **M6 Assembly and player:** EDL, ffmpeg graph builder, captions, music ducking, export, player, basic timeline (order, trim, swap take).
7. **M7 Hardening:** staleness UI, resume after crash, offline acceptance test, Playwright flows, packaging (`reelforge` installable with `uv tool install`).
8. **v1.1:** full 4-track timeline, manual overlay canvas, voice design, character sheets, overnight queue, visual QA, caption/hashtag suggestions.

**Top technical risks**

| Risk | Signal | Response |
| --- | --- | --- |
| Draw Things API lacks edit mode or is unstable | S1 fails | Make mflux the primary image adapter; keep Draw Things for manual use |
| a2v lip sync weak on cartoon faces | S2 quality poor | Talking shots via i2v + a separate lip-sync pass (evaluate options), or more close-up, simpler faces |
| Memory contention between Draw Things and LTX | S4 shows OOM | Enable auto-quit of Draw Things before video stages |
| Upstream CLI churn | `doctor` flag check fails after an update | Pin commits; update deliberately behind a test render |
| Render times too long | NFR-4 missed | Draft-then-final workflow, overnight queue, optional cloud backend later |
