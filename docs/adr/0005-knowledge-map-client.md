# ADR 0005 — A progressive, addressable and accessible Sigma v4 Knowledge Map

- **Status:** Accepted
- **Date:** 2026-09-02
- **Decision ledger:** D-117 … D-149 (`KNOWLEDGE_CANVAS_PLAN.md` §19 and
  `PROJECT_MANAGEMENT.md` §6). D-117–D-133 are this decision's own; D-134–D-149
  were recorded by the tasks that implemented it, `T-207`–`T-209`
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
4. **Topology alone does not answer the user's reading task.** The required journey is to
   search for knowledge, judge a result before opening it, read the stored statement and
   evidence, then choose related knowledge with its relation and content already visible.
   Bare circles force blind clicks; navigating every selection to the Reader discards graph
   context and creates repeated backtracking. Research on knowledge-graph consumers likewise
   identifies the limits of node-link diagrams and proposes contextual knowledge cards that
   preserve discoverability, while information-scent research treats omitted differentiating
   content as a cause of pogo-sticking.

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
8. **Make the Map a progressive content browser.** Its single journey is Search →
   Preview/Peek → Focus → Quick Read. Search and reading remain inside `#/map`; the Reader is
   the deliberate destination for the complete source, not the price of understanding every
   node. *(D-130)*
9. **Copy content; do not re-author it.** Result, Peek, selected and related cards use the
   API record verbatim. On-stage previews may visibly truncate; Quick Read exposes the full
   stored `label`, recorded locator excerpt/time, active relation, derivation, provenance and
   source before technical identifiers. Missing content stays missing; there is no generated
   client summary. *(D-131)*
10. **Use a bounded card constellation over the same WebGL graph.** The stage has one primary
    selected Knowledge Card, at most one transient Peek, labelled active relations and only
    the compact neighbour previews that an explicit density policy can place. Sigma's
    `graphToViewport`/`afterRender` overlay pattern keeps those DOM elements anchored without
    turning every node into HTML. Every node returned by the bounded neighbourhood remains in
    the semantic related list, so a viewport budget never becomes silent omission. *(D-132)*
11. **Preserve exploration history without inventing semantics.** Focus selection pushes the
    existing `mapLink` grammar, browser Back restores prior focus without leaving Map, and
    transient Peek writes no history. Radial/region grouping and deterministic ordering may
    use only relation, direction, vocabulary, provenance, source and identity. No inferred
    importance, cluster, score or decorative quantitative axis is presented as data.
    *(D-133)*

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
| Keep circles plus a side inspector only | The user must still click a node before learning what it contains or why its relation matters. Quick Read solves reading after selection; Preview/Peek and related cards solve informed choice before it |
| Turn every visible node into a rich card | It collapses at overview density, creates a second DOM renderer and contradicts the measured reason Sigma was selected. The bounded constellation gives the focused subgraph cards while WebGL retains the whole context |
| Use the supplied radial references as a radar or importance chart | No API field states a radial value or importance score. A visually plausible shape would be an invented claim. The design borrows centre, sectors, labelled paths and restrained regions only where exact fields support them |

## Consequences

**Positive**

- New Map styling is built on the renderer API expected to continue, with v4 primitives and
  layers matching provenance/kind semantics rather than custom shader classes by default.
- Page size cannot alter the final accumulated graph: identities, direction and repeated
  straddling edges have one merge rule.
- Empty, partial and complete are visible states rather than inferences from a cursor.
- Pointer, keyboard, reload and Reader navigation share one selection identity.
- Search results and graph neighbours expose verbatim information scent before selection, and
  Quick Read exposes the complete stored statement/evidence without a route change.
- Focus history preserves orientation while the full WebGL graph remains the context behind a
  bounded number of readable cards.
- The existing API and canonical files remain unchanged.

**Negative / accepted costs**

- Sigma v4 is still prerelease. Exact pins prevent surprise upgrades but do not remove bugs;
  the real-device `T-202` gate and stable-v3 fallback contain that risk.
- The client needs a small graph store with pending edges and cancellation, rather than
  handing one response directly to Sigma.
- The Map has both a visual renderer and a semantic DOM control surface. They must be tested
  to select the same `global_id`.
- Overlay cards need collision/density policy and render synchronisation; the semantic related
  list is required because no viewport can promise to place every neighbour card legibly.
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
11. **No blind-choice dependency.** A result or returned neighbour has a verbatim textual
    preview and its real relation context before focus; the full Reader is not required merely
    to learn what a node says.
12. **No client-authored knowledge.** On-stage card truncation is visibly presentational;
    Quick Read's complete selected text, excerpts, confidence, derivation and times are copied,
    absent or linked, never completed or summarised by the client.
13. **Overlay count is bounded; neighbour access is complete.** One primary selected card and at
    most one Peek exist on stage; density-budgeted compact cards may omit a placement, but
    every neighbourhood record remains in the semantic related list and WebGL graph.
14. **Peek is ephemeral; Focus is history.** Hover/keyboard preview writes no URL entry;
    selection uses `mapLink`, and browser Back restores a prior focus without leaving Map.
15. **Visual emphasis is not evidence.** Grouping, order, shape and path labels derive only
    from stated graph fields. No inferred relevance, importance, quantitative axis or cluster
    enters the view without a separate data/contract decision.

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

## Projection result (`T-203`, 2026-09-02)

