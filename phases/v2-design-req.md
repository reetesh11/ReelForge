# ReelForge v2.0 — UI redesign (workspace, stage rail, colour, readable config)

Binding inputs: `ReelForge — Product Spec.md` (the six stages and what each one means), `web/src/` as it stands (components, API hooks, tests). Requires M1 to M6b merged. This is a front-end-only change: no API, schema, database or job change. Out of scope: new product features, new stages, new API fields, a mobile app, i18n.

## Why
The current UI works but is hard to use:
- Every stage is stacked on one long page (Story, then Cast, then Voices). The stage stepper is not clickable, so moving between stages means scrolling.
- Every button looks the same, so the one action that matters (Approve, Continue) is lost among Save, Export and Import.
- The story config reads like a form: long full-width inputs, truncated text (`Look` is cut off), identical grey boxes for every scene, four identical buttons per card, and a full-width orange "needs update" bar.
- Colour is a single grey-blue on near-black; nothing tells you where you are, what needs you, or what is done.

## Inputs already decided (owner, 2026-11-05)
- **Stage rail:** horizontal, at the top of the project page.
- **Landing stage:** opening a project lands on the stage that is waiting for the person.
- **Theme:** follows the system setting (light or dark); no manual toggle.
- **Scope:** the whole UI (shell, project workspace, all six stages, Projects list, Library, Settings).
- **Colour:** one theme colour used with intent, so the UI is colourful but not noisy. Decided: **teal** (see Design tokens). Semantic colours stay separate from the theme colour.
- Existing accessible names, roles and test ids stay stable so the existing frozen web tests pass unchanged.

## Design principles
1. One stage in view at a time; the rest is one click away, never a scroll away.
2. One primary action per view, visibly the strongest thing on screen.
3. State is shown by icon and label as well as colour (accessible without colour vision).
4. Anything that needs the person (review, failed, stale) is surfaced, not buried.
5. Config is read first and edited second: it reads as content, and fields appear as fields only when edited.
6. Same vocabulary and components in every stage.

## Requirements

### Shell and navigation
- R1. **App shell:** a left sidebar with the ReelForge brand mark and name and the three links, in this order and with this exact text: `Projects`, `Settings & status`, `Library`. The active link is clearly marked. Page content is centred with a maximum width of about 1120 px. Below 900 px the sidebar becomes a top bar.
- R2. **Reconnect banner** keeps its `status` role and text and is restyled with the tokens.

