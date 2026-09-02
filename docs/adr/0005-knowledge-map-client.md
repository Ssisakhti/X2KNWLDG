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

## Gate result (`T-202`, 2026-09-02)

The compatibility gate has run. **The v4 line is kept**; the stable-v3 fallback was not
needed and no v3 code was written.

**What was pinned.** `sigma@4.0.0-beta.5`, `graphology@0.26.0`, `graphology-types@0.24.8`,
`graphology-layout-forceatlas2@0.10.1`, and `@types/events@3.0.3`. All five are exact pins,
all are MIT, and all are recorded with their versions in
[`THIRD_PARTY_NOTICES.md`](../../THIRD_PARTY_NOTICES.md) together with the two packages they
pull in transitively (`graphology-utils@2.5.2`, `events@3.3.0`). Five tests in
`tests/test_ui_scaffold.py` fail if a pin becomes a range, if the version the gate page
prints stops matching the manifest, if the harness leaks into the production build or the
application, or if a licence entry goes missing.

**Where it ran.** macOS 26.5.2 on Apple silicon (arm64), Google Chrome 152.0.7977.65,
WebGL2 through `ANGLE (Apple, ANGLE Metal Renderer: Apple M5)` — a real GPU path, not a
software rasteriser. The page was served by `npm run dev` and answered by
`create_app(project_root=…)` over the **real ingested project**, so the graph came from the
same code path `x2knwldg ui` serves and not from a fixture or a mock.

**What it drew.** `/api/graph?limit=500` returned 86 nodes and 118 edges with
`truncated: false` and `next_cursor: null` — the real sample is one honest page under the
contract maximum, as [`PROJECT_MANAGEMENT.md`](../PROJECT_MANAGEMENT.md) §3 states it should
be. The renderer drew **86 of 86 nodes and 118 of 118 edges**, with 0 edges whose endpoint
was off the page and 0 self-loops. Node and edge identities are the API's own `global_id`
and relation `id`.

**Measurements** (ranges as recorded across the 21 renders, with the cold first pass called
out separately):

| Operation | Cost |
|---|---|
| 200 ForceAtlas2 iterations, 86 nodes / 118 edges, synchronous | **2.7–3.4 ms** steady, **8.5–9.0 ms** on the first pass of a page load |
| Attribute update across all 86 nodes, then `refresh()` | 0.9–2.2 ms |
| One full create → update → select → teardown round | ~62 ms (20 rounds in 1243 ms) |

The synchronous layout is two orders of magnitude inside a 16.7 ms frame, so **D-121: no
layout worker**. The cold pass being three times the steady one is the number to re-measure
first if a filter change ever lays out on every keystroke.

**Lifecycle.** Create, update, resize (grow *and* shrink), selection by id, selection by
pointer click, and teardown were each exercised, then 20 further create/update/select/
teardown cycles ran back to back. Every renderer context was released: 21 created, 21 lost,
none left live, with a `webglcontextlost` event for each — Sigma v4's `kill()` calls
`WEBGL_lose_context.loseContext()` explicitly, so invariant 10 is observable rather than
assumed. A 22nd renderer created after all that drew the graph normally. No uncaught
exception, no unhandled rejection, and no page-level failure was recorded at any point. The
only 404 in the walk was `/favicon.ico`, which the harness page does not define; no API
request failed.

**Determinism.** Render #22 and render #1 are indistinguishable — the same clusters in the
same places, compared between the two captured screenshots by eye rather than by pixel
difference. Seeds are hashed from each node's `global_id` rather than taken from its position
in a page, which is what makes a reload and a later page reproduce the same picture (D-118);
that the layout is a pure function of those seeds is asserted in
`web/src/map/seedPositions.test.ts`.

### Findings

Four, none of them blocking. Two are v4 observations that stay open; two were fixed inside
this task.

1. **The published v4 declarations do not type-check on their own.** `sigma`'s `.d.ts`
   files `import "events"`, and that package ships no types, so `tsc` fails outright while
   `web/tsconfig.json` keeps `skipLibCheck: false` — which risk R17 exists to keep on.
   Pinning `@types/events@3.0.3` resolves it. **Not a v4 defect**: `sigma@3.0.3` depends on
   `events` too, so the stable line would have needed the same package.
2. **The beta emits `GL_INVALID_OPERATION` warnings while rendering correctly.** Chrome logs
   `glDrawArraysInstanced: Active draw buffers with missing fragment shader outputs` a few
   times per context during renderer setup. The graph, its edges and its labels all draw, no
   error surfaces to the page, and nothing is visibly missing — so this is recorded rather
   than acted on. It is exactly the class of thing the maintainer's "combinations of newer
   features may contain bugs" warning describes, and it is the first thing to re-check on the
   next beta or on 4.0.0 final.
3. **ForceAtlas2 does not refuse an unpositioned node; it produces `NaN` silently.**
   `graphology-layout-forceatlas2` reads `attr.x` straight into a `Float32Array`, so a node
   inserted without a position becomes `NaN`, raises nothing, and is simply not drawn — a
   real entity missing from the Map with no error anywhere. Seeding is therefore part of
   inserting a node in `web/src/map/`, never a separate pass that can be skipped.
4. **A hash is not automatically a spread.** The first seeding implementation used FNV-1a
   alone. This project's ids share a long prefix and differ in their last characters, and
   FNV-1a's avalanche is weak in exactly that case: 200 sequential ids fell into four of ten
   radius buckets and none into the inner half of the disc, so the graph started as a ring —
   the one shape gravity cannot improve. Adding Murmur3's finalizer spread the same ids
   evenly (17–23 per bucket). The seeds were distinct throughout, so nothing failed; the
   layout was just worse for a reason no test would have reported.

### What the gate hands to later tasks

- **D-121** — the layout stays synchronous. `T-204` must not introduce a worker without a
  new measurement, and must keep the seed-then-layout order.
- **D-122** — the Map must not draw the raw `label`. Rendering the real labels showed why:
  a knowledge unit's label is its whole `normalized_statement`, and 86 sentences at once
  overlap into a pile that hides the graph, with the longest running past the container edge.
  `T-205` owns a truncation and density policy; the full statement stays in the inspector.
- **Selection needs a signal stronger than size.** The gate's size-only selection is
  indistinguishable at real node density, which is a concrete reason `T-207`/`T-208` cannot
  rely on a subtle visual change alone — and, with D-120, cannot rely on colour either.
- **The harness is not the Map.** `web/gate.html` and `web/src/map/gate/` are
  development-only, unrouted, and excluded from the production build; `#/map` remains
  `T-204`'s to create. `web/src/map/gate/gateGraph.ts` is a single-page conversion for this
  gate and is explicitly **not** the `T-203` projection.

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
