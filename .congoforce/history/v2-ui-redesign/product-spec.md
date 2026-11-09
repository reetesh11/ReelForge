# Product spec — ReelForge v2.0 UI redesign (workspace, stage rail, colour, readable config)

Binding detail for exact texts, names and layout numbers is `phases/v2-design-req.md` (R1 to R37), copied at `.congoforce/tasks/v2-ui-redesign/input.md`. This spec does not weaken it. Front-end only: no API, schema, job, data-fetching, caching, WebSocket or route change other than the `stage` query parameter (R37).

## User-facing behaviour

### Today (for reference)
- `web/src/AppRoutes.tsx`: a plain `nav` ("Main") with `Projects`, `Settings & status`, `Library`; `/` redirects to `/projects`.
- `web/src/routes/ProjectPage.tsx`: `h1` plus `StageStepper` (not clickable), then Story, Cast and the later screens stacked on one page; `?screen=frames|shots|assembly` (and none = Voices) selects the later screens. Messages: `Loading...`, `Project not found.`, `Couldn't load this project.`, `This stage arrives in a later milestone.`, `Couldn't load the story.`.
- `web/src/theme.css`: dark grey-blue tokens with a light variant; hex values scattered in components.

### App shell
- A left sidebar shows the ReelForge brand mark and name, then the links `Projects`, `Settings & status`, `Library` in that order. The active link is visibly marked (not by colour alone: e.g. weight plus an indicator bar). The nav keeps its `Main` label.
- Content is centred, max width about 1120 px. Below 900 px the sidebar becomes a top bar with the same links in the same order.
- The reconnect banner keeps its `status` role and its text, restyled as a notice with tokens.

### Project workspace
- **Header:** breadcrumb `Projects / Project` (`Projects` is a link to `/projects`), the project title as the `h1`, and the text "N of 6 stages approved" with a progress bar. N is the number of stages whose state is `approved`; bar fill is N/6 of the track width. While stages data has not loaded, the readout is not shown (no "0 of 6" flash).
- **Stage rail:** the existing `ol` labelled `Stages`, six `li` cells in a six-column grid (gap at most 8 px), filling the full content width, no empty space on the right. Each cell has two left-aligned lines:
  - Line 1: stage name in bold, state icon after the name on the same row, vertically centred. The name never wraps into line 2; if too narrow it truncates with an ellipsis and a `title` carrying the full name (`Key frames` stays on one line).
  - Line 2 (separate element): state value in small muted text: `Approved`, `Needs review`, `Rendering 42%`, `Not started` (and the existing `badgeText` wording for other states, e.g. stale, failed, queued).
  - The cell text still contains the stage label and the `badgeText` text.
  - Unlocked cell: the whole cell is a link to `?stage=<key>`; no underline, no link-blue text. Locked cell: plain, dimmed, `aria-disabled="true"`, no link.
  - Icons: approved = check; needs review = exclamation; rendering or queued = spinner glyph; stale = refresh; failed = cross; not started = the stage number (1 to 6). A rendering stage also shows a thin progress bar along the cell's bottom edge.
  - Current (shown) stage: theme-colour border and tinted background; its link has `aria-current="step"`. Approved cells have a green accent, needs-attention amber, failed red.
  - The rail is sticky at the top of the viewport while scrolling. Below 900 px cells keep a minimum width, the rail scrolls horizontally inside itself, and the current cell is scrolled into view.
- **One stage at a time:** only the selected stage's panel is in the document. Stage keys: `story`, `cast`, `voices`, `frames`, `shots`, `assembly`. The legacy `?screen=` values keep working as aliases. Selection by `stage` takes precedence over `screen` if both are present. A locked or unknown stage value shows the default stage (R6) and the page does not error.
- **Landing stage (no `stage`/`screen` in URL):**

  | Project stage | Shown |
  |---|---|
  | DRAFT | Story |
  | STORY_APPROVED | Cast |
  | CAST_APPROVED | Voices |
  | VOICES_APPROVED | Key frames |
  | FRAMES_APPROVED | Shots |
  | SHOTS_APPROVED, REEL_EXPORTED, EXPORTED | Assembly |

  The landing stage is shown without rewriting the URL.