The projection and the progressive snapshot are built, in
[`web/src/map/`](../../web/src/map/README.md) and behind no route: `graphProjection.ts`,
`graphSnapshot.ts` and `graphWalk.ts`, with 48 hermetic tests and 3 against a running server.

**What was measured.** The same walk over the **real 86-node/118-edge graph**, at four page
sizes, served by `create_app(project_root=…)` over the real ingested project:

| Nodes per page | Pages | Edges held at once, peak | Accumulated | `truncated` on the last page | `complete` |
|---|---|---|---|---|---|
| 1 | 86 | 54 | 86 nodes / 118 edges | `true` | `true` |
| 10 | 9 | 46 | 86 / 118 | `true` | `true` |
| 50 | 2 | 35 | 86 / 118 | `true` | `true` |
| 500 | 1 | 0 | 86 / 118 | `false` | `true` |

Page size does not change the graph, which is invariant 3 stated as a measurement rather than
as an intention. The peak column is what a renderer would otherwise have drawn as dangling
edges or invented nodes: 54 of them at one node per page, and none left at the end.

**What the walk settled that this ADR left ambiguous.** Invariant 4 says `truncated: true`
cannot be hidden by reaching a null cursor. The table shows the other half of it: *every* page
of a multi-page walk reports `truncated`, the last one included, because both repository
implementations compare the page against the whole filtered node set. So partiality cannot be
accumulated from that flag either, and D-123 is the rule that came out of it — finished walk,
nothing pending, and either `truncated: false` or the loaded count reaching the stated
`total`, with an uncounted `total` leaving the question open.

Two decisions follow from building it, and both bind `T-204`–`T-208`: node and edge
attributes are the API's record verbatim plus a seeded position, with styling left to the
renderer's reducers (**D-124**); and a repeated identity that disagrees in any field is a
refusal naming that field, with absent and `null` read as the same statement (**D-125**).

`GraphWalk` is the one graph store this phase gets. §8.6 of
[`PROJECT_MANAGEMENT.md`](../PROJECT_MANAGEMENT.md) forbids a second one, and the reason is
invariant 5: two snapshots never share a graph object, so a filter change cannot mix two
questions even if a component forgets that it should not.

## Shell result (`T-204`, 2026-09-02)

The Map has an address. `#/map` is a declared route with a navigation entry,
[`web/src/views/MapView.tsx`](../../web/src/views/MapView.tsx) composes it, and
the renderer lifecycle is one class — `MapSession` in
[`web/src/map/mapSession.ts`](../../web/src/map/mapSession.ts) — reached through
an injected factory whose only production implementation is
`web/src/map/sigmaRenderer.ts`. `GraphWalk` is driven through
`web/src/map/useGraphWalk.ts`, a binding that owns *when* a question is asked
and nothing about what a page means. No second store, no second projection, no
second Sigma wrapper.

**What it draws, and what it says.** The first request is `GRAPH_PAGE_LIMIT`
nodes — the contract's own maximum — so the real 86-node/118-edge sample
arrives as one page. Beside the canvas, read from `GraphSnapshot.state` and
never recomputed: nodes loaded against the total the server counted, edges
drawn, edges **held** for an endpoint that has not arrived (D-059), pages
applied, and whether the accumulated graph is whole (D-123). A next page is a
button, never automatic, and it re-settles the graph already on screen instead
of creating a second renderer.

That statement is rendered *before* the canvas. It is the description that
survives when the picture cannot be read at all — by a screen reader, or in a
browser with no WebGL2 — and a Map whose only honest account came after the
drawing would read as complete to anyone who never reached the drawing.

**Styling is still `T-205`'s.** The graph carries `x`, `y` and the record and
nothing else (D-124), so Sigma draws its own uniform default size and colour.
`renderLabels` is off, because D-122's truncation policy does not exist yet and
a knowledge unit's label is its whole `normalized_statement`. No placeholder
palette was written: it would be the second style table §8.6 forbids.

**Measured.** The frontend suite is **267 hermetic tests in 27 files**, plus
**17** against a running server — 21 of them new here, 11 over the lifecycle
and 10 over the view. Against the real ingested project the Map states 86 nodes
/ 86 counted, 118 edges, 0 held, `truncated: false`, complete; against the
committed fixtures it states whatever that server returns, compared field by
field with the payload rather than to a constant. `npm run build` splits the
renderer into a 362 kB chunk (94 kB gzipped) the Library and the Reader never
load.

`#/map` has not yet been walked in a browser: `T-202` proved the renderer over
this graph on this machine, and the route's own browser walk — including a real
`ResizeObserver`, a real camera and 21 more create/kill cycles — is `T-209`'s.

### Findings

Four, all fixed inside this task, and the first two are the ones a later task
would otherwise rediscover.

1. **`sigma` cannot be imported statically in a jsdom program.** Its default
   primitives call `layerFill` while the module body evaluates, and `layerFill`
   destructures `UNSIGNED_BYTE` off the global `WebGL2RenderingContext` — which
   jsdom does not define. So a static `import Sigma from "sigma"` anywhere in
   the application's module graph is a `ReferenceError` at load, and it takes
   down the suites of every component that has nothing to do with the Map.
   `MapView` reaches the renderer through a dynamic `import` instead (D-127),
   which is also why the Library and the Reader no longer carry it. A test
   fails if a static import reappears.
2. **`useState` calls a function it is handed.** Holding the renderer factory
   in state stored it unwrapped, so React invoked it as a lazy initialiser and
   constructed a renderer *during render*, before the container existed. What
   caught it was a test asserting that an `index_unavailable` refusal creates
   no renderer at all — the counting test, not the drawing one.
