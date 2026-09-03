# Twitter/X extraction prompts (T-227)

The vendor-neutral passes in `prompts/` are written for a time-based medium: a
segment is a stretch of seconds, evidence is a time range, and coverage walks a
timeline. Two of the five do not survive that change of medium, and they are
replaced here rather than edited in place, so the YouTube workflow keeps reading
exactly as it does today.

| Pass | Twitter | Why |
|---|---|---|
| 1 — extraction | `01_post_extraction.md` | A post is the segment; a claim cites a post id and a codepoint span, and the excerpt must equal its span exactly |
| 2 — normalize/dedupe | *reuse* `prompts/02_normalize_deduplicate.md` | Nothing in it is time-based |
| 3 — relationships | *reuse* `prompts/03_relationships.md` | Edges relate unit ids, whatever medium the units came from |
| 4 — derived synthesis | *reuse* `prompts/04_derived_synthesis.md` | Derived units carry no locator at all |
| 5 — coverage audit | `05_item_coverage_audit.md` | Coverage is item-based: an enumerated set, not a continuous timeline |

The three-attempt repair cap is stated once in each pass 5 because it is the
same rule — CLAUDE.md and `WORKFLOW.md` state it, and `validators.py` enforces
it through one implementation for both coverage shapes.
