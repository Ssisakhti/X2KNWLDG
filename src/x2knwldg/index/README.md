# The SQLite index

Delivered by `T-101`–`T-104`, behind `repository.IndexRepository`. This is Track
A: it turns the canonical files under `output/` into pages of v1 records fast
enough to serve, and it is the only thing in the project allowed to keep a copy
of them.

```python
from pathlib import Path
from x2knwldg.index import SqliteRepository, build_index, refresh_index
from x2knwldg.index.search import document_indexer, search_retrieval

build_index(root, index_documents=document_indexer(root))   # or refresh_index
repo = SqliteRepository.open(root, search=search_retrieval)
repo.status().payload()["counts"]   # {"sources": 1, "artifacts": 85, ...}
```

| File | Holds |
|---|---|
| `errors.py` | What the store refuses: `StoreError`, `IndexCorrupt`, `SchemaTooNew`, `Fts5Unavailable` — inside the frozen D-030 taxonomy |
| `schema.py` | The DDL and the versioned migrations. The only module that writes `CREATE` |
| `scanner.py` | Discovery, per-run digests, incremental change detection, the build lifecycle. The only module that writes record rows |
| `search.py` | FTS5 candidate retrieval behind `query.rank_documents`, and the `documents` corpus |
| `repository.py` | `SqliteRepository` — the ten protocol methods. Writes nothing at all |
| `__init__.py` | The public surface |

Stdlib only: `sqlite3` ships with Python, so this package works on a bare core
install and its tests run in the zero-dependency CI job (ADR 0001 invariant 5).

## The one rule above the others: nothing exists only here

The index is a **rebuildable cache**. Canvas plan §5 invariant 5 and
[ADR 0001](../../../docs/adr/0001-local-web-ui.md) invariant 3 both say it:
nothing may exist only in `.x2knwldg/`, and deleting that directory must lose no
evidence, no canonical knowledge and no user content. Every number this package
reports is reproducible from the canonical files, so a stale count is a bug
rather than a data achievement.

That is a claim about behaviour, so it is a test.
`tests/test_sqlite_equivalence.py` (`T-104`) proves eight things over one tree,
comparing **page for page** — items element-wise and in order, `limit`, `total`
with `null` distinguished from `0`, and `next_cursor` as an exact token string:

1. a full `build_index` answers exactly what a cache-free `MemoryRepository` does;
2. `refresh_index` against no index at all, and against a migrated-but-empty
   one, reaches the same state as a full build;
3. a no-op refresh reports every run unchanged and changes no page;
4. one run's `knowledge_units.json` edited — refresh equals a from-scratch rebuild;
5. a run added — refresh equals a rebuild;
6. a run removed — refresh equals a rebuild, no orphaned record or search
   document survives, and `total` *falls*;
7. `output/library/` rebuilt on its own, changing no run — refresh equals a rebuild;
8. `.x2knwldg/` deleted entirely and rebuilt — equal to the original.

Token equality across two implementations is legitimate rather than lucky: the
cursor MAC key is per-process, so `page_from_window` mints identical tokens for
identical positions and a mismatch means the two disagree about the position or
about the record's content digest.

## Which module may write what

The division is not tidiness. Each boundary is a defect that cannot happen.

- **`schema.py` writes DDL and nothing else.** Canvas plan §9.4 requires
  migrations to be explicit and versioned, and the frozen
  `StatusPayload.index.index_version` is read from `MIGRATIONS` rather than
  typed beside it.
- **`scanner.py` writes record rows and nothing else** — and never touches
  `documents`, `document_tokens` or `documents_trigrams`. Keeping an
  external-content FTS5 index in step with its content table is `search.py`'s
  contract; half-populating it from here would leave a searchable corpus nobody
  owns. The hook is `DocumentIndexer`, called inside the scan's own transaction,
  and this module never imports `search`, so the two stay independently
  testable.
- **`search.py` owns the corpus**, including dropping the documents of a source
  the records no longer hold. Without that, a deleted run's hits would go on
  being returned for ever with `total` counting them — which is `T-104`
  scenario 6.