3. **A merged page cannot keep the picture still.** A continuation page's nodes
   arrive on their identity seeds, which say nothing about the structure the
   layout already found, so the whole graph is relaxed again and the drawing
   moves (D-128). Pinning the placed nodes is what
   `graphology-layout-forceatlas2` offers instead, and it needs a third node
   attribute — which D-124 does not let the graph carry.
4. **`allowInvalidContainer: false` makes the stage's size load-bearing.** The
   refusal is the behaviour worth keeping — a graph drawn into a zero-sized box
   is the failure nobody can explain — but it means an unsized container has to
   be a state the Map can render. It is: the renderer's refusal is caught and
   stated beside counts that are still true (D-129).

### What the shell hands to later tasks

- `MapView` takes `createRenderer`, and the tests inject a fake. `T-205`–`T-208`
  extend the same seam rather than reaching for Sigma themselves.
- Styling arrives as reducers passed to `createSigmaRenderer`, and `T-205` owns
  both that and the label policy `renderLabels: false` is holding open.
- Selection is deliberately absent: `enableEdgeEvents` is off and nothing
  listens for `clickNode`, so `T-206` defines the selection grammar once and
  `T-207` consumes it, with no interim identity to migrate.
- The `data-map-*` attributes on the state panel are the test seam for
  "partial is not whole"; keep them true if the panel is restyled.

## Approved browsing experience (`T-205`–`T-209`, 2026-09-02)

The user approved a Map that combines the global network with readable, card-shaped focus.
The four supplied visual references are references, not specifications: their reusable ideas
are a quiet stage with one strong focus, rectangular content nodes, labelled active paths,
visible interaction history, radial focus/context and editorial hierarchy. Their decorative
or quantitative shapes are not data and are not copied as if they were.

```text
Explore                         Focus + Quick Read

  o---◇---o                     [related statement]
   \  |  /                        relation \
     [o]                    ┌──────────────────────┐  ┌──────────────┐
   /  |  \                  │ selected full       │  │ statement    │
  o---o---◇                 │ Knowledge Card      │  │ evidence/time│
                            └──────────────────────┘  │ derivation   │
                               relation /             │ source/meta  │
                           [related statement]        └──────────────┘
```

`T-205` supplies renderer states and semantic density, `T-206` supplies preview/Peek and
focus history, `T-207` supplies the bounded constellation/related list/Quick Read (delivered;
see *Constellation result*), `T-208` ensured the same journey exists without hover or WebGL
(delivered; see *Accessibility result*), and `T-209` walks the complete task in a real
browser. The acceptance question is behavioural: before opening a related node, can
the user state what it says and why its real relation makes it worth opening? No numeric UX
threshold is fixed until the pre-card experience is observed as a baseline.

## Constellation result (`T-207`, 2026-09-02)

The Map can be read. A selection now loads what the entity *is*
(`/api/entities/{entity_id}`) and what it is connected to
(`GET /api/graph/neighborhood/{entity_id}`, depth 1 by default and 1–3
exposed) — the last two operations of the frozen contract that nothing had
called — and turns both into three surfaces: a bounded card constellation over
the marks, a related list that cannot omit anything, and Quick Read over the
whole stored record.

**The neighbourhood is not the graph.** Both answers go through `T-203`'s
projection, refusal included, but into a structure of their own that is
replaced whole when the selection or the depth changes and is never handed to a
renderer (D-134). Merging it into `GraphSnapshot` would draw nodes the URL's
filters exclude, push the loaded count past the `total` the server counted for
a different question, and make `complete` a claim about a set nobody asked for
— invariants 4 and 5, from the other direction.

**The bounded overlay is presentation, and that is the design.** It has no
button, no link and no focusable element; it takes no pointer events, so a
click passes through to the mark underneath; and it is hidden from the
accessibility tree, because every card on it is a second view of a row in the
related list beside it (D-137). What that buys is worth stating plainly: the
overlay cannot build a duplicate accessibility tree over the same entities, it
cannot own an action that is unreachable without WebGL, and it cannot introduce
a second selection identity, because it holds no handler at all. It is also a
*sibling* of the container the renderer owns, since `MapSession.kill()` empties
that container and a React subtree inside it would be removed from under React
the first time a filter changed.

**The density policy is a function, and its refusals are counted.**
[`placeConstellation`](../../web/src/map/constellation.ts) applies four clauses
to the related list in its own deterministic order — the neighbour is not drawn
on this Map, its mark is off the stage at this camera position, its card would
overlap one already placed (one card per 240 px cell, the same device Sigma's
`labelDensity` uses for labels), or it is beyond the four-card budget — and
each of them returns a *reason* that is counted and rendered in words. Cards
placed plus omissions counted equals the neighbours returned: asserted on
fixtures and on the real fan-out. That is R20's mitigation in one sentence, and
it is why the risk is now green rather than "controlled by design gate".

**The canvas is a third caller.** `MapSession` grew `onNode`, `onRender`,
`graphToViewport` and `nodePosition`, with the handlers in a mutable slot read
by a trampoline subscribed once per renderer — so a click reaches the same
`useMapFocus.focusEntity` the search rail's buttons call, and what a click
*does* can change on every render without the live renderer being rebuilt
(rebuilding it would kill the accumulated picture, D-126). `enableEdgeEvents`
stays off: `T-204` left it "until something selects an edge", and this is the
task that would have — an edge has no address in D-119's grammar, so its
relation is named in words instead (D-135).

