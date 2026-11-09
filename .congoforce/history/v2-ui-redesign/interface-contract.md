# Interface contract — v2-ui-redesign

Everything is under `web/`. Tests are vitest + RTL (`web/tests/acceptance/`) plus Playwright (`web/e2e/`). Import alias `@` = `web/src`.

### Pure helpers: `@/workspace/stages`
- `export type StageKey = "story" | "cast" | "voices" | "frames" | "shots" | "assembly"`
- `export const STAGE_KEYS: readonly StageKey[]` in that order.
- `export function landingStage(projectStage: Project["stage"]): StageKey` — DRAFT story; STORY_APPROVED cast; CAST_APPROVED voices; VOICES_APPROVED frames; FRAMES_APPROVED shots; SHOTS_APPROVED, REEL_EXPORTED, EXPORTED assembly.
- `export function resolveStage(params: URLSearchParams, projectStage: Project["stage"], stages: StageInfo[] | undefined): StageKey` — `stage` param wins over `screen`; a value not in `STAGE_KEYS`, or whose `StageInfo` has `locked: true`, yields `landingStage(projectStage)`. With `stages` undefined, only unknown values fall back.
- `export function waitingStage(stages: StageInfo[]): StageInfo | null` — first unlocked stage with state `needs_review`, `failed` or `stale`; else first unlocked stage not `approved`; else `null`.
- `export function approvedCount(stages: StageInfo[]): number` — count of state `approved`.
- `export function waitingReason(stage: StageInfo): string` — `"<label> needs review"`, `"<label> failed"`, `"<label> is stale"`, `"<label> not started"`, otherwise `"<label> <badgeText lowercased>"`.
- `StageInfo`, `badgeText(stage)` stay exported from `@/components/StageStepper` with the current behaviour.

### Routes and URL
- `/` still replaces to `/projects`. `/projects/<id>?stage=<StageKey>`; legacy `?screen=voices|frames|shots|assembly` still works. Landing stage is shown without rewriting the URL. No other route or API call changes.

### App shell (`@/AppRoutes` `AppRoutes`, rendered inside a Router and QueryClientProvider as today)
- `nav` with accessible name `Main`; links in order `Projects` (`/projects`), `Settings & status` (`/settings`), `Library` (`/library`); active has `aria-current="page"`. Brand text `ReelForge` inside the nav. Reconnect banner keeps `role="status"` and today's text.

### Project page (`@/routes/ProjectPage` `ProjectPage`)
- Breadcrumb: `nav` named `Breadcrumb` with link `Projects` (`/projects`) then the text `Project`. `h1` is the project title.
- Progress readout: text exactly `N of 6 stages approved` (absent until stages load) and an element `role="progressbar"` with `aria-valuenow=N`, `aria-valuemin=0`, `aria-valuemax=6`, whose fill child `data-testid="progress-fill"` has inline `style.width` = `N/6*100%` (3 gives `50%`).
- Rail: `ol` named `Stages`, six `li`. Unlocked `li` contains one `a` (href ends `?stage=<key>`); locked `li` has `aria-disabled="true"` and no `a`. Shown stage's `a` has `aria-current="step"`, no other. Each cell contains `[data-testid="stage-name"]` (bold name, icon `svg` or number in the same row, `title` = full label) and a separate `[data-testid="stage-state"]` with `badgeText` (e.g. `Rendering 42%`). Rail has class `stage-rail`; `li` cells have class `stage-cell`. Grid: six equal columns, gap at most 8 px.
- Panels: panel for the shown stage only, as `section` with `data-testid="stage-panel-<key>"` (absent from the DOM for other stages). Headings and texts inside are as today (Story editor, `Cast` heading, voice board, etc.).
- Next-up bar: element `data-testid="next-up"` containing `waitingReason` text and button named `Go to <label>` (e.g. `Go to Cast`); absent when the waiting stage equals the shown stage or nothing waits.
- Page-state messages keep exact text and tags/roles: `Loading...`, `Project not found.`, `Couldn't load this project.`, `This stage arrives in a later milestone.`, `Couldn't load the story.`; each in an element with class `state-message`.
- In-flow buttons keep names: `Continue to key frames`, `Continue to shots`, `Continue to assembly`, `Back to key frames`, `Back to Shots`; clicking pushes a history entry with the new `?stage=` and does not reload.