- **`repository.py` writes nothing** (ADR 0002 invariant 2). A reader that could
  write is a reader that can be made to disagree with the files.

## The storage shape, and why it looks under-normalised

**Records are stored verbatim as JSON.** ADR 0002 invariant 2 forbids the
repository supplying a value the canonical files do not carry, and the v1 records
are deliberately sparse: `Source.counts` omits a key whose file was unreadable
rather than zeroing it, and `adapter_metadata.unreadable_files` is absent rather
than empty when there is nothing to report. A normalised column per field would
have to choose a representation for every one of those absences, and every choice
would be an invention. So `doc` round-trips byte for byte and the API serialises
what the adapters produced.

**The extracted columns are not the filters.** ADR 0002 invariant 5 is explicit:
`matches_source`, `matches_entity`, `matches_relation` and
`relation_belongs_to_source` are the definition of each filter, and where a SQL
`WHERE` clause disagrees with them, they are right. `min_confidence` is the sharp
case — `matches_entity` fails a missing or non-numeric confidence on purpose ("a
unit that states no confidence is not confident enough"), while SQL's
`NULL >= 0.5` is `NULL`, which is not `false` and does not filter; and SQLite
sorts TEXT above every number, so a bare comparison *returns* an entity whose
confidence is the string `"high"`. The columns and the indexes over them narrow
candidates. The Python predicates decide.

**The order key is two columns, never one.** `repository.order_key` joins the
identity and the content digest with a NUL byte, so `identity` and `digest` are
stored separately and ordered as a pair — no NUL is ever handed to SQLite, and
`page_from_window` rebuilds the token from the record itself. The `PRIMARY KEY`
on `identity` is also the uniqueness the seam's README asks for: it makes the
order **total**, and a total order is what stops a tie across a page boundary
deleting a record from the paged output while `total` goes on counting it. That
is why `T-104` walks the whole filter space at `limit=1`.

`documents_trigrams` is an **external-content** FTS5 index over `documents`, so
the searchable text is stored once rather than twice. It is the only virtual
table in the schema — `document_tokens` is an ordinary one, and the only other
`USING fts5` in the package is the capability probe `connect` creates and drops
to find out whether this build of SQLite has the extension at all.

## Migrations are forward-only, appended and never edited

An edited migration is a schema that differs between two machines which both
report the same version, and nothing downstream could detect that. Adding a
column means adding a version, even when the old one has only ever run here.
`SCHEMA_VERSION` is derived from the last entry of `MIGRATIONS`; `migrate` is
idempotent, so it is safe on every open; a database *newer* than this code
raises `SchemaTooNew` rather than being read through a schema this code does not
understand — and the fix it names is deleting the cache, which is free precisely
because of the rule at the top of this file. `require_fts5` refuses a build on a
SQLite without FTS5, naming the interpreter, and `has_fts5` probes by creating a
table rather than by reading `PRAGMA compile_options`, which is empty on some
builds and therefore not evidence either way.

## The build lifecycle

`index_state` holds one row, and its `state` is one of `repository.INDEX_STATES`:
`absent`, `building`, `ready`, `error`. `building` is committed *before* any
work; every row of a scan is then written in one transaction that ends by
writing `ready` and `built_at`. So an interrupted build leaves the previous rows
intact and the state honest, no path writes `ready` over a half-full index, and
`refresh_index` refuses to be incremental against a state that never reached
`ready` — it does a full build instead. `status()` answers in every state;
everything else raises `IndexUnavailable`, because an empty index and an unbuilt
one are different answers (D-030).

A scan may be cheap, but it may never be quiet. Every run ends in exactly one of
four reported outcomes — indexed, unchanged, skipped, evicted — and `ScanReport`
carries the count of each beside the reason for every departure from the happy
path, in the two damage tiers D-043 established: `skipped_runs` for a run that
could not be indexed at all, `incomplete_runs` for one indexed with named gaps.
A run's digest covers its whole subtree rather than its `metadata.json`, because
a re-run rewrites `knowledge_units.json` and leaves the metadata untouched.
`output/library/` keeps a `runs` row of its own: it is not a run, but without the
row a `rebuild_library` that changed no run at all would leave the fragment as
the previous scan saw it — a stale answer arrived at cheaply. `T-104`
scenario 7 is that row.

One divergence is deliberate and worth knowing before comparing anything:
`adapt_project` refuses the **whole project** when one run is unmappable, while
this scanner skips that run and names it. Skip-and-name is right per D-043 — one
broken run must not cost a reader every other run — but it means that on a
*damaged* project the index is a named superset of what the `MemoryRepository`
oracle can produce. `strict=True` reproduces the refusal exactly, which is the
mode a page-for-page equivalence proof wants.

## Search: retrieval here, ranking in `query.py`

`SqliteRepository.search` pages over `search_retrieval`, which retrieves
candidates and hands them to `query.rank_documents` **unchanged**. That split is
the same move ADR 0002 invariant 5 makes for filters: the index narrows, the
Python function specifies. `bm25()` appears nowhere — it is a different ranking
function, and adopting it would reorder every result the CLI and the MCP tools
ship today and forfeit `T-104`'s equivalence, in exchange for a relevance model
nobody asked for.

Retrieval is subtler than "run the query through an FTS index", because
`SearchDocument.score` is two disjuncts: `score > 0` iff the query's tokens
intersect the document's **or** the folded query is a substring of the folded
text. Each disjunct needs its own index, and the obvious index for each is wrong.

**A `unicode61` FTS index is not `query._tokens`.** It splits on `_` where
Python's `\w+` does not, and it does not split scriptless CJK at all, while
`_tokens` expands a CJK run into single characters and adjacent bigrams.
Measured: for the query `機習` against `機械学習のモデル` the scorer returns
**0.667** — both characters are tokens of the document — while a `unicode61`
`MATCH` returns nothing *and* a trigram substring scan returns nothing, because
the two characters are not adjacent so no substring exists. Every such
disagreement is a silently missing hit. So `document_tokens` stores `_tokens`'s
own output verbatim, one row per token, and the overlap disjunct is exact by
construction instead of approximately right.

**`LIKE` is wrong outright, because `%` and `_` in a *user's* query are `LIKE`
wildcards.** A search for `100%` matched a document reading "growth was 100
percent", and `a_b` matched `axb` — hits the user never asked for.
`LIKE … ESCAPE` fixes the semantics and disables the trigram optimisation
entirely, dropping the plan from `INDEX 0:G0` to `INDEX 0:`. `GLOB` is
byte-exact, which is what is wanted here because both sides are already
NFKC-casefolded by `query._fold`, and it keeps the index once `*`, `?` and `[`
are escaped. Trigram `MATCH` is refused for a third reason: it silently returns
**zero rows** for a needle under three characters (`ai`, `機`), and absence
presented as a fact is the one thing this codebase refuses.

What the union buys, measured on the real sample (578 documents, 5083 token rows):

| query | token candidates | substring only | this union | oracle |
|---|---|---|---|---|
| `learning` | 3 | 1 | 4 | 4 |
| `model` | 10 | 9 | 19 | 19 |
| `the` | 162 | 91 | 253 | 253 |

The right two columns agree, which is the point: a token-only index would have
returned 3, 10 and 162 and said nothing about the rest.

## What is searchable, and what is deliberately not

The searchable field set is `query.run_documents`', and this package builds its
corpus from that function rather than re-deriving the list — so the two readers
cannot drift, and widening is one edit rather than two (D-046).

**`derivation_note` is indexed** (D-047). It earns that on one ground: a phrase a
reader can see in the Reader should be a phrase they can search for. Not on
recall — measured on the real sample it contributes **25** tokens no other field
holds, out of **1095**, and the word `the` moves 253 → 258. The accepted cost is
to precision: `derivation_note` is *derived* commentary about provenance, so a
domain term appearing only there ranks a unit for what the reasoning says rather
than for what the unit claims. That is why the list stops there.

Two things are not searchable, and neither is skipped for effort. Both are
**measured** to cost no reachable word, and both measurements are tests, so if
that stops being true the suite says so instead of the README going quietly
stale:

- **`context` is not indexed.** Every token it holds already appears in the
  unit's own `content` or `normalized_statement`: on the real sample, where 9
  units carry one, the set difference is **empty**. There is no query that
  indexing it would newly answer, so it would be cost without effect.
  `test_not_indexing_context_costs_no_reachable_word` is that measurement.
- **Segment text is not stored, and no `transcript_segment` hit shape exists.**
  A segment's `text` is byte-identically the concatenation of the captions it
  spans, and those are indexed, so segments add **zero** words of their own
  (`test_not_storing_segment_text_costs_no_reachable_word`). What a segment hit
  would change is the *granularity* of a result, not what can be found — and
  that is a question for the Reader, which can group captions by the
  `caption_ids` each segment already carries, rather than for the frozen
  contract. Minting the shape would be an `openapi.json` change first and a
  regenerated `types.d.ts` second (ADR 0002 invariant 3), widening Track B's and
  Track C's surface to make findable what is already findable (D-048).

A gap that used to be here has been closed:

- **A run the scanner *skipped* is named over HTTP** (D-050). It has a `runs`
  row with its reason and a `ScanReport.skipped_runs` entry, and it has no
  `Source` record — so it is in no page and in no count. `/api/status` therefore
  used to describe a project of two sources where three run directories existed,
  with nothing in the payload to say which reading was right. `StatusPayload`
  now carries an optional `runs` object — `discovered`, `indexed`, and the rest
  **named** in `skipped` with a reason, because "one run was skipped" is not
  actionable and "this directory, for this reason" is. It is optional in the
  schema so v1 stays additive, and unconditional here so a reader can tell
  "nothing was skipped" from "this server does not report it".
  `MemoryRepository` omits the field rather than claiming `skipped: []`, for the
  same reason it reports `index_version: null`: it has no scan to report.

  The reason itself is stored **project-relative** (D-051). `AdapterError` names
  the directory it refused and names it absolutely, which was unremarkable while
  the string only reached a CLI report and became a leak of the user's
  filesystem layout the moment it reached a response body (D-030, ADR 0003). It
  is sanitised where it is recorded, so there is one rule rather than a
  sanitiser at each boundary.

## Tests

| File | Asks |
|---|---|
| `tests/test_sqlite_schema.py` | Does the DDL hold what the seam needs, and does a migration ledger stay forward-only? |
| `tests/test_sqlite_scanner.py` | What does a scan report, what does it refuse, and what does it never write? |
| `tests/test_sqlite_search.py` | Is the ranked hit list the one `query.py` produces — for CJK, truncations, wildcards and FTS5 operators? |
| `tests/test_sqlite_repository.py` | Is the reader indistinguishable from `MemoryRepository`, item for item and token for token? |
| `tests/test_sqlite_equivalence.py` | Are a rebuild, an incremental refresh, and the canonical files the same answer? (`T-104`) |

All five are stdlib-only and run in the zero-dependency CI job. Every one of
them copies the committed fixtures into `tmp_path` first: no test in this
package writes to `tests/fixtures/` or to `output/`, and
`tests/test_sqlite_equivalence.py` proves it by comparing every canonical file's
size and `st_mtime_ns` afterwards.

## References

- [ADR 0001](../../../docs/adr/0001-local-web-ui.md) — the local web layer, its tracks and its invariants
- [ADR 0002](../../../docs/adr/0002-index-repository-seam.md) — the seam this package implements
- [ADR 0004](../../../docs/adr/0004-graph-membership-and-search-corpus.md) — graph membership and the search corpus
- [`src/x2knwldg/repository/README.md`](../repository/README.md) — the interface, endpoint by endpoint
- [`src/x2knwldg/adapters/README.md`](../adapters/README.md) — where the records come from
- [`schemas/api/v1/README.md`](../../../schemas/api/v1/README.md) — the frozen contract behind it all
