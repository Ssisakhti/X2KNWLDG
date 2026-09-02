# `web/src/map/` — the Knowledge Map

Phase 2: `T-202`'s seeding and compatibility harness, `T-203`'s projection, and
`T-204`'s renderer lifecycle
([ADR 0005](../../../docs/adr/0005-knowledge-map-client.md)):

| Path | Holds |
|---|---|
| `seedPositions.ts` | Deterministic, non-zero starting positions, hashed from a node's `global_id` |
| `graphProjection.ts` | The typed conversion of one `EntityRef`/`IndexedRelation` into graph attributes, and the equality that decides whether a repeated identity is a repeat or a conflict |
| `graphSnapshot.ts` | `GraphSnapshot` — pages accumulate into one `MultiDirectedGraph`, edges wait for their endpoints, and the snapshot states what it does and does not yet hold |
| `graphWalk.ts` | `GraphWalk` — the cancellable, framework-free driver: one question at a time, opaque cursors carried and never read |
| `useGraphWalk.ts` | That walk bound to a component: `deps` name the question, unmount disposes it, and nothing here decides what a page means |
| `mapSession.ts` | `MapSession` — **the** renderer lifecycle: lay out, draw, resize, zoom, reset, kill. Framework-free, and reached through an injected factory |
| `sigmaRenderer.ts` | The only module that imports `sigma`, and the only place the application constructs it |
| `gate/` | The `T-202` compatibility harness: a single-page graph builder and the renderer lifecycle it exercises |

The route itself is [`../views/MapView.tsx`](../views/MapView.tsx). The style
matrix, `mapLink`, the neighbourhood and the inspector are `T-205`–`T-208`.

## Seeding is not decoration

A seed is a function of a node's **identity**, never of its index in a page.
A Map accumulates pages (D-118), so an index-derived seed moves a node when the
next page arrives, and a reload cannot reproduce the picture the user saw. And
no node is seeded at the origin, because ForceAtlas2's repulsion divides by the
distance between two bodies.

Seed where a node is **inserted**, not in a pass before the layout.
`graphology-layout-forceatlas2` reads `attr.x` straight into a `Float32Array`,
so a node with no position becomes `NaN`, raises nothing, and is simply not
drawn — a real entity missing from the Map with no error to notice.
`nodeAttributes` is therefore the only way a node is built.

## A page is not a graph

D-059: a page of `/api/graph` carries an edge when both endpoints pass the node
filter and **at least one** of them is on that page. So a page can hold an edge
whose far endpoint arrives later, and the same edge comes back on the later
page too. Handing one page to a renderer has three outcomes and no fourth: the
edge dangles, the far node gets invented, or connectivity is dropped and a full
walk no longer reproduces the API's graph.

`GraphSnapshot` is the alternative. Nodes dedupe by `global_id`, edges by their
own `id`, and an edge is **held** — never drawn, never discarded — until both
of its endpoints have arrived. Measured against the real 86-node/118-edge
graph, a walk at one node per page holds up to 54 edges at once and ends with
none: 86 nodes and 118 edges, the same set a single request returns. Page size
does not change the graph.

A repeated identity carrying a *different* record is a `GraphConflictError`,
not a merge — a merge would draw a record no request returned. Absent and
`null` are the same statement, because the contract spells every optional field
`field?: T | null`; anything else is a disagreement, and the refusal names the
field.

## What the projection may add

`x`, `y`, and the API's record. Nothing else — no label, no size, no colour.
The record is stored verbatim so the Map can be read as evidence of what the
index holds; display attributes belong to the renderer's reducers (`T-205`),
and D-122 forbids drawing the raw `label` anyway, since a knowledge unit's
label is its whole `normalized_statement`.

## Complete is not "the cursor ran out"

`truncated` is the API's statement about **a page**, and both repository
implementations compute it against the whole filtered node set — so the *last*
page of a multi-page walk reports `truncated: true` as well. Neither fact alone
settles whether the accumulated graph is whole, so `GraphSnapshot.state` reports
them separately and calls the graph complete only when the walk has finished,
no edge is pending, and either the API said nothing was cut short or the loaded
node count has reached the stated `total` (D-123). A `total` of `null` is
*unknown*, never zero, so a snapshot that cannot prove it is whole says so.