- **Next-up bar:** one line under the rail, shown only when the waiting stage differs from the shown stage. Waiting stage = first unlocked stage that is `needs_review`, `failed` or `stale`; otherwise the first unlocked stage that is not approved. Copy: the stage name and the reason (e.g. "Cast needs review", "Shots failed", "Voices not started") and a button `Go to <stage label>` (e.g. `Go to Cast`). Pressing it changes the URL to that stage without a reload. Hidden when the waiting stage is the shown one, or when every unlocked stage is approved.
- **In-flow navigation:** `Continue to key frames`, `Continue to shots`, `Continue to assembly`, `Back to key frames`, `Back to Shots` keep their names and move between stages by changing the URL (history entry added, no full reload). Browser Back returns to the previous stage.
- **Page states:** `Loading...`, `Project not found.`, `Couldn't load this project.`, `Loading...`, `This stage arrives in a later milestone.`, `Couldn't load the story.` keep their exact text and share one state-message style (centred card or inline notice with icon for errors; `Loading...` muted). Roles stay as today.

### Action hierarchy
- Five button levels: CTA (large, solid teal-to-coral gradient, one per stage), primary (solid teal), secondary (outlined), ghost (text only), danger (red text, solid red on hover). Repeated row actions are icon buttons (36 px minimum target, 18 to 20 px inline SVG in `currentColor`, `title` and `aria-label`).
- Disabled buttons look disabled. When the reason is not obvious they explain it by `title` or helper text (existing: `Save your changes first`; the CTAs show why they are not ready).
- CTA per stage: Story `Approve story`; Cast `Approve this one` (one per character card; visible text "Approve" with a check icon, accessible name `Approve this one`); Voices `Continue to key frames`; Key frames `Continue to shots`; Shots `Continue to assembly`; Assembly `Export final`.
- Primary: `Generate candidates`, `Generate all lines`, `Generate all frames`, `Render all`, `Rebuild preview`, and `Save` while dirty. Danger: `Delete`. Ghost or secondary: `Import story.yaml`, `Export story.yaml`, `Move up`, `Move down`, the `Versions` fold.
- **Sticky action bar:** each stage with a main action has a bar pinned to the bottom of the viewport within the stage panel (soft shadow). Secondary actions left, CTA right. When the CTA is disabled, the reason is visible beside it or in its `title`.

### Story stage
- Header: story title, `Version` selector, estimated length as a chip; `Versions` fold, `Export story.yaml`, `Import story.yaml` are ghost; Form and YAML are a segmented toggle (roles `tablist` / `tab` unchanged).
- Approved: the message `Story approved. Editing it will mark dependent items for update.` is a calm info banner with an icon, no bordered box. `Approve story` is CTA before approval and secondary after.
- Settings: a compact read-only summary of language, visual style, aspect ratio, frames per second, target seconds; it opens into the editable fields with unchanged labels and field names.
- Characters: one labelled section per character (`Character <key>`): avatar initial, name, `@key`, stale chip; two-column field grid; `Look` is a multi-line textarea showing the whole text. Toolbar `Move up`, `Move down`, `Delete` (Delete separated, danger). `Add character` is a dashed add-card.
- Scenes: numbered storyboard, one labelled section per scene (`Scene <id>`). Header: number, setting, `@speaker`, duration. `Action` and `Line` are textareas. A `suggested` scene shows an amber chip and an `Accept` button. `Framing`, `Product in shot`, `Continue from`, `End card` in one row. Same toolbar. `Add scene` is a dashed add-card.
- Needs update: amber chip with the text `needs update`, only inside the card header.
- Unsaved changes: the guard and its message are unchanged. When the draft differs from the saved story the action bar shows "Unsaved changes" and `Save` is primary; otherwise neither the indicator nor primary styling (Save is then secondary or disabled as today).

### Cast stage
- Header: `Cast` heading, status strip "N of M characters approved", licence banner and backend-down panel (same logic) as notices.
- Character card: large master image or candidate area at left; name, aliases, state chip, bible line, age at right. Age input and `Save age` on one line.
- Candidates: grid of fixed-size square tiles. Click a tile to select: theme-colour outline plus check badge in its corner, `aria-pressed` as today. No separate text "select" control.
- Toolbar of icon buttons under the candidates, each with `title` and `aria-label` equal to today's name, containing an `svg`:

  | Name | Icon |
  |---|---|
  | `Approve this one` | check, plus visible word "Approve" (the CTA) |
  | `Regenerate 4 more` | refresh |
  | `Edit look text and regenerate` | pencil |
  | `Refine selected (img2img)` | wand |
  | `Upload my own image` | upload |
  | `Use from library` | library |
  | `Change approval` (approved card) | undo |
  | `Replace from library` (approved card) | swap |

  `Generate candidates` keeps its text (primary) on an empty card. `Approve this one` is disabled until a candidate is selected.
