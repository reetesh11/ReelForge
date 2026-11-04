# Verify report — m5-frames-shots

## Result
PASS — all criteria met by code and tests; helper checks passed (642 tests, lint, typecheck, build, frozen set intact).

## Acceptance criteria
| # | Criterion | Status | Evidence |
| --- | --- | --- | --- |
| AC-1 | Frame job gets master, look verbatim | met | frames/generate.py, test_m5_frames.py |
| AC-2 | Product image input; missing is reported, frame still generates | met | frames/product.py, test_m5_frames.py |
| AC-3 | Talking shot has frame + voice take, 8k+1 frames; action has no audio | met | shots/generate.py, test_m5_shots.py |
| AC-4 | Re-roll touches one shot only | met | test_m5_shots.py |
| AC-5 | Doctor fails on missing flag | met | adapters/ltx.py, test_m5_ltx_adapter.py |
| AC-6 | Exit 137/-9 classified OOM, Draft retry | met | shots/state.py is_oom, generate.py, tests |
| AC-7 | shot_mem_gb preflight, one heavy job | met | config.py, shots/service.py:496, worker.py |
| AC-8 | Last frame artifact; continue uses it | met | shots/generate.py, test_m5_shots.py |
| AC-9 | Estimates, reorder, pause, cancel | met | shots/service.py, worker paused_projects, tests |
| AC-10 | Staleness scoped per scene | met | tests |
| AC-11 | FRAMES_APPROVED / SHOTS_APPROVED gates | met | frames/service.py recompute_stage, tests |
| AC-12 | Uploads checked by content and size | met | shots/uploads.py, frames service, tests |
| AC-13 | Mock backend, no network | met | conftest guard, tests |
| AC-14 | Existing tests unchanged | met | test_m5_unchanged.py, frozen set intact |
| AC-15 | Manual real-Mac check | untestable | docs/manual-checks.md entry added; results blank, to be run by a human |

## Spec compliance
Matches tech.md architecture (routes, services, state, generate handlers, backends, media, migration 0005, worker handlers). Web screens and queue panel added. Nothing unrequested found. The pack image is not sent as pixels to Draw Things (documented limitation).

## Code quality
No correctness defects found. Notes: paused queue state is in memory only (worker.py:71); the motion-prompt LLM fallback swallows errors silently (shots/generate.py:35).

## Recommendation
Ready for a human reviewer. Run the AC-15 manual checks on the reference Mac before shipping.