### Project workspace
- R3. **Project header:** breadcrumb (`Projects / Project`, the first part a link), the project title as the `h1`, and an overall progress readout ("N of 6 stages approved") with a progress bar. N is the number of stages whose state is `approved`.
- R4. **Stage rail:** the existing `ol` labelled `Stages` with six `li` items stays (locked items keep `aria-disabled="true"`, each item's text still contains the stage label and the badge text from `badgeText`). The six items are equal-width cells that fill the full width of the content area (CSS grid, six equal columns, no gaps wider than 8 px; no empty space to the right). Inside each cell, two lines, left-aligned:
  - **Line 1:** the stage name in bold, with the state icon beside it (icon after the name, same line, vertically centred). The name never wraps onto the state text (`Key frames` stays on one line, shrinking or truncating with an ellipsis and a `title` rather than wrapping into line 2).
  - **Line 2:** the state value in smaller muted text (`Approved`, `Needs review`, `Rendering 42%`, `Not started`) on its own line, never run together with the name.
  - A cell is a link when the stage is not locked (the whole cell is the click target, no underline, no link-blue text); locked cells are plain and dimmed.
  - State icons: done (check), needs review (exclamation), rendering or queued (spinner glyph), stale (refresh), failed (cross), not started (the stage number). A rendering stage also shows a thin progress bar along the bottom edge of the cell.
  - The current stage cell is highlighted (theme-colour border and tinted background) and its link has `aria-current="step"`. Done cells get a green accent, needs-attention cells amber, failed red.
  - The rail stays pinned to the top of the viewport while the page scrolls. Below 900 px the cells keep a minimum width and the rail scrolls horizontally, keeping the current stage in view.
- R5. **One stage at a time:** the page shows only the selected stage. The selection is in the URL (`?stage=story|cast|voices|frames|shots|assembly`) so it can be linked and the browser back button works. The old `?screen=` values keep working. A stage that is locked cannot be opened by URL; the page shows the default stage instead.
- R6. **Landing stage:** with no `stage` in the URL the page opens on the stage that is waiting for the person. Rule, from the project stage: DRAFT → story, STORY_APPROVED → cast, CAST_APPROVED → voices, VOICES_APPROVED → frames, FRAMES_APPROVED → shots, SHOTS_APPROVED or later → assembly.
- R7. **Next-up bar:** when a different stage than the one on screen is waiting (first unlocked stage that is `needs_review`, `failed` or `stale`, otherwise the first unlocked stage that is not approved), a one-line bar says which stage and why, with a button `Go to <stage label>`. It is not shown when the waiting stage is the one on screen.
- R8. **Stage navigation inside the flow:** every Continue and Back action moves between stages by changing the URL (no full page reload), and the existing buttons keep their names (`Continue to key frames`, `Continue to shots`, `Continue to assembly`, `Back to key frames`, `Back to Shots`).
- R9. **Page states:** loading, not found (`Project not found.`), load failure (`Couldn't load this project.`), and the story messages (`Loading...`, `This stage arrives in a later milestone.`, `Couldn't load the story.`) keep their text and appear in a consistent state-message style.

### Action hierarchy
- R10. **Button levels:** five levels used everywhere: CTA (large, solid theme colour with a gradient, one per stage), primary (solid theme colour), secondary (outlined), ghost (text only), danger (red text, solid on hover). Repeated row-level actions use **icon buttons** (see R21a) instead of long text labels. Disabled buttons look disabled and, when the reason is not obvious, explain it (title or helper text; existing example: `Save your changes first`).
- R11. **One CTA per stage:** Story `Approve story`; Cast `Approve this one` on each character card, enabled once a candidate is selected (one CTA per card); Voices `Continue to key frames`; Key frames `Continue to shots`; Shots `Continue to assembly`; Assembly `Export final`. Generate-style actions (`Generate candidates`, `Generate all lines`, `Generate all frames`, `Render all`, `Rebuild preview`) are primary. Destructive actions (`Delete`) are danger. Import, Export story.yaml, Move up, Move down are ghost or secondary.
- R12. **Sticky action bar:** each stage that has a main action keeps it in an action bar that stays visible while scrolling (bottom of the viewport on the stage panel). The CTA is on the right, secondary actions on the left. Disabled-until-ready CTAs show why.

### Story stage
- R13. **Header:** story title, version selector (`Version`), and the estimated length as a chip. The `Versions` fold, `Export story.yaml` and `Import story.yaml` stay but are ghost-level; Form and YAML become a segmented toggle (roles `tablist` and `tab` unchanged).
- R14. **Approved state:** the `Story approved. Editing it will mark dependent items for update.` message is a calm info banner with an icon, not a bordered box. The `Approve story` button changes from CTA to secondary once the story is approved.
- R15. **Story settings** show as a compact read-first summary (language, visual style, aspect ratio, frames per second, target seconds) that opens into the editable fields; labels and field names are unchanged.
- R16. **Characters:** one card per character with an avatar initial, the name, the `@key`, and the stale chip; fields in a two-column grid; `Look` is a multi-line field that shows its whole text. Card actions (`Move up`, `Move down`, `Delete`) are a small toolbar with `Delete` separated and styled as danger. `Add character` is a dashed add-card.
- R17. **Scenes:** a numbered storyboard. Each scene card header shows the number, the setting, the `@speaker` and the duration. `Action` and `Line` are multi-line fields. A `suggested` scene shows an amber chip and an `Accept` button. Less-used options (`Framing`, `Product in shot`, `Continue from`, `End card`) are grouped in one row. Same toolbar as R16. `Add scene` is a dashed add-card.
- R18. **Needs update:** shown as a small amber chip in the card header (text `needs update`), never as a full-width bar.
- R19. **Unsaved changes:** the unsaved-changes guard and its message stay; a visible "Unsaved changes" indicator appears in the action bar while the text differs from the saved story. `Save` becomes primary only while there are unsaved changes.

### Cast stage
- R20. **Cast header:** `Cast` heading, a status strip "N of M characters approved", the licence banner and the backend-down panel in their current logic but in the notice styles of R30.
- R21. **Character card:** large master image (or candidate area) on the left; name, aliases, state chip, bible line, and age on the right. The age field and `Save age` sit together on one line. Candidates are a tile grid of fixed-size square tiles (not full-width rows). Selecting a candidate is done by clicking the tile itself: the selected tile gets a theme-colour outline and a check badge in its corner. There is no separate "select" control with text. The candidate area, its actions and the approval state are laid out in one compact block, not spread down the page.
- R21a. **Icon actions:** the Cast actions are icon buttons in one toolbar under the candidates, each with a tooltip (`title`) and an `aria-label` that keeps today's name so assistive technology and existing tests are unchanged: `Approve this one` (check icon plus the short visible word "Approve", the only CTA-styled button on the card; its accessible name stays `Approve this one`), `Regenerate 4 more` (refresh icon), `Edit look text and regenerate` (pencil icon), `Refine selected (img2img)` (wand icon), `Upload my own image` (upload icon), `Use from library` (library icon), `Change approval` and `Replace from library` on an approved card (undo and swap icons). Icons are inline SVG (no new dependency) drawn with `currentColor`, 18 to 20 px, in 36 px minimum touch targets. `Generate candidates` keeps its text because it is the first action on an empty card. The same rule applies to the repeated per-card actions on Voices, Key frames and Shots (play, regenerate, approve, reopen, delete): icon buttons with tooltips and `aria-label`s, with the one CTA per stage keeping its text.
- R22. **Generating state:** shows a progress bar with "Generating image X of Y - N s elapsed" (text unchanged) and the `Cancel` button.
- R23. **Voice setup** (shown on an approved character) keeps its behaviour inside a collapsible section within the card.

### Voices, Key frames, Shots
- R24. **Status strip:** each of the three boards shows a strip above the cards with counts (approved, stale, without take or frame) and the primary generate action; existing counts and texts (`N of M lines approved`, `N lines have no take yet`) stay.
- R25. **Cards:** each card has a state chip (approved green, stale amber, failed red, rendering blue, not started grey) in its header. Cards that need the person (failed, stale, needs review) have a highlighted edge. Within a board, cards keep scene order.
- R26. **Voices:** emotion picker, `Play all`, phrase gap, takes and the "How this will sound" panel keep behaviour; the audio player is styled and aligned with the tokens.
- R27. **Shots:** the queue panel is a compact side or top panel with the running job highlighted; `CompareTakes` shows takes side by side.

### Assembly stage
- R28. **Layout:** the player (9:16) on the left; timeline, captions and export panel on the right. `Rebuild preview` is primary, `Export final` is the CTA; the safe-zone overlay and licence dialog keep behaviour. The `Export` section keeps its label.

### Other pages
- R29. **Projects list:** cards (not bare rows) with the title as the link, a mini stage rail (six segments coloured by state), "N/6 stages approved", the edited time, and the stage waiting for the person as a chip. `New project` is a primary button; the `Projects` heading, the `Projects` list label, `No projects yet.` and the loading skeletons keep their text and test ids. **Library** is a card grid with the master image first. **Settings & status** shows each dependency as a status card with a coloured dot plus a word (Ready, Warning, Missing); `Voice model` select keeps its label.

### Design tokens and states
- R30. **Tokens:** all colours, spacing, radii, shadows and type sizes come from CSS custom properties on `:root` (defined once in `web/src/theme.css`, or files it imports). No raw colour values in component files. Notices (`info`, `success`, `warning`, `error`) share one component style with an icon.
- R31. **Colour:** theme colour **teal**, used for the active stage, links, focus rings, selection and the start of the CTA gradient; the CTA gradient runs from teal to a warm **coral** (clearly different from the amber attention colour and from green). Surfaces are lightly tinted with the theme hue (dark: deep blue-green near-black; light: cool off-white with a teal tint), not neutral grey. Semantic colours are separate and fixed in meaning: green = done, amber = needs attention, red = failed or destructive, blue = working or running. Green must be clearly distinguishable from teal (green yellow-leaning, teal blue-leaning) and the working colour is a true blue, not cyan, so it does not read as the theme colour. The theme colour is never used for a semantic meaning. Changing the theme colour means changing one token set.
- R32. **Light and dark** both ship, chosen by the system setting (`prefers-color-scheme`), both tuned (not an inversion). Text and key UI meet WCAG AA contrast (4.5:1 body text, 3:1 large text and UI parts) in both.
- R33. **Type and space:** body 14 to 15 px, a fixed scale (12, 14, 16, 20, 28), tabular numbers for timers, percentages and counts; 8 px spacing grid; card radius 12 px; borders over heavy shadows, with a soft shadow only on sticky bars and dialogs.

### Accessibility and behaviour
- R34. Every interactive element has a visible focus ring (2 px, theme colour). Colour is never the only carrier of state. `prefers-reduced-motion` turns off non-essential animation (spinners may stay but do not pulse or slide).
- R35. Keyboard: the stage rail, action bar and card toolbars are reachable in a logical tab order; the stage rail links work with Enter; no keyboard trap in dialogs, which close on Escape.
- R36. Layout holds from 360 px to 1920 px wide without horizontal page scroll (the stage rail may scroll within itself).
- R37. No change to data fetching, caching, WebSocket events, routes other than the `stage` query parameter, or API calls.

## Acceptance criteria
- AC-1: The sidebar links read `Projects`, `Settings & status`, `Library` in that order, and `/` still redirects to `/projects`.
- AC-2: On a project page the `Stages` list has six items; each unlocked item contains a link to `?stage=<key>`, locked items have `aria-disabled="true"` and no link; the item for the shown stage has `aria-current="step"` on its link.
- AC-3: Opening `/projects/<id>` with no `stage` shows the stage from the R6 table for each of the project stages DRAFT, STORY_APPROVED, CAST_APPROVED, VOICES_APPROVED, FRAMES_APPROVED, SHOTS_APPROVED, EXPORTED (and only that stage's panel is in the document).
- AC-4: `?stage=cast` shows only the Cast panel; `?stage=voices` only the Voices panel; the old `?screen=frames` still shows Key frames; a locked stage in the URL falls back to the R6 stage.
- AC-5: Clicking a stage link changes the shown panel without a full page load, and the browser Back button returns to the earlier stage.
- AC-6: The next-up bar shows when the waiting stage differs from the shown stage, names that stage, and its button navigates to it; it is absent when they match.
- AC-7: The header reads "N of 6 stages approved" where N is the count of approved stages from the stages data, and the progress bar width matches N/6.
- AC-8: Each of the six CTAs in R11 exists with the button name stated there and carries the CTA style class; it is disabled while its precondition is unmet (existing preconditions unchanged).
- AC-9: Only one element per stage panel carries the CTA style class; in Cast the rule is one per character card (each card has at most one).
- AC-10: In the Story form each character and scene renders as a labelled section (`Character <key>`, `Scene <id>`); `Look`, `Action` and `Line` are multi-line fields (`textarea`) and show their full text; editing any field still updates the YAML exactly as before.
- AC-11: A stale character or scene shows the `needs update` chip inside its card header; no element outside a card header shows that text.
- AC-12: While the draft differs from the saved story the action bar shows "Unsaved changes" and `Save` has the primary style; when equal, neither.
- AC-2a: Each stage cell has exactly two text lines: the stage name (bold) with the icon in the same row, and the state value in a separate element below; the six cells have equal width and together span the full width of the content area at 1440 px and 900 px (checked in the browser run, e2e).
- AC-13a: In Cast, every action in R21a is a button whose accessible name equals the previous visible text, has a `title`, and contains an `svg` rather than the long text; the only visible text button besides `Generate candidates` is none. Clicking a candidate tile selects it and shows the check badge.
- AC-13: Cast: the selected candidate tile is marked (`aria-pressed` or equivalent state, unchanged from today) and visually outlined; `Approve this one` is disabled until a candidate is selected.
- AC-14: Voices, Key frames and Shots boards show the status strip with the counts, and each card shows a state chip whose text matches its state.
- AC-15: Projects list: each project card shows the six-segment mini rail and the "N/6 stages approved" text; the heading, list label, empty text and skeleton test ids are unchanged.
- AC-16: Tokens: no component file under `web/src` (outside the token file) contains a hex colour or `rgb(`; checked by a test or lint rule.
- AC-17: Light and dark token sets both define every token; text on surface and on CTA meets the AA ratios (checked by a unit test over the token values).
- AC-18: With `prefers-reduced-motion: reduce`, no CSS animation other than the spinner glyph rotation remains (test over the CSS or a manual check).
- AC-19: Every existing frozen web test (`web/tests`, `web/e2e` where run) passes unchanged, and `pnpm build`, `pnpm lint` and `pnpm test` pass.
- AC-20: Manual check on the reference Mac, recorded in `docs/manual-checks.md`, in light and dark, at 1440 px and 390 px wide, with a project at DRAFT, STORY_APPROVED, CAST_APPROVED and SHOTS_APPROVED: the owner confirms (a) the current stage and the waiting stage are obvious at a glance, (b) the CTA is the first thing the eye finds, (c) the stage rail reads at a glance (name and state on separate lines, icon beside the name, full width), the Cast icons are understandable from the icon and tooltip alone, (d) the Story config is readable without opening a field, (e) the colour feels lively and not noisy.

## Out of scope
- New features, new stages, new API fields; changing what any stage does.
- A manual theme toggle, user-chosen theme colours, brand-kit theming of the app.
- Redesigning the player's internals or the Monaco YAML editor beyond theming it with the tokens.
- Animations beyond hover, focus and progress.

## Decided by the owner (2026-11-05)
- Horizontal stage rail; landing on the stage waiting for the person; system theme; whole UI in one change.
- One theme colour, more colourful than today.

## Open questions
- None. Theme colour (teal, with a coral CTA accent), one CTA per Cast card, and shipping as one change were all settled by the owner on 2026-11-05.