- Generating: progress bar with "Generating image X of Y - N s elapsed" (text unchanged) and `Cancel`.
- Voice setup on an approved character sits in a collapsible section inside the card, behaviour unchanged.

### Voices, Key frames, Shots
- A status strip above the cards with counts and the primary generate action; existing texts stay (`N of M lines approved`, `N lines have no take yet`; equivalents for frames and shots).
- Each card header has a state chip: approved green, stale amber, failed red, rendering blue, not started grey. Text matches the state. Cards needing the person (failed, stale, needs review) have a highlighted edge (plus the chip, so not colour alone). Cards stay in scene order.
- Repeated card actions (play, regenerate, approve, reopen, delete) are icon buttons with `title` and `aria-label`; the stage CTA keeps its text.
- Voices: emotion picker, `Play all`, phrase gap, takes and the "How this will sound" panel behave as today; the audio player is token-styled.
- Shots: compact queue panel (side or top) with the running job highlighted; `CompareTakes` shows takes side by side.

### Assembly stage
- 9:16 player at left; timeline, captions, `Export` section (label kept) at right. `Rebuild preview` primary, `Export final` CTA. Safe-zone overlay and licence dialog behave as today. Below 900 px the two columns stack, player first.

### Other pages
- **Projects:** `Projects` heading and list label, `No projects yet.` and skeleton test ids unchanged. Each project is a card: title as link, mini rail of six segments coloured by state, "N/6 stages approved", edited time, chip for the stage waiting for the person. `New project` is primary.
- **Library:** card grid, master image first.
- **Settings & status:** one status card per dependency with a coloured dot plus a word (`Ready`, `Warning`, `Missing`); `Voice model` select keeps its label.

### Theme, type, accessibility
- All colour, spacing, radius, shadow and type values come from CSS custom properties in `web/src/theme.css` (extended, not replaced). Light and dark both ship via `prefers-color-scheme`; no manual toggle.
- Teal is the theme colour (active stage, links, focus, selection, CTA gradient start); CTA gradient teal to coral. Surfaces are tinted teal-leaning (dark: deep blue-green near-black; light: cool off-white). Semantic colours fixed: green done (yellow-leaning), amber needs attention, red failed or destructive, blue working (true blue). Teal is never used for a semantic meaning.
- Type scale 12 / 14 / 16 / 20 / 28 px, body 14 to 15 px, tabular numbers for timers, percentages, counts. 8 px grid. Card radius 12 px. Borders over shadows; soft shadow only on sticky bars and dialogs.
- Notices (`info`, `success`, `warning`, `error`) share one style with an icon.
- 2 px theme-colour focus ring on every interactive element; reduced-motion turns off all animation except spinner rotation; logical tab order (rail, panel, action bar); Escape closes dialogs; no horizontal page scroll from 360 to 1920 px (rail may scroll internally).

## Acceptance criteria

