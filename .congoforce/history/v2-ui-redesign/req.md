---
class: feature
size: large
title: ReelForge v2.0 UI redesign (workspace, stage rail, colour, readable config)
---
# Requirements — ReelForge v2.0 UI redesign

## Problem
The current web UI stacks all six stages on one page, has an unclickable stage stepper, gives every button the same look, and shows story config as a long form of grey boxes. People cannot tell where they are, what needs them, or which action matters. This change redesigns the whole front end (shell, project workspace, six stages, Projects list, Library, Settings) with one-stage-at-a-time navigation, a clear action hierarchy and a teal/coral token-based light and dark theme. It is front-end only. Full detail is in the source file `phases/v2-design-req.md` (R1 to R37), which is binding for exact texts, names and layout numbers.

## Requirements
Numbering follows the source file; each line is one behaviour.
- R1. The system shall render a left sidebar (top bar below 900 px) with brand mark and the links `Projects`, `Settings & status`, `Library` in that order, active link marked, content centred at max about 1120 px.
- R2. The reconnect banner shall keep its `status` role and text and use tokens.
- R3. The project page shall show breadcrumb, `h1` title, and "N of 6 stages approved" with a progress bar, N being stages in state `approved`.
- R4. The existing `ol` labelled `Stages` shall render six equal-width grid cells (gap at most 8 px, full width) each with name plus state icon on line 1 and state text on line 2; unlocked cells are links, locked cells keep `aria-disabled="true"`; current cell has `aria-current="step"`, highlight, and the rail is sticky and scrolls horizontally below 900 px.
- R5. When `?stage=<key>` (or legacy `?screen=`) is present and unlocked, the page shall show only that stage; if locked, the page shall show the R6 default stage.
- R6. When no stage is in the URL, the page shall open on: DRAFT story, STORY_APPROVED cast, CAST_APPROVED voices, VOICES_APPROVED frames, FRAMES_APPROVED shots, SHOTS_APPROVED or later assembly.
- R7. While a different stage than the one shown is waiting, the system shall show a one-line next-up bar with button `Go to <stage label>`; otherwise not.
- R8. Continue and Back actions shall navigate by URL change without full reload, keeping existing button names.
- R9. Loading, not-found, load-failure and story state messages shall keep their text in one consistent style.
- R10. The system shall provide five button levels (CTA, primary, secondary, ghost, danger), icon buttons for repeated row actions, and explained disabled states.
- R11. Each stage shall have exactly the CTA named in the source (`Approve story`, `Approve this one` per Cast card, `Continue to key frames`, `Continue to shots`, `Continue to assembly`, `Export final`); generate actions primary; `Delete` danger; Import, Export story.yaml, Move up, Move down ghost or secondary.
- R12. Each stage with a main action shall keep it in a sticky action bar, CTA right, secondary actions left.
- R13 to R19. Story stage: header with version selector, length chip, segmented Form/YAML; calm approved banner and `Approve story` becomes secondary once approved; read-first settings summary; character cards and numbered scene storyboard with multi-line `Look`, `Action`, `Line`; `needs update` only as card-header chip; "Unsaved changes" indicator in action bar and `Save` primary only when dirty.
- R20 to R23. Cast stage: header and status strip; character card with large image, fixed-size square candidate tiles selected by click (check badge, outline); R21a SVG icon buttons with `title` and `aria-label` equal to today's names; progress bar for generating state; collapsible voice setup.
- R24 to R27. Voices, Key frames, Shots: status strip with counts, per-card state chips, highlighted edge for cards needing the person, styled audio player, compact queue panel, side-by-side `CompareTakes`, icon buttons for repeated card actions.
- R28. Assembly shall lay out the 9:16 player left, timeline/captions/export right; `Rebuild preview` primary, `Export final` CTA.
- R29. Projects list shall use cards with mini six-segment rail and "N/6 stages approved"; Library a card grid; Settings status cards with dot plus word.
- R30 to R33. All colour, spacing, radius, shadow and type values shall come from CSS custom properties in `web/src/theme.css`; teal theme colour, coral CTA gradient, fixed semantic colours; light and dark by `prefers-color-scheme`, WCAG AA; type scale 12/14/16/20/28, 8 px grid, 12 px card radius.
- R34 to R36. Visible 2 px focus rings, reduced-motion support, logical keyboard order, Escape closes dialogs, no horizontal page scroll from 360 to 1920 px.
- R37. The system shall not change data fetching, caching, WebSocket events, API calls or routes other than the `stage` query parameter.

