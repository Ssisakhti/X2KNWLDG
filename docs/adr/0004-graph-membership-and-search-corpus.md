# ADR 0004 — One membership rule for a source's graph, and a corpus the index owns

- **Status:** Accepted
- **Date:** 2026-08-31
- **Decision ledger:** D-041 (graph node membership) and D-042 (the search corpus), added to
  `KNOWLEDGE_CANVAS_PLAN.md` §19. D-041 **extends** D-035, which stays true as written;
  D-042 replaces two consequences [ADR 0002](0002-index-repository-seam.md) recorded.
- **Supersedes:** [ADR 0002](0002-index-repository-seam.md) in part — decision 6 gains the
  node-membership rule it left implicit, and two of its *Consequences* plus one
  *Alternatives* row no longer describe the code. ADR 0002 stays `Accepted`; decisions 1–5
  and 7 are untouched.
- **Superseded by:** none

## Context

[ADR 0002](0002-index-repository-seam.md) fixed the indexer↔API seam and shipped
`MemoryRepository` behind it. Two things about it have since changed, one because it was
wrong and one because it was slow.

### The two views of a source disagreed about one fact

ADR 0002 decision 5 (D-034) settled what a source's relations are: *a relation belongs to a
source when the source produced it, or when either endpoint is an entity of that source.*
Its alternatives table is explicit about why — filtering on `source_id` alone would drop the
17 `expresses_concept` edges, which name no run, and *"a Reader would show a source without
the links it makes to the concepts it expresses"*.

`/api/graph?source_id=…` never applied that rule. Its node set was "entities of this source",
and an edge was drawn only when both endpoints were in it. A canonical concept belongs to no
source at all (D-016 gives it the reserved `library:concepts` namespace), so every
`expresses_concept` edge had one endpoint outside the node set and was dropped.

**Measured on the sample, 2026-08-31:** `/api/sources/{id}/relations` returned **118**
relations; `/api/graph?source_id=…` drew **101** edges over 69 nodes — all 17
`expresses_concept` edges missing, and the 17 concepts with them. Two endpoints of the same
API, answering one question two ways, and the one a user would call "the graph" was the
lossy one.

### Search re-read the library on every page

`MemoryRepository.search` walked `<project_root>/output` and re-scored every canonical file
per call. Two consequences, neither of them the intended trade-off:

- **The cost ADR 0002 named was being paid per page, not per query.** ADR 0002's alternatives
  row rejected `MemoryRepository` as a production index because it *"re-runs
  `query.search_knowledge`'s linear scan per search"*. Paging made that per *page* — a full
  walk of a result set cost the whole library once per page of it.
- **It was a second, disagreeing view of the library.** A run that appeared on disk after the
  repository was built was searched and returned hits, and every one of those hits carried
  `source_id: null`, because no `Source` record existed to resolve it against. Renderable,
  and unnavigable: no other method on the repository would admit that run existed.

## Decision

1. **A node belongs to a source's graph when it is an entity of that source, *or* when a
   relation of that source names it as an endpoint.** `relation_belongs_to_source` (D-034) is
   the single definition of "a relation of that source", and `graph_nodes` in
   `repository/base.py` is the single implementation of the membership rule. The graph takes
   the relations rule as given and draws the nodes those relations need. *(D-041)*
2. **The edge rule is unchanged.** An edge is drawn only when **both** endpoints are nodes of
   this graph and at least one of them is on this page. See *What this decision is not*.
3. **Every other filter still applies to every node.** `provenance_class`, `kind`, and the
   rest are node filters and are checked before membership: a client asking for
   `provenance_class=source` gets the graph it asked for, and the edges to what it excluded
   go with it. Membership widens the candidate set; it does not exempt anything from a filter.
4. **The search corpus is built from the index, not from the filesystem.** Each run is located
   by the `canonical_dir` its own indexed `Source` record carries — already proven inside the
   project root by `adapters.project_relative` (R15), and re-checked on use, because a
   resolver that does not re-check is not a boundary (ADR 0003 invariant 5). A run that is not
   in the index is not searched, which is what every other method on the repository already
   says about it. No id is joined onto a path, so no host path can reach an error body (D-030).
   *(D-042)*
5. **The corpus is built once per repository instance, on the first search, and never
   invalidated.** Not at construction: a repository that never searches must not pay for one,
   and `/api/status` must stay cheap. *(D-042)*
6. **A source whose canonical files will not read is recorded as unreadable, not as empty.**
   Its hits are unknown rather than zero, and the page reports `total: null` rather than
   counting them as none.

## What this decision is not

ADR 0002's alternatives table rejected *"include an edge when **either** endpoint passes the
node filter"*, because *"the edge would dangle to a node the filter excluded, and a Map that
draws a dangling edge asserts a node it will not show."* **That rejection stands, and this
decision is not a quiet reversal of it.**

The two are opposites in effect:

| | Rejected alternative | D-041 |
|---|---|---|
| What widens | The **edge** rule | The **node** set |
| The far endpoint | Stays out of the graph | Becomes a node of the graph |
| Result | An edge pointing at a node the page will not show | Both endpoints present and drawn |

D-041 exists precisely so nothing dangles: the concept is *in* the graph, so the edge to it
lands on a node the client can see. An implementation that keeps the old node set and relaxes
the edge test would produce the dangling graph ADR 0002 refused, and would satisfy neither
decision. `check_index_integrity` refuses a dangling endpoint at construction, so this is
enforced rather than merely intended.

## Alternatives considered