- AC-1: The sidebar `nav` lists, in DOM and visual order, links with exact text `Projects`, `Settings & status`, `Library`, with `href`s `/projects`, `/settings`, `/library`; the active one is marked (`aria-current="page"` via NavLink plus a visual mark). Visiting `/` replaces the URL with `/projects`.
- AC-2: On `/projects/<id>` the `ol` named `Stages` has exactly six `li`. Each unlocked `li` contains an `a` whose `href` ends in `?stage=<key>` (keys `story`, `cast`, `voices`, `frames`, `shots`, `assembly`). Each locked `li` has `aria-disabled="true"` and contains no `a`. The `a` of the shown stage has `aria-current="step"`; no other link has it.
- AC-3: `/projects/<id>` with no `stage`/`screen` shows only the panel from the R6 table for projects at DRAFT (Story), STORY_APPROVED (Cast), CAST_APPROVED (Voices), VOICES_APPROVED (Key frames), FRAMES_APPROVED (Shots), SHOTS_APPROVED (Assembly), EXPORTED (Assembly; REEL_EXPORTED likewise). The panels of the other five stages are not in the document at all (not merely hidden). The URL is not rewritten.
- AC-4: `?stage=cast` shows only Cast; `?stage=voices` only Voices; `?screen=frames` shows only Key frames (`?screen=shots`, `?screen=assembly` likewise; `?screen=voices` shows Voices). A locked stage, or an unknown value, in `stage` or `screen` shows the R6 stage for the project's stage.
- AC-5: Clicking an unlocked stage link updates the URL query and swaps the panel with no document reload (client-side navigation; app state such as the SSE connection persists). Browser Back restores the previous URL and panel. Enter on a focused link behaves the same as click.
- AC-6: With a waiting stage W different from shown stage S, the next-up bar is present, contains W's label and reason, and has a button named `Go to <W label>` that navigates to `?stage=<W key>`. When W equals S, or nothing is waiting, the bar and button are absent from the DOM.
- AC-7: The header text is exactly "N of 6 stages approved" with N = count of stages with state `approved` in the stages data (0 to 6). The progress bar exposes `role="progressbar"` with `aria-valuenow` N, `aria-valuemax` 6, and its fill width is N/6 of the track (e.g. 3 gives 50%).
- AC-8: Buttons with these exact accessible names exist in their stage panel and carry the CTA style class: `Approve story` (Story, until approved; after approval it carries secondary style, not CTA), `Approve this one` (each Cast card), `Continue to key frames` (Voices), `Continue to shots` (Key frames), `Continue to assembly` (Shots), `Export final` (Assembly). Each is disabled exactly when its existing precondition is unmet (e.g. `Approve this one` with no selected candidate); preconditions are not changed. A disabled CTA gives its reason by `title` or adjacent text when the reason is not obvious.
- AC-9: In each stage panel at most one element has the CTA class. In Cast, each character card has at most one, and the panel may therefore have several (one per card). Generate-style actions use the primary class, never CTA.
- AC-10: In the Story form every character is a section with accessible name `Character <key>` and every scene a section named `Scene <id>`. `Look`, `Action`, `Line` are `textarea` elements whose value is the full untruncated text and whose height grows to show multi-line text without clipping. Editing any field updates the YAML text byte-for-byte as the current implementation does.
- AC-11: A stale character or scene shows the text `needs update` in a chip inside its card header. The string `needs update` appears nowhere outside a card header (no banner, no full-width bar).
- AC-12: While the draft text differs from the saved story the action bar shows the text "Unsaved changes" and `Save` has the primary class. When draft equals saved, the indicator is absent and `Save` is not primary. The unsaved-changes guard message is unchanged.
- AC-2a: Each stage cell has exactly two text lines: the bold stage name with its icon in the same row, and the state value in a separate element below it. At viewport widths 1440 px and 900 px the six cells have equal widths (within 1 px), the gap is at most 8 px, and together they span the full width of the content area (first cell left edge and last cell right edge equal the rail container's edges within 1 px). Verified by Playwright e2e.
- AC-13a: In Cast every action in the table above is a `button` whose accessible name equals today's text, has a non-empty `title` and contains an `svg`. The only visible-text buttons on a card are `Generate candidates` and `Approve this one` (visible word "Approve"). Clicking a candidate tile selects it and shows the check badge on that tile only.
- AC-13: The selected candidate tile has `aria-pressed="true"` (as today) and the theme-colour outline; unselected tiles have `aria-pressed="false"`. `Approve this one` is disabled until a candidate is selected, enabled after.
- AC-14: Voices, Key frames and Shots each show a status strip above the cards with counts (approved, stale, without take or frame) and keep existing count texts (`N of M lines approved`, `N lines have no take yet`). Each card has a header chip whose text equals its state label (Approved, Stale, Failed, Rendering, Not started, as the board uses today); needs-the-person cards also have the highlighted edge.
- AC-15: Each project card shows a mini rail of six segments (colours by state, with a text or `title`/accessible equivalent so state is not colour-only) and the text "N/6 stages approved". The `Projects` heading, the `Projects` list label, `No projects yet.` and the loading skeleton test ids are unchanged.
- AC-16: A test or lint rule fails if any file under `web/src` other than `web/src/theme.css` (and files it imports) contains a hex colour (`#rgb`, `#rrggbb`, `#rrggbbaa`) or `rgb(`. Existing component hex values are migrated to tokens.
- AC-17: In `web/src/theme.css` the light and dark token sets define exactly the same token names. A unit test computes contrast: body text on surface and bg at least 4.5:1; CTA label on every stop of the CTA gradient at least 4.5:1; large text and UI parts (borders of controls, focus ring, chips' text per its background) at least 3:1 for UI parts and 4.5:1 for small chip text; in both light and dark.
- AC-18: Under `prefers-reduced-motion: reduce`, the only CSS animation that remains is the spinner glyph rotation; transitions and other keyframe animations (pulse, slide, skeleton shimmer) are off. Verified by a test over the CSS or a manual check.
- AC-19: All existing frozen tests in `web/tests` (and `web/e2e` where run) pass unchanged. `pnpm build`, `pnpm lint`, `pnpm test` pass. A frozen test that conflicts with a requirement is changed only through Gate 2, never edited in place.
- AC-20: Manual check on the reference Mac, written up in `docs/manual-checks.md`, in light and dark, at 1440 px and 390 px, for projects at DRAFT, STORY_APPROVED, CAST_APPROVED, SHOTS_APPROVED. The owner confirms: (a) current stage and waiting stage obvious at a glance; (b) the CTA is the first thing the eye finds; (c) the stage rail reads at a glance (name and state on separate lines, icon beside the name, full width) and the Cast icons are understandable from icon and tooltip alone; (d) Story config readable without opening a field; (e) colour feels lively and not noisy.

New ids implied by the requirements (not in req.md; added because the behaviour is stated there):
- AC-21: (R35) In the stage rail, action bar and card toolbars, Tab order follows visual order (rail, panel content, action bar); no keyboard trap; every open dialog closes on Escape and returns focus to its opener.
- AC-22: (R36) From 360 px to 1920 px wide the document has no horizontal scroll on any page; only the stage rail may scroll horizontally inside itself below 900 px.
- AC-23: (R2, R9) The reconnect banner keeps `role="status"` and its text; the six page-state messages keep their exact text.
- AC-24: (R34) Every interactive element shows a 2 px theme-colour focus ring on keyboard focus; state is never colour only (each state has an icon or word).

## Edge cases and errors
- Stages data loading or failed: the header shows the title and breadcrumb but no "N of 6" readout, rail or next-up bar; the stage shown falls back to the R6 stage from `project.stage`. Only the Story `Loading...` message etc. as today.
- Project not found / load failure: only the page-state message, no rail or header.
- `story === null` at DRAFT: Story panel shows `StoryInput` as today; `Approve story` is not offered there.
- Both `stage` and `screen` present: `stage` wins.
- Unknown `stage` value, or a locked one, shows the R6 stage without error; the current cell still gets `aria-current="step"`.
- A project changes stage while open (e.g. approval): the unlocked set updates; if the shown stage becomes locked, the page shows the R6 stage. The next-up bar updates.
- Rendering stage with unknown percent: state text `Rendering` with no number; no cell progress bar width of 0 fake value.
- 360 px: sidebar becomes top bar, rail scrolls inside itself, cards stack to one column, action bar stays reachable with CTA not hidden.
- Long names (project title, character name, stage label): truncate with ellipsis and `title`, no layout break.
- Cast: a card with zero candidates shows only `Generate candidates` (primary); no CTA is enabled; the card has no more than one CTA in all states.
- Unsaved Story draft and the user clicks a stage link: the existing unsaved-changes guard and message apply as today to stage navigation away from Story.
- Dark and light must both keep chip and notice text legible; colour blindness: every state carries icon or word.

## Out of scope
- New features, stages, API fields; any API, schema, database or job change; changing what any stage does.
- Manual theme toggle, user-chosen or brand-kit theme colours, mobile app, i18n.
- Redesigning player internals or the Monaco editor beyond token theming.
- Animations beyond hover, focus and progress.

## Open questions
- Does the unsaved-changes guard (R19) also cover leaving Story via the stage rail (it is a URL change within the same route), or only the existing leave triggers? This spec assumes it covers any navigation away from Story that it covers today and asks tech-spec to confirm what "today" includes.
- Exact label per state in chips and rail beyond `Approved`, `Needs review`, `Rendering N%`, `Not started` (stale, failed, queued): this spec assumes the existing `badgeText` wording is reused. Confirm.