## Acceptance criteria
Taken from the source file, ids kept as written there so later stages map one to one.
- AC-1: Sidebar links read `Projects`, `Settings & status`, `Library` in order; `/` still redirects to `/projects`.
- AC-2: On a project page the `Stages` list has six items; unlocked items contain a link to `?stage=<key>`, locked items have `aria-disabled="true"` and no link; the shown stage's link has `aria-current="step"`.
- AC-3: `/projects/<id>` with no `stage` shows the R6 stage for DRAFT, STORY_APPROVED, CAST_APPROVED, VOICES_APPROVED, FRAMES_APPROVED, SHOTS_APPROVED, EXPORTED, and only that panel is in the document.
- AC-4: `?stage=cast` shows only Cast; `?stage=voices` only Voices; `?screen=frames` still shows Key frames; a locked stage in the URL falls back to the R6 stage.
- AC-5: Clicking a stage link changes the panel without a full page load; browser Back returns to the earlier stage.
- AC-6: The next-up bar shows when the waiting stage differs from the shown one, names it, and its button navigates there; absent when they match.
- AC-7: Header reads "N of 6 stages approved" (N from stages data) and progress bar width equals N/6.
- AC-8: Each R11 CTA exists with the stated name and the CTA style class, and is disabled while its existing precondition is unmet.
- AC-9: At most one CTA-class element per stage panel; in Cast at most one per character card.
- AC-10: Story form renders each character and scene as a labelled section (`Character <key>`, `Scene <id>`); `Look`, `Action`, `Line` are `textarea` showing full text; edits update the YAML exactly as before.
- AC-11: A stale character or scene shows `needs update` inside its card header; no element outside a card header shows that text.
- AC-12: While the draft differs from the saved story the action bar shows "Unsaved changes" and `Save` has primary style; when equal, neither.
- AC-2a: Each stage cell has two text lines (bold name with icon in the same row; state value in a separate element below); six equal-width cells span the content width at 1440 px and 900 px (Playwright e2e).
- AC-13a: In Cast every R21a action is a button whose accessible name equals today's text, has a `title`, contains an `svg`; clicking a candidate tile selects it and shows the check badge.
- AC-13: Cast selected tile keeps its pressed state and is outlined; `Approve this one` is disabled until a candidate is selected.
- AC-14: Voices, Key frames, Shots show the status strip with counts, and each card a state chip whose text matches its state.
- AC-15: Each project card shows the six-segment mini rail and "N/6 stages approved"; heading, list label, empty text and skeleton test ids unchanged.
- AC-16: No component file under `web/src` outside the token file contains a hex colour or `rgb(` (test or lint rule).
- AC-17: Light and dark token sets define the same tokens; text on surface and on CTA meets 4.5:1 and large text/UI parts 3:1 (unit test over token values).
- AC-18: Under `prefers-reduced-motion: reduce`, no CSS animation remains except spinner rotation.
- AC-19: All existing frozen web tests (`web/tests`, `web/e2e` where run) pass unchanged; `pnpm build`, `pnpm lint`, `pnpm test` pass.
- AC-20: Manual check on the reference Mac, recorded in `docs/manual-checks.md`, light and dark, 1440 px and 390 px, projects at DRAFT, STORY_APPROVED, CAST_APPROVED, SHOTS_APPROVED; owner confirms items (a) to (e) of the source file.

## Out of scope
- New features, stages or API fields; any API, schema, database or job change.
- Manual theme toggle, user-chosen or brand-kit theme colours, mobile app, i18n.
- Redesigning player internals or the Monaco editor beyond token theming.
- Animations beyond hover, focus and progress.

## Assumptions
- The source file `phases/v2-design-req.md` is the detailed spec; this req.md summarises it and does not weaken it. It is currently untracked in git and must be committed with the task.
- In AC-13a, "Approve this one" keeps the visible word "Approve" next to its icon (per R21a); the "no other visible text button" clause means no other text buttons besides `Generate candidates` and that CTA.
- Test ids and accessible names not listed stay as they are today; if a frozen test conflicts with a requirement, it is revised through Gate 2, not hand-edited.
- `web/src/theme.css` already exists and is extended rather than replaced by a new file.
- Size is large (about 40 component files across all pages), although the owner chose one change; the split below is a suggestion for implementation loops, not a change to scope.

## Suggested split
Each part keeps the existing frozen tests green and is shippable alone (the later parts reuse the earlier tokens and components).
1. Foundation: tokens and light/dark themes (R30 to R34, AC-16 to AC-18), button levels, notices, app shell, reconnect banner, Settings and Projects list and Library restyle (R1, R2, R10, R29, AC-1, AC-15).
2. Workspace: project header, stage rail, `?stage=` routing, landing stage, next-up bar, in-URL Continue/Back, sticky action bar (R3 to R9, R12, AC-2 to AC-7, AC-2a).
3. Story and Cast: R13 to R23, R11 CTAs for those stages (AC-8 to AC-13a for Story and Cast).
4. Voices, Key frames, Shots, Assembly: R24 to R28, remaining CTAs and chips (AC-14, AC-9), then final AC-19 and AC-20 checks.

## Open questions
- None. The input records that theme colour, one CTA per Cast card and shipping as one change were settled by the owner on 2026-11-05. The owner may still choose to ship via the split above because the size is large.