| Alternative | Why rejected |
|---|---|
| Leave the graph as it was and change `/api/sources/{id}/relations` to match it | It would re-adopt the "filter on `source_id` alone" behaviour D-034 rejected for a stated reason, and lose the concept links from both views instead of one. The lossy view is not the one to standardise on |
| Give concepts a `source_id` so they become entities of a source | D-016 exists because a cross-source concept belongs to no single run. Assigning it one would be a fabricated fact in a record, and would break the moment a second source expressed the same concept |
| Relax the edge rule instead of widening the node set | It draws the dangling edge ADR 0002 refused. See *What this decision is not* |
| Keep two rules, one per endpoint, and document the difference | Two answers to "what is this source's graph" is the drift D-026 and R12 are about. A documented disagreement is still a disagreement, and the Reader and the Map would show different libraries |
| Build the search corpus at construction | `/api/status` and every non-search call would pay for a corpus nothing asked for. `MemoryRepository` already re-reads every run at construction; adding a second full pass to it makes the cheap calls expensive to fix the expensive one |
| Invalidate the corpus when `output/` changes | A watcher, a hash pass, or a stat-per-call — real machinery for a reference implementation whose whole point is to be simple and correct. The index is a snapshot; taking a new one means constructing a new repository, which is one line and is what `T-104` does anyway |
| Keep searching the filesystem so new runs appear immediately | It is the behaviour that produced hits with `source_id: null`. A hit the API cannot resolve to a source is worse than a hit that is not there yet: the first looks like data |

## Consequences

**Positive**

- The Reader and the Map show the same library. Verified on the sample: `/api/graph` and
  `/api/sources/{id}/relations` both report **118** edges over **86** nodes, with all 17
  `expresses_concept` edges present in both.
- One membership rule, in one function, used by both endpoints. A SQLite implementation
  (`T-101`–`T-104`) inherits it rather than re-deriving it in SQL, and ADR 0002 invariant 5
  already says the Python helpers win where a `WHERE` clause disagrees.
- Search costs one pass over the library per repository, not one per page.
- A search hit always names a source `/api/sources/{id}` will answer for.

**Negative / accepted costs**

- The corpus is held in memory alongside the records. `MemoryRepository` was already a
  whole-library-in-memory strategy and says so; this raises the constant, not the order.
- A repository instance never sees a run finalised after it was built — for search now as
  well as for every other method. That is the index being a snapshot, stated rather than
  worked around, and `T-103` replaces the whole mechanism.
- A source's graph can contain nodes that are not entities of that source. Any client
  grouping nodes by owner must read `source_id` on the node rather than infer it from the
  query — the concepts carry `source_id: null` (D-016) and always did.

**Neutral**

- Search pagination stays offset-based and the cursor stays opaque. With the corpus fixed at
  first search, the ranking under a cursor no longer moves within a repository's life.

## Corrections to ADR 0002 (stale facts, not decisions)

`docs/adr/README.md` permits correcting a stale fact in place. Three statements in ADR 0002
stopped describing the code; each is marked there, with its original text kept:

1. *Alternatives* — "It re-reads every run on construction and **re-runs
   `query.search_knowledge`'s linear scan per search**." The construction pass is still true;
   the per-search scan is not. `MemoryRepository` no longer calls `search_knowledge` at all —
   it uses `query.run_documents` / `query.rank_documents` over its own corpus. The row's
   conclusion is unchanged: this is still not the production index, and `T-103` still exists
   to remove the linear scan.
2. *Consequences, positive* — "`T-104` gets an **oracle with no cache at all**." The corpus is
   a cache. What `T-104` may rely on is narrower and is stated in D-042: a **freshly
   constructed** `MemoryRepository` reads the canonical files and nothing else, so the oracle
   is cache-free *per instance*. `T-104` must construct one per comparison rather than reuse
   one across a rebuild.
3. *Consequences, negative* — "a run finalised between two pages can shift the ranking under
   the cursor." It cannot, within one repository: the corpus is fixed at first search. The
   underlying caveat survives in a different form — the ranking a cursor indexes belongs to
   the snapshot that issued it.

## Invariants this decision must preserve

1. **One membership rule.** `relation_belongs_to_source` decides what a source's relations
   are, and `graph_nodes` decides what its graph is drawn over from that. Neither endpoint
   may grow a second rule, in Python or in SQL.
2. **Nothing dangles.** Every edge in a graph page has both endpoints among that graph's
   nodes. `check_index_integrity` refuses a dangling endpoint at construction.
3. **The node filters are not membership.** A filter excludes a node and every edge to it,
   whether that node got in by ownership or by reachability.
4. **A search hit names an indexed source.** No hit may carry a `source_id` the index cannot
   resolve, and no run outside the index is searched.
5. **No id and no host path reaches a search error body.** The corpus resolves through the
   record, not by re-deriving a directory name (D-030, ADR 0003).
6. **Unreadable is not empty.** A source whose files will not read makes `total` unknown; it
   never contributes a zero that reads as a fact.

## References

- [ADR 0002](0002-index-repository-seam.md) — the seam, decisions 5 (D-034) and 6 (D-035)
- [ADR 0003](0003-reject-unsafe-identifiers.md) — invariant 5, containment re-checked at use
- [`KNOWLEDGE_CANVAS_PLAN.md`](../KNOWLEDGE_CANVAS_PLAN.md) §15 API, §19 (D-016, D-034, D-035,
  D-041, D-042)
- [`PROJECT_MANAGEMENT.md`](../PROJECT_MANAGEMENT.md) §6, §10
- `src/x2knwldg/repository/base.py` — `graph_nodes`, `relation_belongs_to_source`,
  `matches_entity`, `check_index_integrity`
- `src/x2knwldg/repository/memory.py` — `MemoryRepository.graph`, `.search`, `._documents`
- `src/x2knwldg/query.py` — `run_documents`, `rank_documents`, `search_knowledge`

*Citations here are symbol names, not line numbers — see the note at the end of
[ADR 0003](0003-reject-unsafe-identifiers.md).*
