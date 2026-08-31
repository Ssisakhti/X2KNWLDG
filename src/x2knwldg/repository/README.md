# The index repository

Delivered by `T-007`. This is the seam where Track A (the SQLite indexer,
`T-101`–`T-104`) and Track B (the FastAPI server, `T-105`–`T-108`) meet — and
the only place they meet. Track B calls `IndexRepository` and never opens a
database, a canonical file, or a run directory. Track A implements it and never
imports a route.

| File | Holds |
|---|---|
| `base.py` | The contract: queries, results, the D-030 error taxonomy, the shared cursor encoding, and the filter rules |
| `memory.py` | `MemoryRepository` — the reference implementation over `adapters.adapt_project` |
| `__init__.py` | The public surface |

```python
from pathlib import Path
from x2knwldg.repository import MemoryRepository, SourceQuery

repo = MemoryRepository.from_project(Path.cwd())
page = repo.list_sources(SourceQuery(limit=20, status="PASS"))
page.items        # Source records, exactly as the adapters produce them
page.page_info()  # {"limit": 20, "next_cursor": ..., "total": ...}
```

## Eleven endpoints, ten methods

[`schemas/api/v1/openapi.json`](../../../schemas/api/v1/README.md) is the
specification. Every endpoint in it is answered here, and nothing else is:

| Endpoint | Method |
|---|---|
| `GET /api/status` | `status()` |
| `GET /api/sources` | `list_sources(SourceQuery)` |
| `GET /api/sources/{source_id}` | `get_source(source_id)` |
| `GET /api/sources/{source_id}/entities` | `list_entities(EntityQuery)` |
| `GET /api/sources/{source_id}/relations` | `list_relations(RelationQuery)` |
| `GET /api/entities/{entity_id}` | `get_entity(entity_id)` |
| `GET /api/artifacts/{artifact_id}` | `get_artifact(artifact_id)` |
| `GET /api/media/{artifact_id}` | `get_artifact(artifact_id)` |
| `GET /api/search` | `search(SearchQuery)` |
| `GET /api/graph` | `graph(GraphQuery)` |
| `GET /api/graph/neighborhood/{entity_id}` | `neighborhood(NeighborhoodQuery)` |

`/api/media` deliberately reuses `get_artifact`. The record carries `path` —
project-relative, produced by `adapters.project_relative` — and `available`.
Serving bytes, range requests, and the loopback binding are `T-108`'s. A
repository that streamed files would put path safety in two places (risk R14).

## The five rules

1. **Pages of v1 records, not rows.** Every list method returns a `Page` of the
   plain dicts `IndexRecords.by_model()` already produces. A row type of its own
   would be a third vocabulary for the same fact (D-026).
2. **The cursor encoding is the repository's alone.** The contract calls it
   opaque, so the API passes it through unparsed and the frontend cannot depend
   on it. `encode_cursor` / `decode_cursor` in `base.py` are that encoding, and
   both implementations share it.
3. **A cursor is bound to the query that issued it.** Change a filter and the
   cursor is refused; change only `limit` and it still works, because a keyset
   position does not depend on page size. Re-anchoring a cursor onto a different
   collection would return data for a question nobody asked.
4. **Absence is a return value; malformation is an exception.** A well-formed id
   naming nothing returns `None` or an empty page — the API renders `404`. An id
   that fails `ids.py` raises `InvalidId` before anything is read (D-020).
5. **The repository can say it cannot answer.** `status()` answers in every
   state; everything else raises `IndexUnavailable` unless the state is `ready`.
   An empty index and an unbuilt one are different answers (D-030).

## Errors are D-030, executable

| Exception | `code` | HTTP |
|---|---|---|
| `InvalidId` | `invalid_id` | 400 |
| `InvalidQuery` | `invalid_request` | 400 |
| `IndexUnavailable` | `index_unavailable` | 503 |
| `RepositoryError` | `internal` | 500 |

The API renders the error it is handed. It does not get to choose a different
status for the same refusal, and `404` is never an exception — it is what a
route makes of `None`.

## Two rules that are decisions, not details

**A relation belongs to a source when the source produced it, *or* when either
endpoint is an entity of that source.** The second clause is not redundant: the
17 `expresses_concept` edges in the current library carry `source_id: null`
because `adapt_library` produces them and they are cross-source (D-025). They
are still the edges that connect a source to the concepts it expresses, and a
Reader that hid them would be hiding the source's own links. Endpoint membership
is read off the global id (D-011) — no join, and no second rule.

**A graph page is a page of nodes, not of edges.** Paging over edges would
silently drop an entity that has no relations. An edge is included when both
endpoints pass the node filter and at least one is on this page: requiring
*both* keeps the page renderable, because an edge to a filtered-out node would
dangle, and a Map that draws a dangling edge asserts a node it will not show. An
edge straddling two pages appears in both; a client accumulating pages dedupes
by `id`.

## `MemoryRepository` is a reference, not an index

It reads every run through `adapters.adapt_project`, holds the records in
memory, and re-runs the linear scan of `query.search_knowledge` for every
search — which is the cost `T-103`'s FTS5 tables exist to remove. Do not serve a
growing library from it. It exists so that:

- **Track B can start on day one.** `T-105`–`T-108` build routes against it
  while `T-101`–`T-104` build SQLite behind the same interface.
- **Track A gets an oracle.** `T-104` must prove a rebuilt index equals an
  incrementally updated one. Both must also equal this — a repository with no
  cache at all. Where they disagree, the canonical files are right and the index
  is stale (ADR 0001 invariant 3).
- **R18 is closed.** D-028's additive search fields (`global_id`, `source_id`)
  now live in `MemoryRepository.as_api_hit`, which is what
  `tests/test_api_contract.py` exercises. They were a test helper no server
  would ever call. The source type is read from the indexed source rather than
  assumed to be YouTube.

## Writing the SQLite implementation (`T-101`–`T-104`)

- Implement the `IndexRepository` protocol; do not widen it. An endpoint that
  needs something this interface cannot express is a contract change first.
- Page with `WHERE <order key> > ?`, and issue the cursor through
  `encode_cursor`. Both implementations then produce the same token for the same
  position, which makes rebuild-equivalence a page-for-page comparison rather
  than a second implementation of the comparison.
- Order by the keys in `ORDER_KEYS`: `Source.id`, `Artifact.id`,
  `EntityRef.global_id`, `IndexedRelation.id`. The order is total and
  lexicographic, so nothing else needs to be stored to page by it.
- Reuse `matches_entity`, `matches_relation`, `matches_source`, and
  `relation_belongs_to_source` as the definition of each filter, even where SQL
  expresses them as a `WHERE` clause. Where SQL and these disagree, these are
  the specification.
- Report `index_version` from the migration table, and `built_at` from the last
  completed build. `MemoryRepository` reports `None` for both because it has no
  persisted index — stating a version there would claim a durable artifact that
  does not exist.

## Tests

| File | Asks |
|---|---|
| `tests/test_repository.py` | What does the seam refuse, and what must stay true of a second implementation? (stdlib only — runs on a bare core install) |
| `tests/test_api_contract.py` §5 | Does what the repository returns validate as the response body of the endpoint it serves? (needs `jsonschema`, a `dev` extra) |