**Measured.** The frontend suite was **491 hermetic tests in 44 files**, plus
**22** against a running server — 85 of them new here, and 5 of the 22.
(`T-208` took it to 550 in 51; see *Accessibility result* below.) Against
the real ingested project, the graph's most connected entity is a derived unit
with **8 neighbours and 13 edges** among them, spanning both relation
vocabularies and including a canonical concept that belongs to no source: the
related list holds exactly those 8, every edge is joined, nothing is
unreachable, and Quick Read renders the server's own statement without
shortening it.

The build cost is measured against the same commit's own before-and-after on
this machine: the application bundle goes from 421.05 kB to 445.13 kB (121.02
to 127.48 kB gzipped) and the stylesheet from 10.81 kB to 11.36 kB, while the
renderer chunk moves by 0.23 kB — 371.67 to 371.90 kB — which is the adapter
and nothing else. None of `T-207` is in the chunk the Library and the Reader
never load. (The absolute renderer figure differs slightly from the 377 kB
`T-205` recorded; the 371.67 kB above is that same chunk re-measured here, so
the delta is the number to read, not the difference between the two rows.)

### Findings

Three, all fixed inside this task.

1. **A placement computed during render asks a renderer that has not been given
   the graph yet.** React runs a render, then its effects; the effect that
   calls `MapSession.attach` runs *after* the render that first sees the page.
   So the first placement asked `nodePosition` for every node and got `null`
   for all of them — which the policy correctly reports as "not drawn on this
   Map", a true statement about the wrong situation. The draw effect now marks
   the graph as placed once the renderer holds it. Without that, the overlay
   waited for a frame event to correct itself, and the omission report was
   wrong until it arrived.
2. **Following the camera exactly means re-rendering the DOM per frame.** Cards
   are anchored per node, and the placement feeds the omission report, so
   re-placing on every `afterRender` would re-render the related list and the
   search rail sixty times a second for one pan. The Map had already answered
   this question for labels — `hideLabelsOnMove: true` — so cards follow the
   same rule: hidden while the camera moves, placed when it settles (D-138).
3. **TypeScript does not check a hyphenated JSX attribute against a
   component's props.** `data-map-statement="complete"` on a component that
   does not forward it compiles cleanly and renders nothing, so a test asserting
   on that attribute is asserting on something that was never there. `Bidi`
   takes its marks explicitly, the way `MapLegend`'s `Row` already did.

### What the constellation handed to later tasks

All three of these were `T-208`'s, and all three are settled; see
*Accessibility result*.

- **The overlay stays presentation.** `T-208` made the DOM path primary without
  giving the overlay a single control, and a scaffold test still fails if a
  button, link or field appears there.
- **Three panels competed for one screen** — the search rail, Quick Read and
  the related list. `T-207` made Quick Read a `<details>` and stopped;
  "collapsible rather than permanent competing panels" became `Disclosure`,
  written once, with each panel's count in its own summary (D-143).
- **The transient Peek is rendered in exactly one place.** It was the search
  rail's; moving it was allowed and it was moved, because that panel now folds
  and a card inside a closed `<details>` is invisible. It is the route's, still
  exactly one (invariant 13).
- **Four more numbers for `T-209` to measure**: the card budget, the cell size,
  the stage inset and the settle delay. They are stated once, in
  `constellation.ts`, beside the reasoning for each.
- The `data-map-card`, `data-map-related-entity`, `data-map-stage-omission` and
  `data-map-quickread` attributes are the test seam for "no neighbour silently
  disappears"; keep them true if these surfaces are restyled.

## Accessibility result (`T-208`, 2026-09-02)

The Map is usable without a pointer, without WebGL2 and in Persian, and the
route now says which state it is in rather than letting five conditions each
answer for themselves.

**Two honest-state functions, and the pairs are the point.** `mapState.ts`
holds `describeGraph` over the walk's own report and `describeCanvas` over the
renderer's, and every number in them is copied out of `GraphSnapshotState`.
What they exist for is the pairs a per-site condition collapses:

- **Unasked is not empty.** A snapshot with no page applied has nothing to
  count, so it prints no zeros -- printing them would be D-068's shape again,
  an empty answer to a question nobody asked, presented as an answer.
- **Partial is not whole.** `complete` is read, never recomputed (D-123).
- **Refused is not empty.** The pages that arrived stay countable, and the view
  says out loud that they are not an answer to the request that failed.
- **Undrawn is not absent.** The graph can be whole and undrawable at once.

**The renderer's two failures are two states** (D-140). A module that never
loaded is a browser with no WebGL2; a renderer that refused *this container* is
almost always its size and recovers on the next layout. One message for both
had been telling readers of the second case to find a different browser.

**The account is no longer only counts.** D-129 put the snapshot's counts
before the canvas because they were the only text a screen reader could reach;
`MapOutline` is the companion that was promised, and D-142 is why it is shaped
the way it is. It lists every entity the Map has drawn on the same
`MapResultCard` the search rail renders -- so the row a reader lands on carries
the statement, the provenance, the kind, a preview on focus, a Focus button
that is the *same* selection identity a mark is, and the Reader link -- in the
API's own order, bounded at 25 with everything past the bound counted and a
control that lists more. It is not windowed, and that is the trade `T-207` left
open, settled in the other direction: a row outside the DOM is a row no screen
reader and no in-page search can reach, which costs the very claim the list
exists to make.