## One question at a time

`GraphWalk.open` retires the generation in flight, aborts its request, and
builds a new snapshot with a new graph. A page that answers after its question
stopped being asked is dropped whole — a page's nodes, edges and cursor only
mean anything together (D-079). Two snapshots never share a graph object, so
"filter snapshots never mix" is structural rather than remembered.

Cursors are carried and handed back, never parsed, compared, or displayed.

## The gate is a harness, not the Map

`gate/` answers one question — does the pinned renderer draw and release the
real graph on this machine — and it is deliberately quarantined:

- `web/gate.html` is served only by `npm run dev`. Vite's build input is
  `index.html` alone, so the harness is not in `dist/`.
- No application module imports it, and it defines no route.
  `tests/test_ui_scaffold.py` fails if either changes.
- Its single-page graph builder is **not** the `T-203` projection and must not
  grow into one: page accumulation, conflict refusal and holding an edge until
  both endpoints arrive live in `graphSnapshot.ts`.

Walking it:

```bash
../.venv/bin/python scripts/dev_api.py --project-root ..   # the real library
npm run dev                                               # then open /gate.html
```

Load and render, then use Update, Resize, Select, Teardown and Cycle ×20. The
page states what it drew — nodes and edges drawn against nodes and edges
returned, edges with an endpoint off the page, self-loops, `truncated` — and
counts every WebGL context it has created against the ones that have been lost.
A teardown that leaves a context live is the leak invariant 10 of ADR 0005
forbids. The recorded result of that walk, its measurements and its four
findings are in the ADR under *Gate result*.

## One renderer, and a kill that is counted

`MapSession` is the only Sigma lifecycle in the application, and
`tests/test_ui_scaffold.py` fails if a second constructor appears. The reason is
that the failure it guards against is a *sequence*: a second `attach` must kill
the first renderer, `kill` must be idempotent because an unmount can follow a
replacement, and an operation arriving after the kill — a `ResizeObserver`
callback, a page that merged while the route was closing — must do nothing
rather than throw or reach a dead context.

None of that is observable in jsdom, which has no WebGL, so the renderer is
reached through `MapRenderer`/`MapRendererFactory` and the tests inject a fake
that records the order it was asked in. `creates` and `kills` must finish equal
after any sequence, which is how a leaked WebGL context shows up as a number
rather than as a blank canvas in an unrelated place: the browser answers an
excess of live contexts by losing the **oldest** one. Sigma v4's `kill()` calls
`WEBGL_lose_context.loseContext()`, so `T-202` was able to prove the release
really happens; this module is what keeps calling it.

React 19's `StrictMode` double-invokes effects, so an attach that did not kill
its predecessor would leak a context on the very first mount.

## Sigma is loaded on demand, not imported

`sigmaRenderer.ts` is the only module that names `sigma`, and nothing imports it
statically. That is not tidiness: `sigma`'s default primitives call `layerFill`
while the module body evaluates, and `layerFill` destructures `UNSIGNED_BYTE`
off the global `WebGL2RenderingContext`, which jsdom does not define. A static
import anywhere in the application's module graph is therefore a
`ReferenceError` at load that fails the Library's and the Reader's suites for a
module neither of them uses. `MapView` reaches it through
`import("../map/sigmaRenderer")` instead, which also keeps a 362 kB chunk out of
the two routes that draw no graph.

## The layout moves when the graph grows

A continuation page's nodes arrive on their identity seeds, and a seed says
nothing about the structure the layout has already found — drawn unrelaxed, a
second page is a scatter of dots over a settled graph. So `update()` relaxes the
whole graph again and the picture shifts. The alternative is pinning what is
placed, and `graphology-layout-forceatlas2` reads a `fixed` node attribute for
exactly that: it is not used, because D-124 lets a node carry `x`, `y` and the
API's record and nothing else, and layout state on the data is the thing that
rule exists to prevent.

## Running the projection against the real server

The unit tests are hermetic; `graphWalk.integration.test.ts` is not, and it is
the only place page size is proved not to change the graph:

```bash
../.venv/bin/python scripts/dev_api.py --project-root ..    # or --fixtures
X2KNWLDG_API_BASE=http://127.0.0.1:8931 npm test
```
