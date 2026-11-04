# Acceptance test plan — ReelForge v2.0 UI redesign

## Coverage
| Criterion | File | Test names | Red because |
| --- | --- | --- | --- |
| AC-1 | `web/tests/acceptance/v2_shell.test.tsx` | sidebar order/hrefs/brand/active; `/` redirect | brand text not in nav, no active mark check passes today only for redirect (green part) |
| AC-2 | `web/tests/acceptance/v2_workspace.test.tsx` | rail links, current marker, stage-name/stage-state | rail items are not links, no `aria-current`, no testids |
| AC-3 | same | per-project-stage landing (8 cases), helper keys and `landingStage` | `@/workspace/stages` and `stage-panel-*` do not exist; page stacks all stages |
| AC-4 | same | `?stage=`, `?screen=` aliases, precedence, locked/unknown fallback, `resolveStage` | no `stage` param support, no panel testids |
| AC-5 | same | link click, Enter, Continue/Back buttons, history Back | no links; `Back to voices` still uses `screen` |
| AC-6 | same | next-up absent/present/navigate/failed, `waitingStage`, `waitingReason` | no `next-up` element, helpers missing |
| AC-7 | same | breadcrumb, h1, `N of 6`, progressbar and fill width, no readout on stages error, `approvedCount` | none of these elements exist |
| AC-2a | `web/e2e/stage-rail.spec.ts` | 1440 and 900 px geometry | no `stage-name`/`stage-state`, cells not an equal grid |
| AC-8 | `web/tests/acceptance/v2_cta.test.tsx` | six CTAs with class and preconditions, Approve story secondary after approval, Delete danger | no `stage-panel-*`, no `btn-*` classes, no `cast-card` testid |
| AC-9 | same | one CTA per panel and per Cast card, generate actions primary | same |
| AC-10 | `web/tests/acceptance/v2_story.test.tsx` | sections, textareas with full text, YAML edit | Look/Action/Line are `input` today (edit test is green) |
| AC-11 | same | chip only inside `.card-header` | chip sits in `Card` outside a header |
| AC-12 | same | Unsaved changes and primary Save toggling | no `action-bar`, no indicator |
| AC-13a | `web/tests/acceptance/v2_cast.test.tsx` | icon buttons, visible-text buttons, empty card, approved card, check badge | no `cast-card` testid, text buttons, tiles are `li`/radio |
| AC-13 | same | `button.tile` aria-pressed, Approve gating | tiles have no `aria-pressed` |
| AC-14 | `web/tests/acceptance/v2_boards.test.tsx` | Voices, Key frames, Shots strip and chips | no status-strip/state-chip/data-attention |
| AC-15 | `web/tests/acceptance/v2_projects.test.tsx` | mini rail, New project primary, skeleton/empty (green) | no mini rail |
| AC-16 | `web/tests/acceptance/v2_theme.test.ts` | scan of `web/src` | components contain hex values today |
| AC-17 | same | same token names, contrast per set | dark set is `:root`, light is in media; tokens missing |
| AC-18 | same | reduced-motion block, keyframe names | no such block, no `spin` keyframes |
| AC-23 | `web/tests/acceptance/v2_shell.test.tsx` | banner (green), five state messages in `.state-message` | plain `<p>` today |

Shared fixtures: `web/tests/acceptance/v2_helpers.tsx` (not a test file).

## Approach
Tests render `AppRoutes` in a `MemoryRouter` with the existing `stubFetch` helper and read only the public surface from the interface contract (testids, classes, roles, labels). A small probe component next to the app exposes the location and a `navigate(-1)` button to check client-side navigation and history Back. Stage panels are located by `data-testid="stage-panel-<key>"`. AC-16 to AC-18 parse `web/src/theme.css` with a brace scanner; the contrast maths was checked against known values (black on white 21, #777 on white 4.48). AC-2a is a Playwright spec using the project API like the existing e2e specs.

Notes on fairness:
- Cast tiles are found with `button.tile` (contract), not by role, so the old `radio` role is not asserted either way.
- The "only visible-text buttons" test ignores `Save age` (R22 keeps it on the card).
- Voice, frame and shot chip labels use today's wording (`Needs update`, `No take yet`, `No frame yet`, `No shot yet`).
- Frozen tests that conflict with the contract (role `radio` on tiles, `Select`/`Enlarge`/`Compare` text buttons, `Back to voices`) will need a Gate 2 revision; I did not touch them.

## Untestable criteria
- AC-19: regression gate; the full check run covers it.
- AC-20: manual check on the reference Mac.
- AC-21, AC-22, AC-24: need real layout, focus and visuals; covered by the manual pass (focus colour contrast is in AC-17).

## Open questions
- Frozen M-series tests use `role="radio"` and `aria-checked` on candidate tiles and text `Select`/`Enlarge` buttons; the contract says `button.tile` with `aria-pressed`. Which wins for the frozen cast tests (revise at Gate 2)?