**The canvas is a picture only while it is one** (D-141). `role="img"` and the
label are written only while a live renderer holds the graph, and the states
where it does not each say what they are: nothing drawn yet, nothing to draw,
no WebGL2, this container refused.

**The panels fold, and none of them goes quiet** (D-143). `Disclosure` is the
one collapsible panel; the count lives in the `<summary>`, so a folded panel
still states what it holds, and `preferOpen` follows the journey's step -- with
nothing selected the search rail is open, with something selected Quick Read
and the related list are, and the companion opens *itself* whenever it is the
only view of the graph.

**Motion is answered twice because there are two animators** (D-144). The
stylesheet neutralises everything the browser animates, in a blanket rule
rather than a list, because the list is what rots. `motion.ts` answers for the
camera, which the stylesheet cannot reach, and answers `undefined` when motion
is welcome rather than inventing a duration the renderer already has.

**Measured.** The frontend suite is **550 hermetic tests in 51 files**, plus
the same **22** against a running server -- 59 of them new here, none in an
existing file, and the whole suite was also run *against* `dev_api.py`: 572
passed, nothing skipped. The build cost, measured against this commit's own
before-and-after on this machine: the application bundle goes from 445.12 kB
to 454.34 kB (127.50 to 130.02 kB gzipped) and the stylesheet from 11.33 kB to
12.19 kB, while the renderer chunk does not move at all -- 371.90 kB before and
after. That last figure is the one worth reading: nothing `T-208` added is in
the chunk a browser without WebGL2 will fail to load, which is the point of the
whole task.

### Findings

Four, all fixed inside this task, and the first two are the ones a later task
would otherwise rediscover.

1. **A `<details>` fires `toggle` asynchronously -- including for a change a
   script made.** Rendering `open={state}` therefore turns every programmatic
   change into an event that arrives a task later and writes its own value back
   into the state that caused it. Two preference changes in quick succession
   (a page arrives, the renderer refuses it, and the companion's step changes
   twice) let the *first* event land after the second change, and the panel
   closed itself with nothing having been clicked -- while every unit test of
   the component passed, because a unit test changes the preference once. The
   element's `open` is now a prop at mount and imperative afterwards, and the
   toggle handler reads the *element* rather than trusting the event's payload.
2. **A canvas is described as drawing one render before it draws.** React runs
   a render and then its effects, so the render that first sees a page precedes
   the effect that hands the graph to the renderer. `T-207` found this in the
   constellation's first placement; here it made the picture flicker into
   existence and out again, which is what fired the `<details>` defect above.
   The fix is that "a live renderer holds this graph" is *state*, not a ref:
   a ref cannot say it, because it changes without a render.
3. **The one Peek was rendered inside a panel that now folds.** With something
   selected the search rail collapses, so a pointer on a mark opened a card
   inside a closed `<details>` -- invisible, on the one surface that has no
   other way to say what a mark states. It is the route's now, immediately
   below the stage, and still exactly one (invariant 13). Below rather than
   above, because a transient card that resizes the container makes the
   renderer re-measure on every hover.
4. **The counts and the camera do not arrive together.** A test that waited for
   the counts and then clicked *Zoom in* was clicking a disabled button, and it
   had been passing because the old `drawn` flag was true a render early --
   for the same reason finding 2 describes. Waiting for the control rather
   than for the counts is the honest wait: there is no camera until there is a
   renderer.

### What the accessibility pass hands to `T-209`

- **Three claims jsdom is the wrong witness for.** What Sigma's camera does
  with `{ duration: 0 }` on a real canvas; whether the narrow-screen stage
  keeps a real height (`allowInvalidContainer: false` makes that load-bearing);
  and whether a real screen reader and a real keyboard walk the DOM path the
  suite asserts by role, attribute and event.
- **Three more numbers to measure**: the outline's page of 25, the 44 px touch
  minimum, and the 48rem breakpoint at which the stage shortens.
- **Two guards that must keep failing**: there is one `<details>` in `web/src`
  and one reader of `prefers-reduced-motion`, and neither completeness list is
  windowed. Both are in `tests/test_ui_scaffold.py`.
- The `data-map-panel`, `data-map-panel-open`, `data-map-outline`,
  `data-map-reading` and `data-map-stage-companion` attributes are the test
  seam for the disclosure and the honest states; keep them true if these
  surfaces are restyled.

## Walk result (`T-209`, 2026-09-03)

**The Map has been opened in a browser.** Everything `T-202`–`T-208` built is
walked automatically now, on the real library and on the committed fixtures,
and the walk found four defects the jsdom suites could not have found, two
claims that were false in a browser, and one inverted piece of reasoning. All
of them are fixed; every number the phase had chosen by argument is measured
or replaced by a measured one.

**Where it ran.** macOS 26.5.2 on Apple silicon (arm64), **Google Chrome
152.0.7977.65** through Playwright's `channel: "chrome"` — the same browser and
machine `T-202` recorded — reaching WebGL2 through
`ANGLE (Apple, ANGLE Metal Renderer: Apple M5)`, a real GPU path. The harness is
`@playwright/test@1.62.1`, pinned exactly for the same reason the renderer is
(D-117): a walk's result is only about the versions that produced it. The whole
gate was then re-run on Playwright's **bundled Chromium 151.0.7922.34**, which
answers WebGL2 through SwiftShader — a software rasteriser — and passes there
too, which is worth more than it sounds: the route needs no GPU.

