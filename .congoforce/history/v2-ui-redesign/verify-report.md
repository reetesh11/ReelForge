# Verify report: v2-ui-redesign

## Result
PASS. All code-checkable criteria are met; AC-20 (owner manual pass) and the AC-2a Playwright run are still open for the human.

## Acceptance criteria
| # | Criterion | Status | Evidence |
| --- | --- | --- | --- |
| AC-1 | Sidebar links and redirect | met | AppRoutes.tsx nav order; v2_shell.test.tsx |
| AC-2, AC-3, AC-4 | Rail links, landing stage, stage/screen params, locked fallback | met | workspace/stages.ts resolveStage/landingStage; StageStepper.tsx; v2_workspace.test.tsx |
| AC-5 | Navigation without reload | met | ProjectPage.tsx setParams; StageStepper onClick preventDefault |
| AC-6 | Next-up bar | met | NextUpBar.tsx |
| AC-7 | N of 6 header and bar | met | ProjectHeader.tsx, approvedCount |
| AC-8, AC-9 | CTAs and one per panel/Cast card | met | v2_cta.test.tsx, v2_cast.test.tsx, ctaRules.test.tsx |
| AC-10 to AC-12 | Story form, needs update, unsaved | met | FormView.tsx, StoryEditor.tsx; v2_story.test.tsx |
| AC-13, AC-13a | Cast tiles and icon buttons | met | CastRow.tsx, CandidateGrid.tsx; v2_cast.test.tsx |
| AC-14 | Status strips and chips | met | v2_boards.test.tsx |
| AC-15 | Project card mini rail | met | ProjectCard.tsx; v2_projects.test.tsx |
| AC-16, AC-17 | No hex outside tokens; contrast | met | noHexColours.test.ts, v2_theme.test.ts; grep of diff shows no colours outside theme.css |
| AC-18 | Reduced motion | met | theme.css:1211 (spinner excluded) |
| AC-19 | Frozen tests, build, lint | met | checks.md: 927 passed; frozen set intact; only owner-approved Cast test edits |
| AC-2a | Equal-width cells (Playwright) | met in code, not run | stage-rail.spec.ts not executed (ports busy); see manual item 4 |
| AC-20 | Manual check on reference Mac | not yet done | docs/manual-checks.md table is blank, owner action |

## Spec compliance
R37 holds: no change under web/src/api; routes only gain the `stage` query. Extras: the leave-guard also covers the next-up button (small, sensible). Key frames back button keeps "Back to voices" as the owner decided.

## Code quality
No blocking or major defects. Notes: landing stage is pinned at first load (ProjectPage.tsx:25), intentional. useDialog.ts handles Escape and focus return cleanly. Architecture: components match tech.md (ProjectHeader, StageStepper rail, NextUpBar, stages helpers, shared primitives).

## Recommendation
Ready for a human reviewer. Owner should complete the AC-20 manual table and run the stage-rail e2e with the app stopped.
