# ADR 0005 — A progressive, addressable and accessible Sigma v4 Knowledge Map

- **Status:** Accepted
- **Date:** 2026-09-02
- **Decision ledger:** D-117 … D-120 (`KNOWLEDGE_CANVAS_PLAN.md` §19 and
  `PROJECT_MANAGEMENT.md` §6)
- **Supersedes:** none
- **Superseded by:** none

## Context

Phase 1 serves the complete frozen read-only API and leaves four consumers deliberately
unused: `/api/graph`, `/api/graph/neighborhood/{entity_id}`, `/api/entities/{entity_id}` and
`/api/search`. The real sample projects to 86 entities and 118 directed relations. Of those
relations, 45 are `derived_from` and 17 are `expresses_concept`; both are library-synthetic,
not members of the canonical `RELATION_TYPES` vocabulary. The Map must render the graph the
API actually carries rather than a simplified second model.

Three boundaries make the frontend choice architectural rather than routine.

1. **Sigma's next renderer API is already public but still prerelease.** Sigma v4 began as
   an alpha. At this decision date the official v4 site identifies itself as the v4 beta
   site, and its quickstart is built for `4.0.0-beta.5`. The v4 migration guide replaces
   v3's program-class styling with declarative primitives and layers. The maintainer reports
   the v4 API full-featured and not expected to move, while explicitly warning that
   interactions between newer features may still expose bugs. This project is starting its
   Map now and has no v3 Map to migrate.
2. **A graph page is not necessarily a drawable graph.** D-059 permits an edge on one page
   to cross to a node on another page, provided both endpoints pass the graph filter. The
   edge repeats on both pages. The API states `truncated` separately from
   `page.next_cursor`, because even the final page of a paged walk is still a slice of a
   larger graph.
3. **WebGL is a visual surface, not the whole interaction model.** The application requires
   keyboard operation, bidi-correct content and provenance distinctions that do not depend
   on colour. Putting an HTML component on every node would defeat Sigma's reason for being,
   but leaving selection inside a canvas would make the Map pointer-only and would provide
   no useful semantic description of the graph.

Sigma requires node positions. Graphology's ForceAtlas2 implementation likewise requires
non-zero initial `x`/`y` positions and offers a worker. The canvas plan already says a worker
is introduced only when real data blocks the UI thread, not in anticipation of scale.

## Decision

1. **Start Phase 2 on one exactly pinned Sigma v4 beta.** `T-202` selects the exact version
   and compatible Graphology/renderer packages and commits the lockfile. It must prove
   create, update, resize, selection and teardown over the real 86/118 sample on the user's
   MacBook before `T-203` begins. A prerelease range is forbidden. If the gate finds a
   blocking v4 defect, it records the defect and pins the current stable v3 before any Map
   architecture accumulates. The phase never carries both APIs. *(D-117)*
2. **Use a typed `MultiDirectedGraph`.** Node keys are the existing `global_id`; edge keys
   are the existing relation `id`. Direction, parallel edges, intentional self-loops, null
   confidence, canonical paths and relation vocabulary are preserved. A conflicting repeat
   is an error, not a merge guess.
3. **Treat the Map as a progressive snapshot.** The first `/api/graph` call requests no more
   than the contract maximum of 500 nodes. Later pages are deliberate, cancellable loads.
   Nodes dedupe by `global_id`, edges dedupe by `id`, and an edge stays pending until both
   endpoints exist locally. The UI states loaded/known totals and `truncated`; it never calls
   one page the whole graph. A filter change discards the old snapshot rather than mixing
   two questions. The client never parses an opaque cursor. *(D-118)*
4. **Give Map state one URL grammar.** `mapLink` is the only builder/parser for selected
   `global_id`, source scope, provenance filter and relation-vocabulary filter. Valid state
   survives reload; malformed state is ignored, never coerced. Search hits without a real
   `global_id` remain unaddressable. *(D-119)*
5. **Use the API's filters, not browser inventions.** The Map offers `source_id`,
   `provenance_class` and `relation_vocabulary`. `kind` affects styling and local discovery,
   but is not presented as a server-backed graph filter because `GET /api/graph` does not
   accept it. Widening that is an OpenAPI decision first.
6. **Keep the WebGL view paired with a small semantic DOM surface.** Search results, graph
   state, selected entity, neighbourhood controls, inspector and Reader navigation are
   keyboard-operable DOM. Sigma handles the overview, pan/zoom, hover and pointer selection;
   it does not receive a heavy HTML node for every entity. Both paths update the same
   selected `global_id`. *(D-120)*
7. **Seed positions deterministically before layout.** `T-202` measures a finite synchronous
   layout on the real sample. A worker is added only if that measurement or a later real
   dataset shows blocking. No arbitrary performance threshold is recorded before the
   baseline exists.

## Alternatives considered