**What it was pointed at.** The **built bundle**, served by `vite preview` after
`npm run build`, rather than the dev server's module graph: `x2knwldg ui` serves
`dist/`, and the renderer is a lazily imported chunk (D-127), so "the module
never loaded" is a real network request in production. Behind it, the **real
API** — `create_app(project_root=…)` through `scripts/dev_api.py`, forwarded by
a proxy added to `vite.config.ts` for this purpose. Every expected number in the
specs is read back out of the payload the page was answered with, never typed
into a test, which is what lets one gate serve two libraries: the real ingested
project (86 entities, 118 relations, one page under the contract maximum) and
the committed `PASS`/`PARTIAL`/`FAIL` fixtures (7 and 9). **30 specs, four
files, green on both libraries and both drivers.**

### What it drew

`86 / 86` nodes and `118` edges, `0` held, `complete`, `truncated: false`,
`role="img"` present, one canvas, one WebGL2 context — the counts on screen
compared field by field with `/api/graph?limit=500`. Seven states were produced
and read: unasked/loading (no counts printed at all, camera disabled), empty
(`provenance_class=user` is a real filter with a real empty answer: `0 / 0`
counted, "nothing to draw", the companion opening itself), partial (the request
rewritten to five nodes a page: `held > 0`, `complete: false`), refused
(`503` on the second page: the first page still counted, the error stated, the
counts marked as not an answer to what failed), whole, undrawable
(`WebGL2RenderingContext` deleted before the bundle ran) and container-refused
(a stage of zero height).

### The numbers, now measured

| Chosen by argument | Measured | Kept? |
|---|---|---|
| Automatic labels at the overview (`labelDensity: 1`, `labelGridCellSize: 180`, `labelRenderedSizeThreshold: 14`) | **8 of 86 marks** carry a label at the framed overview; two zoom presses make about twelve speak in the visible area | kept — this is exactly the quiet overview D-122 asked for |
| `MAP_LABEL_NEIGHBOUR_BUDGET = 12` | 12 forced labels around the busiest entity drew **nine sentences into a cluster ~250 px across**: ForceAtlas2 pulls neighbours *towards* their focus, so a fan-out is the densest part of the picture and the worst place to bypass Sigma's grid | **4** (D-145) |
| `MAP_STAGE_CARD_CELL = 240` (a square grid cell) | The grid refused **7 of 8** neighbour cards that would have fitted *and* placed two that overlapped by two thirds of a card | replaced by a measured footprint, 320×248 and 416×176, and an overlap test (D-145) |
| `MAP_STAGE_CARD_BUDGET = 4` | Reached: 4 cards placed on the busiest entity once the focus is framed; 36 cards placed across 23 focuses | kept |
| `MAP_STAGE_CARD_INSET = 24`, `MAP_STAGE_SETTLE_MS = 150` | No clipped card and no card re-placed mid-gesture in any walk | kept |
| `MAP_OUTLINE_PAGE = 25` | 25 rows listed, 61 counted as unlisted, **four presses** of *List more* to reach all 86, every row in the DOM | kept |
| The 44 px touch minimum | Three classes of control were **smaller** on a coarse pointer: the label around the transcript checkbox (30 px), every link inside a card (23 px) and the skip link (41 px) | kept, and the rule widened to cover them |
| The 48rem breakpoint | Stage 1216×630 at 1440×900, 358×360 at 390×844, never below 240 px down to a 320 px viewport | kept |
| — | WebGL contexts over three filter changes and five route round trips: **12 created, 11 lost, 1 live**, one canvas | invariant 10 holds |
| — | The eased camera is mid-flight at 68 ms and 142 ms and final by 230 ms; with `prefers-reduced-motion: reduce` the **first frame after the press is already final** | D-144 confirmed on a real canvas |
| — | The stage begins **790 px down** a 1440×900 document, so about a sixth of the picture is above the fold on load and none of it at 390×844 | recorded, not changed — see finding 8 |

### The third input path, and the bound on the overlay

Two clauses of the `T-201` epic were still unwalked when the gate first went
green, and both are now in it.

**Touch.** "The same journey works with pointer, keyboard and touch; hover is
never required" had been asserted as target *sizes*; the journey itself had
never been tapped. It is now, on a 390x844 phone: the rail is opened, the query
typed, the search pressed, a result focused, Quick Read unfolded, a neighbour
opened and Back pressed — every step a `tap()`, with no pointer move anywhere
in the test, which is the only honest way to check that nothing needs hover. A
touch device fires no `mouseenter`, so a card that stated nothing until hovered
would fail this walk rather than merely look bad.

**The overlay's bound** (invariant 13). Exactly one primary card and exactly
one Peek, asserted against a real pointer: previewing a mark does not add a
second primary card, and a second preview — opened from a row this time —
*replaces* the first rather than joining it. And the completeness half: every
neighbour the policy refuses a card is still drawn as a mark and still listed
in the companion, which the walk checks by exhausting the outline's pages and
comparing the two sets.

One harness lesson came out of it, and it is the kind that wastes an afternoon:
Playwright's `isMobile: true` gives Chrome a **layout** viewport taller than
its visual one — 1305 against 844 here — so an element the page happily
scrolls "into view" can still be off-screen for a tap, and the tap retries
until the test times out. `hasTouch: true` is what makes `pointer: coarse`
match, which is what these tests are actually about, so that is what they use.

### The anti-pogo baseline, and the threshold it sets