### Buttons and action bar
- Button levels are classes on the `button`: `btn btn-cta`, `btn btn-primary`, `btn btn-secondary`, `btn btn-ghost`, `btn btn-danger`; icon buttons add `btn-icon`.
- CTA names (class `btn-cta`; disabled exactly when today's precondition is unmet): `Approve story` (Story until approved, then `btn-secondary`), `Approve this one` (each Cast card), `Continue to key frames`, `Continue to shots`, `Continue to assembly`, `Export final`.
- Primary: `Generate candidates`, `Generate all lines`, `Generate all frames`, `Render all`, `Rebuild preview`, `Save` only while dirty. `Delete` is `btn-danger`.
- At most one `.btn-cta` per stage panel; in Cast at most one per character card (`[data-testid="cast-card"]`, class `card`, added in CastRow).
- Action bar: `data-testid="action-bar"` (class `action-bar`) inside the panel, containing the stage CTA. Story action bar shows the text `Unsaved changes` and `Save` has `btn-primary` while the YAML text differs from the saved story; otherwise neither (Save is `btn-secondary`). `Save your changes first` title text is unchanged.

### Story form
- Each character: `section` with `aria-label="Character <key>"`; each scene: `section` with `aria-label="Scene <id>"`. `Look`, `Action`, `Line` are labelled `textarea` showing the full text and auto-growing (no `rows` clipping). Field labels and YAML edits are exactly as before. `needs update` text appears only inside an element with class `card-header` (as `chip`). Settings summary is a read-only block that expands into today's editable fields (labels unchanged). Version selector label `Version`, tabs `tablist`/`tab` named `Form` and `YAML` unchanged. `Approved` banner text `Story approved. Editing it will mark dependent items for update.` has class `notice`.

### Cast
- Heading `Cast`; status strip `data-testid="status-strip"` with `N of M characters approved`. Candidate tiles are `button` with `aria-pressed` true/false, class `tile`, fixed square; the selected tile contains `[data-testid="check-badge"]` (only that tile).
- Icon buttons (each a `button` with accessible name = `title` = today's text, containing an `svg`): `Regenerate 4 more`, `Edit look text and regenerate`, `Refine selected (img2img)`, `Upload my own image`, `Use from library`, `Change approval`, `Replace from library`. `Approve this one` shows the visible word `Approve` plus an `svg`, `aria-label="Approve this one"`, disabled until a candidate is selected. `Generate candidates` keeps its text. The only visible-text buttons on a card are those two.
- Generating text `Generating image X of Y - N s elapsed` and `Cancel` unchanged, with a `role="progressbar"` bar.

### Voices, Key frames, Shots
- Status strip `data-testid="status-strip"` above the cards with the existing count texts (`N of M lines approved`, `N lines have no take yet` and the frame and shot equivalents). Each card has `[data-testid="state-chip"]` whose text equals the state label used today (Approved, Stale, Failed, Rendering, Not started, ...). Cards that need the person (failed, stale, needs review) carry `data-attention="true"`. Repeated card actions (play, regenerate, approve, reopen, delete) are icon buttons with `title` and `aria-label` equal to the names they have today.

### Assembly
- Layout: player column left, then timeline, captions and `Export` section (label kept) right. `Rebuild preview` is `btn-primary`; `Export final` is `btn-cta`.

### Projects, Library, Settings
- Project card (`li`): title link, text `N/6 stages approved`, `[data-testid="mini-rail"]` with six `[data-testid="mini-rail-segment"]`, each with `data-state` (`approved`, `waiting`, `not_started`) and a `title`. Heading `Projects`, list label, `No projects yet.` and skeleton test ids unchanged. `New project` is `btn-primary`.
- Settings: one status card per dependency with a dot and a word `Ready`, `Warning` or `Missing`; `Voice model` select label unchanged.

### Theme tokens (`web/src/theme.css`)
- `:root { ... }` is the light set; `@media (prefers-color-scheme: dark) { :root { ... } }` is the dark set. Both define exactly the same custom property names, including at least: `--bg --surface --surface-2 --border --text --muted --accent --focus --cta-from --cta-to --cta-text --green --amber --red --blue` and chip pairs `--chip-green-bg --chip-green-fg --chip-amber-bg --chip-amber-fg --chip-red-bg --chip-red-fg --chip-blue-bg --chip-blue-fg --chip-grey-bg --chip-grey-fg`, plus `--space-1..` `--radius-card` (12px), `--fs-12 --fs-14 --fs-16 --fs-20 --fs-28`, `--shadow-bar`. Colour token values are `#rrggbb` hex so tests can compute contrast.
- Contrast pairs asserted: `--text` on `--bg` and `--surface` at least 4.5; `--cta-text` on `--cta-from` and `--cta-to` at least 4.5; each chip fg on its bg at least 4.5; `--border`, `--focus` against `--surface` at least 3.
- One `@media (prefers-reduced-motion: reduce)` block sets `animation: none` and `transition: none` on all elements except the class `.spinner`, which keeps its rotation keyframes (name `spin`). No `@keyframes` other than `spin`, `pulse`, `shimmer`, `slide` exist; all non-spin ones are disabled in that block.
- No file under `web/src` other than `theme.css` (and `schema.d.ts`) contains `#rgb`, `#rrggbb`, `#rrggbbaa` or `rgb(`.

### Playwright (`web/e2e/stage-rail.spec.ts`)
- On a project page at 1440 px and 900 px wide: six `li` in `ol[aria-label="Stages"]` have widths equal within 1 px, gap at most 8 px, first left edge and last right edge equal the `ol` container edges within 1 px; each cell has name and state in separate elements; `Key frames` on one line.
