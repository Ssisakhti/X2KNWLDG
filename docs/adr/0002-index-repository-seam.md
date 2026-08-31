# ADR 0002 — The index repository, and the seam between the indexer and the API

- **Status:** Accepted
- **Date:** 2026-08-31
- **Decision ledger:** D-031 … D-036 (`KNOWLEDGE_CANVAS_PLAN.md` §19)
- **Supersedes:** none
- **Superseded by:** none

## Context

[ADR 0001](0001-local-web-ui.md) chose a local web layer over the existing
pipeline and a four-track execution model. `PROJECT_MANAGEMENT.md` §8.2 states
what makes three of those tracks genuinely concurrent: Track C never waits on
Track B because the API contract is frozen and TypeScript types are generated
from it, and **"Tracks A and B meet only at the repository interface fixed in
`T-007`."** That interface did not exist. This ADR is it.

The edges were already fixed by earlier tasks, and this decision is mostly a
matter of not inventing anything new at a seam that four prior decisions already
constrain:

- **`T-002`** put the record shapes in `schemas/v1/`, and **`T-004`** made
  `adapters` the only way to produce them. `IndexRecords.by_model()` is the shape
  on both sides already.
- **`T-005`** froze eleven `GET` endpoints in `schemas/api/v1/openapi.json`,
  every response body `$ref`-ing `schemas/v1/`. It also fixed the paging envelope
  (`PageInfo` with an **opaque** `next_cursor`), the index states (`absent`,
  `building`, `ready`, `error`), and the error taxonomy (D-030).
- **`T-006`** committed labelled `PASS` / `PARTIAL` / `FAIL` run fixtures, so a
  repository can be tested against a `FAIL` run rather than only a healthy one.
- **D-020** requires that a run directory be resolved by
  `pipeline.resolve_run_dir`, which **rejects** an unsafe id rather than
  sanitising it.

**Verified before deciding (2026-08-31).** `adapt_project` over the real sample
produces 1 source, 85 artifacts, 86 entities, 118 relations. Of the 118
relations, **17 carry `source_id: null`** — the `expresses_concept` edges
`adapt_library` produces, which belong to no single run (D-025). Of the 86
entities, **17 carry `source_id: null`** — the cross-source concepts (D-016).
Every entity in the sample is touched by at least one edge, but nothing in the
model guarantees that, and the `PARTIAL` fixture shows what a sparse run looks
like. These three facts decide most of what follows.

Risk **R18** was also open: D-028's additive search fields (`global_id`,
`source_id`) existed only as `_as_api_hit` in `tests/test_api_contract.py` — a
reference implementation no server would ever call, which proved the frozen
shape *reachable* without making anything reach it.

## Decision

1. **The seam is `IndexRepository`**, a `Protocol` in
   `src/x2knwldg/repository/base.py`. Track B calls it and opens no database, no
   canonical file, and no run directory. Track A implements it and imports no
   route. It lives beside `adapters/` rather than inside `index/` or `server/`,
   because a contract owned by one of the two tracks that share it is not a
   contract. *(D-031)*
2. **It returns pages of v1 records, not rows.** Every list method returns a
   `Page` of the plain dicts the adapters already produce. Ten methods serve the
   eleven endpoints; `/api/media` reuses `get_artifact`, because two ways to
   reach a file would be two places to get path traversal wrong. *(D-031)*
3. **The cursor encoding belongs to the repository**, is shared by every
   implementation through `encode_cursor`/`decode_cursor`, and is **bound to the
   query that issued it**. Changing a filter refuses the cursor; changing only
   `limit` does not, because a keyset position does not depend on page size.
   *(D-032)*
4. **Absence is a return value; malformation is an exception.** `InvalidId`,
   `InvalidQuery`, and `IndexUnavailable` carry the `code` and `http_status` of
   D-030, so the API renders the refusal it is handed rather than choosing one.
   A well-formed id naming nothing returns `None`; `404` is what a route makes
   of that. *(D-033)*
5. **A relation belongs to a source when the source produced it, or when either
   endpoint is an entity of that source.** *(D-034)*
6. **A graph page is a page of nodes, with the edges among them** — not a page
   of edges. *(D-035)*
7. **`MemoryRepository` ships with the seam** as the reference implementation
   over `adapters.adapt_project`, and D-028's additive search fields move into
   it, closing R18. *(D-036)*

## Alternatives considered