The task asked for the click/backtrack cost of the circle-and-label experience
to be recorded *before* a UX threshold was set. It is this, and it is worse than
the phase assumed.

- At the framed overview, **8 of 86 marks carry any text at all**, and a
  drawn label is cut at 42 code points (`MAP_LABEL_CHARS.normal`).
- **34 of the 86 statements share a prefix with another node at every budget
  we could choose**, including the full stored text: 17 pairs are the *same
  statement to the character* — a source-grounded knowledge unit and the
  derived concept that expresses it, joined by `expresses_concept`. For those
  pairs the picture separates them by node shape (both `derived` in one case,
  so not even that) and by hue for `kind`, and by nothing else.
- So from the canvas alone, identifying a mark costs **one selection per
  candidate** — a click and a backtrack each — and for those 17 pairs no
  number of clicks on the *picture* distinguishes them; only the record does.

Against that, the shipped route: a related row carries the neighbour's verbatim
statement, its relation and direction in words, its provenance as a glyph and a
badge, its kind and its identifier, **before anything is opened** — zero clicks
to decide, one to open, and Back returns to the prior focus with the Map never
unmounted. The threshold this walk sets is therefore about the row rather than
the card: *a neighbour must be describable from what is on screen before it is
opened*, and the semantic related list is what guarantees it. The stage's cards
are a second view of those rows and are bounded; on this graph they carry the
focused statement plus one to four neighbours, and every neighbour without one
is counted with a reason.

### Findings

Nine. Four were defects, two were claims that a browser falsified, one was a
piece of reasoning that turned out to be backwards, and two are about the
harness itself.

1. **A renderer that refused its container leaked a WebGL context, every
   time.** Sigma appends its canvases and takes their context in its
   constructor and validates the container *afterwards*, so a zero-sized stage
   throws with a live context already attached — and `MapSession` never
   receives the object whose `kill()` would release it. Measured before the
   fix: seven refused attaches, **seven contexts created, none lost, seven
   canvases piling up in the stage**, and leaving the route released none of
   them. Browsers cap live contexts at around sixteen and answer an excess by
   losing the *oldest*, so the symptom is a different Map going blank later.
   This is ADR 0005 invariant 10, and the jsdom suites could not see it because
   a fake factory throws without having created anything. `MapSession.attach`
   now empties the container and loses the context explicitly on a refusal
   (D-147), and the browser gate counts contexts so the invariant is observed
   rather than assumed.
2. **Selection and the camera had never spoken.** The camera framed the whole
   86-node graph, so a focus sat wherever the layout had put it and its whole
   neighbourhood spanned about a tenth of the stage — which meant *every*
   neighbour card was refused for covering the focused one, on every focus in a
   twenty-entity sample. Worse, `Zoom in` zooms about the **middle of the
   stage** rather than about the selection, so a reader who selected a node and
   pressed it twice pushed the selection off the stage entirely while the route
   went on saying, correctly, that the graph was drawn. Two halves that both
   knew where the focus was, with nothing carrying it between them — the same
   shape as D-069. `MapSession.frame` and D-146 are the fix.
3. **The density policy's grid answered the wrong question.** A 240 px square
   cell asks "is another card in this cell?"; the question is "would this card
   cover one?" — and two anchors either side of a cell boundary can be a pixel
   apart while two in one cell can be 300 apart, so the grid managed to do both
   halves of its job wrong at once (7 of 8 refused, and two placed cards
   overlapping). Replaced by the card's measured footprint. Then a second
   finding surfaced *inside* the fix: a card opens towards the middle of the
   stage so it will not be clipped, so two marks either side of the middle grow
   towards each other and meet. The policy now tries all four orientations in a
   stated order before refusing, and the reserved rectangle includes the mark
   itself, because two cards pointing into the same four pixels from opposite
   directions is the same confusion by another route (D-145).
4. **Escape could not dismiss a Peek opened from the canvas.** `T-208` moved
   the one Peek to the route and added Escape "from anywhere on the route" as a
   React `onKeyDown` on the route's own element — which only ever sees a key
   pressed while focus is *inside* it. A canvas takes no focus, so the one
   surface with no other way to dismiss a Peek was the one surface where the
   key did nothing. The route now listens on `window`, and only while a Peek is
   open (D-148).
5. **"1 hops from the focus."** Also "1 related entities", and "1 returned
   relations name an endpoint the response did not return" — three plural
   errors in one sentence about one real neighbourhood, on a route whose entire
   argument is that the words on screen are the record's own. `interpolate`
   grew one plural form, `{count|singular|plural}`, used by the Map's count
   messages in English and by nothing in Persian, which keeps the singular
   after a numeral (D-149).
6. **`allowInvalidContainer: false` refuses only an *exactly* zero
   dimension.** A stage two pixels high is accepted, drawn into, and reported
   as a picture — with `role="img"` and "Knowledge graph, drawn". So D-144's
   reasoning was backwards: the stylesheet's minimum on the stage is
   load-bearing not because a collapsed container becomes a stated refusal, but
   because it does *not*. The floor is what stands between a small window and
   an unreadable two-pixel graph the route calls drawn (D-147), and
   `tests/test_ui_scaffold.py` now fails if the minimum disappears.
7. **The beta's `GL_INVALID_OPERATION` noise is unchanged.** Chrome still logs
   `glDrawArraysInstanced: Active draw buffers with missing fragment shader
   outputs` a few times per context while drawing everything correctly, exactly
   as `T-202` recorded (finding 2). The gate names it and ignores it, and
   fails on any *other* console error, page error or failed request; the only
   404 in a clean walk is `/favicon.ico`, which this project does not define.