| Alternative | Why rejected |
|---|---|
| Start on stable Sigma v3 | It is the conservative dependency choice, but this is new work and v4 deliberately replaces the renderer API the provenance/kind style matrix would be built on. The v4 beta API is reported stable enough for new work. Stable v3 remains the bounded fallback at `T-202`, not a second implementation |
| Accept `^4.0.0-beta` or another moving prerelease range | A clean install could silently adopt a new beta and change rendering behaviour without a project decision. Exact package and lockfile pins make a prerelease auditable |
| Automatically fetch every graph page before rendering | It hides the first useful overview behind an unbounded walk and makes a growing library pay full cost on every filter. The API was paged to avoid that |
| Render each page independently | D-059 cross-page edges either dangle or require invented placeholder nodes, and the same edge appears twice. Neither is a faithful graph |
| Drop cross-page edges permanently | It makes connectivity depend on page size and order. A full walk would not reproduce the API graph |
| Add `kind` to the graph request from the frontend | The frozen operation has no such query parameter. A frontend-only parameter would be fiction; a real one is an OpenAPI/repository change outside T-201 |
| Put a focusable DOM element over every WebGL node | It duplicates the renderer at graph scale and fights pan/zoom positioning. A bounded results/selection/inspector surface supplies semantics without rebuilding the graph in HTML |
| Treat the canvas as accessible by assigning one label | A single label describes the existence of a graph, not its selectable entities, relationships or controls, and does not make pointer actions keyboard-operable |
| Start with a ForceAtlas2 worker | The current graph is 86/118 and no blocking has been measured. Worker lifecycle and bundling are real complexity; the plan requires evidence before paying it |

## Consequences

**Positive**

- New Map styling is built on the renderer API expected to continue, with v4 primitives and
  layers matching provenance/kind semantics rather than custom shader classes by default.
- Page size cannot alter the final accumulated graph: identities, direction and repeated
  straddling edges have one merge rule.
- Empty, partial and complete are visible states rather than inferences from a cursor.
- Pointer, keyboard, reload and Reader navigation share one selection identity.
- The existing API and canonical files remain unchanged.

**Negative / accepted costs**

- Sigma v4 is still prerelease. Exact pins prevent surprise upgrades but do not remove bugs;
  the real-device `T-202` gate and stable-v3 fallback contain that risk.
- The client needs a small graph store with pending edges and cancellation, rather than
  handing one response directly to Sigma.
- The Map has both a visual renderer and a semantic DOM control surface. They must be tested
  to select the same `global_id`.
- A graph larger than the first page is intentionally incomplete until the user or a focus/
  neighbourhood action loads more data.

**Neutral**

- Phase 2 remains read-only. No board, user edge or Canvas transfer is introduced.
- ForceAtlas2 worker adoption remains a measured implementation decision, not a roadmap
  promise.

## Invariants this decision must preserve

1. **One renderer major after `T-202`.** No compatibility layer and no simultaneous v3/v4
   code path.
2. **One identity.** Node selection is an existing `global_id`; edge identity is an existing
   relation `id`. Neither is synthesized from labels or endpoints.
3. **No dangling rendered edge.** A cross-page edge waits; it is never dropped forever and
   never gets a placeholder endpoint.
4. **Partial stays visible.** `truncated: true` cannot be hidden by reaching a null cursor or
   by showing only currently drawable edges.
5. **Filter snapshots never mix.** Changing source/provenance/vocabulary cancels and replaces
   the current walk.
6. **Cursors remain opaque outside the API client.** Store and return them; never parse them.
7. **No invented graph filter.** A control described as server-backed must exist in the
   generated `Endpoints["getGraph"]["query"]` type.
8. **No WebGL-only operation.** Search, selection, neighbourhood, inspector and Reader
   navigation remain keyboard-operable without hit-testing the canvas.
9. **No colour-only provenance.** The graph/legend and DOM inspector retain a non-colour
   signal for provenance and relation vocabulary.
10. **Lifecycle cleanup is load-bearing.** Sigma and any layout worker are killed on unmount
    or replacement; a filter/reload loop must not accumulate WebGL contexts or workers.

## References

- Sigma v4 beta site: <https://v4.sigmajs.org/>
- Sigma v4 quickstart (`4.0.0-beta.5` at decision time):
  <https://v4.sigmajs.org/get-started/quickstart/>
- Sigma v3 → v4 migration: <https://v4.sigmajs.org/how-to/technical/migration-v3-v4/>
- Sigma v4 announcement and maintainer maturity update:
  <https://github.com/jacomyal/sigma.js/discussions/1539>
- Sigma releases: <https://github.com/jacomyal/sigma.js/releases/>
- Graphology instantiation: <https://graphology.github.io/instantiation.html>
- Graphology mutation/keyed edges: <https://graphology.github.io/mutation.html>
- Graphology ForceAtlas2: <https://graphology.github.io/standard-library/layout-forceatlas2.html>
- W3C keyboard technique G202: <https://www.w3.org/WAI/WCAG22/Techniques/general/G202.html>
- W3C accessibility principles: <https://www.w3.org/WAI/fundamentals/accessibility-principles/>
- [`PROJECT_MANAGEMENT.md`](../PROJECT_MANAGEMENT.md) — `T-201`–`T-209`, D-117 … D-120
- [`KNOWLEDGE_CANVAS_PLAN.md`](../KNOWLEDGE_CANVAS_PLAN.md) §6.3, §13.3, §16 Phase 2
