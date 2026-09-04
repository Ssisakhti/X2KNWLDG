# Test-only Twitter run fixtures

Eight run directories, one per case `T-227` planned, each holding the input
`capture.json` and its `raw/` evidence beside the canonical extraction outputs
the pipeline wrote from them.

**The captures and their raw evidence are real measured bytes. The knowledge
units are not real extraction.** Each `metadata.json` carries `"fixture": true`
and a `fixture_note` saying so, and each unit is a mechanical quotation — the
post's own opening, cited by the span it was taken from. No report, answer or UI
may present a unit here as an analytical claim about a real post. The captures
themselves cannot carry that marker: the contract's root is
`additionalProperties: false`, which `tests/capture_shapes.py` explains at
length.

## The cases

| Case | Input capture | `validation.json` | `coverage.json` | What it prevents |
|---|---|---|---|---|
| `single-post` | `pass-single-post-en` | `PASS` | `PASS` | The baseline: a claim carrying a post id, a codepoint span and an excerpt that re-slices exactly |
| `persian-rtl` | `pass-single-post-fa` | `PASS` | `PASS` | 418 characters of ZWNJ, Persian digits, a NBSP and paragraph breaks. Normalization or trimming on the excerpt path breaks the re-slice *here and nowhere else* |
| `persian-rtl-ltr-run` | `pass-single-post-fa-video` | `PASS` | `PASS` | The bidi case with an embedded LTR `t.co` link, and the only media with **no** `alt_text`: nothing may claim to know what the video shows |
| `self-thread` | `pass-thread-terminal-anchor` | `PASS` | `PASS` | Root-first over ten items from `parent_links`, first item with no `parent_post_id`. Order derived from parent links, never arrival order |
| `partial-thread` | `partial-thread-dangling-chain` | `PARTIAL` | `PARTIAL` | A truncated chain presented as though it began at a root. Both items are audited and cited, and the run is still `PARTIAL`: the audit being complete and the capture being complete are different claims |
| `edit` | `capture_shapes.edited_post_capture()` | `PASS` | `PASS` | An edit history read as content, or the prior ids fetched |
| `tombstone` | `fail-unavailable-post` | `FAIL` | `PARTIAL` | Zero source claims and nothing invented from an item with no author, timestamp or text — and `FAIL` surviving into the canonical outputs |
| `quote` | `pass-quote-post` | `PASS` | `PASS` | A quoted post becoming embedded content or a fetch. It stays an external reference in `metadata.json` (ADR 0007 decision 8) |

Two of these read differently from the plan that ordered them, and the fixtures
follow the code and the decision records rather than the plan's earlier wording:

- **`edit`.** §11 says the prior ids are "named omitted". D-224 settled
  otherwise: `edits` holds prior version ids on the item, and *a prior version
  is not an expected item*. So they are named on the item and appear nowhere
  else — not as items, not as coverage entries, not as external references, and
  never fetched. That is what the fixture pins.
- **`partial-thread`.** §11 also calls it "the tombstone-inside-a-thread shape".
  The measured capture (D-221) is a dangling chain whose *excluded* member is a
  third-party parent, which is a different and equally important shape. No
  committed capture holds an unavailable post inside a multi-item thread; the
  tombstone case covers the unavailable post on its own.

`tombstone` is the awkward one on purpose, and it is this directory's
counterpart to `runs/fail-run`: `knowledge_units.json`, `relationships.json` and
`coverage.json` all exist and are internally consistent, the audit is honest,
and the run is `FAIL` because the capture under it is. A reader that infers
status from "the files are there" will pass its tests against the other seven
and lie about this one.

## Why they are committed

The same reason `tests/fixtures/runs/` exists: `output/` is gitignored, so a
test that needs a real Twitter run on disk would otherwise skip on every machine
but the one that acquired it — a green suite proving nothing. These eight are
always present, and `T-228` has canonical outputs to project without acquiring
anything.

## Layout

This directory **is the output root**, and `tests/fixtures/` is the project root
the runs are expressed against, so a capture here records its evidence as
`twitter-runs/<case>/raw/<file>`. `extract.evidence_integrity` resolves those
paths against `run_dir.parent.parent` — one rule, with no parameter for "where
the project root is", because a second root-resolution rule is what D-039
removed. A run one level deeper, under an `output/` directory of its own the way
a real run sits, would also have been invisible to git: `.gitignore` excludes
`output/` at any depth, deliberately, to keep real evidence out of the
repository.

The evidence bytes are the committed ones, **re-homed and not rewritten**: each
`raw_evidence` entry keeps the `sha256_raw` and `sanitization_removed` its
capture recorded, its `sha256_sanitized` is recomputed from the copied file, and
a mismatch fails the build. `sha256_raw` is carried rather than recomputed
because it is a claim about the bytes the provider returned *before*
sanitization, and those bytes were never committed.

A Twitter run stops at `validation.json`. There is no `report.md`, `graph.json`
or vault export here, because `artifacts.finalize_run` reads a transcript and
segments and no Twitter equivalent exists yet — `T-228` owns the read surfaces.

## Regenerating

```bash
.venv/bin/python tests/fixtures/twitter-runs/build_fixtures.py
```

The builder drives the real code — `initialize_run`, then
`apply_extraction_bundle`, then `validate_run` — so a fixture cannot drift from
what the pipeline actually writes. Hand-written expected JSON is exactly what
would let it (`T-006`, D-157). Re-running it must leave `git status` clean, and
`test_twitter_run_fixtures.py` asserts that by rebuilding every case into a
temporary directory and comparing the bytes.