8. **The picture is the last thing on the route to reach the screen.** The
   counts come before the canvas by decision (D-129), and with the title, the
   filters, the counts panel, the camera controls and the search rail above it
   the stage starts 790 px down a 1440×900 document — and below the fold
   entirely on a phone. Nothing was changed for it: the order is deliberate,
   the DOM path is the primary one (D-142), and the alternative is to weaken
   the one description that survives when the picture cannot be read. It is
   recorded because it is the first thing to reconsider if the Map ever becomes
   the route people arrive on.
9. **Two findings about the harness, both worth keeping.** A Peek is React
   state, so it appears a render *after* the pointer move that opened it and
   stays open until the pointer leaves the mark: a sweep that reads the DOM
   immediately after each move reports the hit one probe late, which passes a
   hover assertion and then clicks empty canvas. And a Peek is rendered below
   the stage, so opening one changes the document's height and a scrolled
   document has its scroll clamped — which moves the stage under a coordinate
   measured before any of that. `browser/gate.ts` confirms a mark before
   returning it and re-measures the stage with the Peek open, and says why.

### What the walk hands to Phase 3

- **The gate is the regression net, and CI runs it.** `npm run browser` walks
  the committed fixtures with both servers started by the config;
  `X2KNWLDG_BROWSER_PROJECT_ROOT` points it at a real project, which is how the
  measurements above were taken. `npm run typecheck:browser` type-checks the
  gate itself, because Playwright transpiles specs without checking them.
- **`web/browser/` imports nothing from `web/src`, on purpose.** A spec that
  imported `MAP_STAGE_CARD_BOX` would agree with whatever the module says,
  which is the one thing a gate must not do. `tests/test_ui_scaffold.py` fails
  if that changes, and fails if the harness leaks into the application.
- **Three numbers are still starting values rather than measurements**, because
  the real library gives them nothing to bite on: `PREVIEW_LIMIT` (240
  characters in a rail), `MAP_STAGE_PRIMARY_CHARS`/`MAP_STAGE_NEIGHBOUR_CHARS`
  and `NEIGHBOURHOOD_LIMIT`. A library with a fan-out larger than eight or a
  statement longer than 121 characters is where they will first be wrong.
- **The framing margin is calibrated, not derived.** `MAP_FOCUS_MARGIN = 1.2`
  is the tightest framing at which no neighbour's mark falls outside the card
  inset, measured over 23 focuses; the relation between a camera ratio and
  pixels is Sigma's own, so a renderer upgrade should re-run that table
  (`mapSession.ts` states it).
- **A pixel golden is still refused** (`PROJECT_MANAGEMENT.md` `T-209`). Where
  the walk needed to compare two pictures it compares them *within one
  browser* — an overview against the same overview after *Reset the view* — and
  determinism across a reload is asserted on the **card anchors**, which are
  the renderer's own answer for where each mark is, rather than on pixels that
  differ between a Metal driver and a software rasteriser for reasons that are
  not defects.

## References

- Playwright: <https://playwright.dev/docs/intro>
- Playwright visual comparisons, and why this gate does not use one:
  <https://playwright.dev/docs/test-snapshots>
- Sigma v4 beta site: <https://v4.sigmajs.org/>
- Sigma v4 quickstart (`4.0.0-beta.5` at decision time):
  <https://v4.sigmajs.org/get-started/quickstart/>
- Sigma v3 → v4 migration: <https://v4.sigmajs.org/how-to/technical/migration-v3-v4/>
- Sigma v4 announcement and maintainer maturity update:
  <https://github.com/jacomyal/sigma.js/discussions/1539>
- Sigma releases: <https://github.com/jacomyal/sigma.js/releases/>
- Sigma interaction events: <https://v4.sigmajs.org/reference/events/>
- Sigma graph-coordinate HTML/SVG overlays:
  <https://v4.sigmajs.org/how-to/layers/sync-html-svg/>
- Graphology instantiation: <https://graphology.github.io/instantiation.html>
- Graphology mutation/keyed edges: <https://graphology.github.io/mutation.html>
- Graphology ForceAtlas2: <https://graphology.github.io/standard-library/layout-forceatlas2.html>
- W3C keyboard technique G202: <https://www.w3.org/WAI/WCAG22/Techniques/general/G202.html>
- W3C accessibility principles: <https://www.w3.org/WAI/fundamentals/accessibility-principles/>
- Shneiderman, *The Eyes Have It*: overview, zoom/filter and details on demand:
  <https://hci.stanford.edu/courses/cs448b/papers/shneiderman96eyes.pdf>
- Li et al., *Knowledge Graphs in Practice*: contextual knowledge cards and preserving
  discoverability: <https://www.cs.tufts.edu/~remco/publications/2023/TVCG2023-KnowledgeGraph.pdf>
- Nielsen Norman Group, information scent and pogo-sticking:
  <https://www.nngroup.com/articles/information-scent/>
  <https://www.nngroup.com/articles/pogo-sticking/>
- [`PROJECT_MANAGEMENT.md`](../PROJECT_MANAGEMENT.md) — `T-201`–`T-209`, D-117 … D-144
- [`KNOWLEDGE_CANVAS_PLAN.md`](../KNOWLEDGE_CANVAS_PLAN.md) §6.3, §13.3, §16 Phase 2