| Alternative | Why rejected |
|---|---|
| A repository row type of its own (`SourceRow`, `EntityRow`, …) | A third vocabulary for the same fact, on top of the two identifier vocabularies R12 already tracks. `IndexRecords.by_model()` is what the schemas validate and what the API serialises; anything between them is a place to drift (D-026) |
| Put the interface in `src/x2knwldg/index/` | §8.2 gives Track A exclusive ownership of that directory. Track B would then depend on a file only Track A may edit, and the seam would move whenever the indexer refactored |
| Let the API hold the SQL and skip the repository | Then the index has no interface, `T-104`'s rebuild-equivalence test has nothing to compare against, and Track B cannot start until Track A finishes — which is the serialisation §8.2 exists to avoid |
| Offset pagination everywhere | A record inserted before the offset shifts every later page and silently skips a record. Keyset paging over a total order does not. Search is the one place offsets remain, because a relevance rank is not a stable key — stated in the docstring rather than hidden |
| A cursor the API can parse (e.g. a plain id) | The contract calls it opaque. The moment a route or the frontend reads it, the encoding is frozen by accident and FTS5 (`T-103`) cannot change how search pages without a contract change |
| Re-anchor a cursor presented with different filters | It would return a page of a collection the client never asked for, and it would look like data rather than like an error |
| Raise `NotFound` for a well-formed id naming nothing | Absence is an ordinary answer about the user's data; an exception is a refusal of the request. Conflating them is how "no sources yet" gets presented as an error, and vice versa |
| Filter a source's relations on `source_id` alone | It would drop the 17 `expresses_concept` edges, which name no run. A Reader would show a source without the links it makes to the concepts it expresses |
| Page the graph over edges | An entity with no relations would never appear on any page, so a full walk of `/api/graph` would silently lose real records — and the Map would never show them |
| Include an edge when *either* endpoint passes the node filter | The edge would dangle to a node the filter excluded, and a Map that draws a dangling edge asserts a node it will not show |
| Ship the interface with no implementation | Track B would have nothing to run against until `T-101`–`T-104` land, and `T-104` would have no cache-free oracle to prove equivalence against |
| Make `MemoryRepository` the production index | It re-reads every run on construction and re-runs `query.search_knowledge`'s linear scan per search. That is exactly the cost `T-103` exists to remove |

## Consequences

**Positive**

- Tracks A and B become genuinely concurrent: B builds routes against
  `MemoryRepository` today, A replaces it behind the same interface.
- `T-104` gets an oracle with no cache at all. A rebuilt index, an incrementally
  updated one, and the canonical files must all produce the same pages; where
  they differ, the index is stale (ADR 0001 invariant 3).
- D-030 stops being prose. `InvalidId.http_status == 400` is a test, not a
  convention a route can forget.
- R18 closes: the additive search fields are served by the code the tests
  exercise, and the source type is read from the indexed source rather than
  assumed to be `youtube`.
- The seam is stdlib-only, so it runs on a bare core install (ADR 0001
  invariant 5) and the contract tests over it run in the zero-dependency CI job.

**Negative / accepted costs**

- Ten methods are now a surface `T-101`–`T-104` must implement in full before
  the SQLite path can serve anything. That is the cost of the endpoints being
  frozen first, and it is paid once.
- `MemoryRepository` holds every record in memory. Fine at 86 entities;
  not a library-scale strategy, and it says so.
- Search pagination is offset-based, so a run finalised between two pages can
  shift the ranking under the cursor. Stated in the docstring rather than
  designed around, because the cursor is opaque and `T-103` can change it.
- A graph edge that straddles two node pages appears on both. Clients dedupe by
  `id`.

**Neutral**

- `MemoryRepository` reports `index_version: null` and `built_at: null`. It has
  no persisted index, and stating a version would claim a durable artifact that
  does not exist.
- The `library:concepts` namespace matches the endpoint membership rule like any
  other source id, which costs nothing: no `Source` record exists for the
  library, so a route 404s before it lists anything.

## Invariants this decision must preserve

1. **The API reads nothing but the repository.** No route opens a canonical
   file, a run directory, or the database. `/api/media` streams the `path` a
   record already carries, through `T-108`'s single safety check.
2. **The repository is a reader.** It never writes a canonical file, never
   recomputes a status, and never supplies a value the canonical files do not
   carry. `PARTIAL` and `FAIL` pass through untouched (ADR 0001 invariant 2).
3. **No implementation widens the interface.** An endpoint that needs something
   `IndexRepository` cannot express is a change to
   `schemas/api/v1/openapi.json` first, and to this interface second.
4. **The cursor stays opaque outside the repository.** Nothing in `server/` or
   `web/` parses one.
5. **`matches_entity`, `matches_relation`, `matches_source`, and
   `relation_belongs_to_source` are the definition of each filter.** Where a
   SQL `WHERE` clause disagrees with them, they are right.
6. **Records handed out are copies.** The API serialises what it is given and
   cannot edit the index by mutating a response.

## References

- [ADR 0001](0001-local-web-ui.md) — the local web layer, its tracks, and its invariants
- [`src/x2knwldg/repository/README.md`](../../src/x2knwldg/repository/README.md) — the interface, endpoint by endpoint
- [`schemas/api/v1/README.md`](../../schemas/api/v1/README.md) — the frozen contract this seam serves
- [`src/x2knwldg/adapters/README.md`](../../src/x2knwldg/adapters/README.md) — where the records come from
- [`PROJECT_MANAGEMENT.md`](../PROJECT_MANAGEMENT.md) §6, §8.2 — the decision ledger and the parallelism model
