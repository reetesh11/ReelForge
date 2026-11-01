# Verify report: m2-story

**Result: PASS.** All executable checks passed (see checks.md). Findings are notes only.

## Pass 1: spec compliance (judged from code)
- AC-1 met. `story:structure` enqueues a `story.structure` job, which runs the LLM and saves a version through `service.save_version`. PUT moves the current flag onto the new row.
- AC-2 met. PUT and import share one `save` path. Invalid input returns 422 with field paths, and no row is written.
- AC-3 met. `yamlio` uses ruamel round-trip. The raw submitted text is stored and written to `story.yaml` unchanged.
- AC-4 met. `structure_story` makes the first call and then exactly one repair call that carries the errors. A second failure raises `AdapterError` before any save.
- AC-5 met. `diff_stories` is semantic and matches rows by id. Only changed scenes or characters get `StoryChange` rows. Stage returns to DRAFT. Stale items are computed per owner, so other scenes are untouched. A top-level change (style, fps and so on) marks everything, which is reasonable.
- AC-6 met. Import calls no LLM. Export returns `yaml_text.encode` of the current row.
- AC-7 met. Question paths are stripped from the draft and nothing is saved when gaps exist. The `suggested` flag is set server-side unless the user supplied dialogue, and it is cleared on save.
- AC-8 met by reading the code. The editor keeps a single `text` state. The Form view edits it through `draft.ts` helpers (comment-preserving), and the YAML view edits the same text. A web acceptance test exists.
- AC-9 met. The mock LLM is the default (`llm_backend: mock`), and the Ollama adapter takes a stub transport. Request shape is checked: `format`, temperature range 0.2-0.4, `keep_alive`. Health uses `/api/tags`, and chat refuses non-loopback URLs.
- AC-10 met. Unsafe tags are rejected, and `/story/schema` serves the JSON Schema.
- AC-11 and AC-12 (added in tests.json) are met. Approve is idempotent, returns 409 when there is no story or structuring is running, and the structural rules (4-8 scenes, duration, single-line look) trigger repair.

Nothing was built beyond the spec apart from small UX items such as the unsaved-changes guard and "Restore as new version". Both are consistent with the approved defaults.

## Pass 2: quality
- Architecture: the components and data flow match the tech.md diagram (routes, service, structure task, LLM protocol with mock and Ollama, web editor). No divergence found.
- Notes (see verify-review.json): duplicated StoryVersionOut construction and an api-to-jobs layering inversion in structure.py; no explicit lock on version numbering in save_version; an unlikely edge case in the stale computation when the previous version cannot be parsed.
- No security issues found. Safe YAML loading, a 1 MB body limit, UTF-8 validation and loopback-only Ollama are all in place.

## For the reviewer
The real-model quality of `qwen3:8b` structuring is out of scope and needs a manual check on the Mac.
