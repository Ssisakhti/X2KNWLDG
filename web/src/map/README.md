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

## Selection has one grammar, and it lives in the URL (`T-206`)

| Path | Holds |
|---|---|
| `../lib/mapLink.ts` | The Map's URL grammar: build **and** parse selection and filters |
| `useMapFocus.ts` | That grammar bound to the router: focus writes history, Back restores it |
| `useMapPeek.ts` | The one transient Peek: hover or keyboard focus, no history, no selection |
| `useMapSearch.ts` | Two corpora — the loaded graph, matched locally, and `GET /api/search` |
| `../components/MapSearchRail.tsx` | The rail: query, both result lists, the focus statement, the Peek |
| `../components/MapResultCard.tsx` | One preview card, and the one preview-truncation policy |
| `../components/MapPeekCard.tsx` | The Peek card itself |

The grammar is
`#/map?focus=<global_id>&source_id=<id>&provenance_class=<class>&relation_vocabulary=<vocab>`.
Three of those four names are the API's own, because `GET /api/graph` accepts
exactly those three filters and a shorter alias would be a second vocabulary
for one set of parameters (invariant 7); `graphFiltersOf` is therefore an
identity rather than a mapping. `focus` is ours, and it is an *identity*: the
entity's existing three-part `global_id`, never a label, an index or a
synthesised key.

Malformed state is ignored, exactly as `readerLink` ignores an unreadable `t`.
`?focus=KU-000001` selects **nothing** rather than guessing the missing parts,
and `?provenance_class=derivd` filters nothing rather than being read as
`derived` — a repaired value would filter a graph the user never asked to
filter, and it would look like working software. `mapPath` re-reads every value
through the same parser, so it cannot write a link its own reader would drop,
and the round trip is a property of the grammar rather than a habit of its
callers.

The search query is deliberately **not** in the grammar: D-119 names selection
and the three filters, and a query in the URL would write a history entry per
keystroke or need a second rule about when it does not.

## Focus is history; Peek is not

They are two modules for one reason: ADR 0005 invariant 14 is two statements,
and a flag inside one hook would let them be confused. `useMapFocus` navigates
— same route, different query, so the route element is never unmounted and the
accumulated graph survives Back. `useMapPeek` holds a single value and calls
nothing: a pointer crossing eight nodes on its way to the ninth leaves no
entries the reader never chose. Re-selecting what is already selected pushes
nothing either, because Back would then appear to do nothing.

At most one Peek exists because the state *is* one value, and only a **loaded**
node can be peeked: the record comes from the accumulated graph through
`recordLookup`, so a Peek can never show a record the Map does not hold. A
`leave` for the node the pointer just left arrives *after* the `enter` for the
one it arrived at, so `close(id)` closes only the Peek it names.

## Two corpora, never merged into one ranked list

`useMapSearch` answers a query twice: from the loaded snapshot, in the browser,
by `label`/`global_id`/`local_id`/`library_id` substring; and from
`GET /api/search`, which reaches entities no page has loaded. They are labelled
and kept apart because merging them needs a client-side score across two
incomparable sources, and a score presented as relevance is the invented
quantity invariant 15 forbids. The local list states how many matched against
how many are loaded, so "nothing matches" and "nothing is loaded" stay
distinguishable.

The indexed half runs through `usePaged`, which is where D-079's lesson already
lives: a response that answers a replaced question is aborted and dropped
whole, cursor included. `include_transcript` defaults to `false` — a caption is
not an entity in v1 — and the rail can turn it on, at which point caption hits
arrive **explained and unaddressable**: no `global_id`, no Focus control, and a
route to their source and timestamp instead. A knowledge-unit hit whose run
states no `video_id` has `global_id: null` by the contract's own decision and
is treated the same way. The absence of the button is the signal; a disabled
one would claim the address exists and is merely unavailable.

Card text is the record's, verbatim (D-131). `previewText` cuts a long
statement on a word boundary and returns a **prefix**, and the card renders a
visible marker beside the cut — nothing is summarised, and nothing is cut
inside a data structure. `T-207`'s on-stage cards must call the same function
rather than write a second policy (§8.6: one card-content formatter).

## What `MapView` wires (`T-206` → the integrator)

```tsx
const focus = useMapFocus();                       // URL ⇄ selection, history
const peek = useMapPeek(recordLookup(walk.graph)); // one Peek, above both surfaces
<MapSearchRail
  graph={walk.graph}
  revision={walk.state.snapshotId}
  focus={focus.focus}
  onFocus={focus.focusEntity}
  peek={peek}
  sourceScope={focus.state.source}
/>
```

`useGraphWalk` then takes `focus.filters` and `[focus.state.source,
focus.state.provenance, focus.state.vocabulary]` as its `deps`, so a filter in
the URL is the question the walk asks. A Sigma `clickNode` handler calls
`focus.focusEntity(id)` — the *same* function the rail's buttons call, which is
what keeps pointer and keyboard on one identity — and `enterNode`/`leaveNode`
call `peek.open(id)`/`peek.close(id)`. Render `peek.peek` in exactly one place:
two components reading one binding would draw the same Peek twice.

## Visual semantics: one style table, in reducers (`T-205`)

Two more modules, and neither of them touches the graph:

| Path | Holds |
|---|---|
| `mapStyle.ts` | **The** style table — provenance/kind for nodes, vocabulary/provenance for edges, the four interaction states — plus `MapStyle`, the view state the reducers read |
| `labelPolicy.ts` | D-122: display truncation, the density and zoom rule, and the Sigma settings that implement them |

`MapLegend` and `MapFilters` are in [`../components/`](../components/), and the
legend reads the same tables the reducers draw from, so agreeing with the marks
is structural rather than remembered.

### Nothing is written; everything is computed

D-124 says a node carries `x`, `y` and the record. So every display attribute
is computed at draw time by a reducer, from the record and from the current
view state, and `sigmaRenderer.ts` passes the two reducers into Sigma. Running
them over the real snapshot and then asserting the node attributes are still
`x`, `y` and `record` is the strongest statement available that styling adds
nothing to the data — and it is a test, in `mapStyle.test.ts`.

### Which channel carries which variable

| Variable | Channel | Survives greyscale |
|---|---|---|
| node `provenance_class` | shape: circle / diamond / square, triangle for a value this build does not know | yes |
| node `kind` | hue, one per kind family | no |
| edge `relation_vocabulary` | head shape and line weight | yes |
| edge `provenance_class` | hue, and a mark at the tail | yes |
| interaction state | size, opacity, depth layer, halo ring, label | yes |

Provenance owns shape on both nodes and edges because it is the distinction a
reader must never get wrong — `source` is grounded in the medium, `derived` is
synthesis, `user` is neither — and ADR 0005 invariant 9 forbids carrying it in
colour alone. Kind has 31 values and cannot have a non-colour channel of its
own; it is a categorical hint that the legend, the label and the DOM cards
spell out in words, and no decision in the approved journey rests on telling
two kind hues apart. `KIND_FAMILY` is a `Record<KnowledgeKind, …>` mirroring
`artifacts.SECTION_ORDER`, so a kind added to the contract is a compile error
here rather than a node that quietly renders as something else.

A `provenance_class` or `relation_vocabulary` the build does not recognise gets
its own mark rather than the nearest known one. A build of this UI can be older
than the index the server is serving, and rounding an unknown provenance to
`source` would be the client making a claim about provenance.

Colours are hex literals, not CSS tokens: WebGL cannot read a custom property,
so the canvas palette is one mid-tone set chosen to survive both the light and
the dark stage, while the legend beside it uses the tokens.

### Labels: truncate for display, ration by density

`renderLabels` is on now, which it was not in `T-204`. The blanket `false` was
holding the door until this policy existed, and it has two halves:

- **Truncation is presentational.** `truncateForDisplay` collapses whitespace,
  cuts by code point (the knowledge is Persian as often as English), prefers a
  word boundary, and appends `…` so the cut is *visible*. The canonical text is
  untouched and Quick Read shows it whole (D-131, invariant 12). Budgets run
  from 42 characters for an ambient label to 160 for the focus — never the 4096
  a `label` may hold.
- **Density is a rule.** A label is forced only for the focus, the node under
  the pointer or the keyboard, and up to `MAP_LABEL_NEIGHBOUR_BUDGET` (12)
  neighbours of the focus. Everything else is `"auto"`, and Sigma's own grid
  decides it: one label per 180×180 px cell, and only for a node drawn at least
  14 px across, which is the zoom rule — the overview is quiet and zooming in
  is what makes it speak. Once something *is* focused, unrelated nodes lose
  their labels and dim to 0.35; they are never hidden, because de-emphasis is
  not absence.
- Edge labels are stricter: an edge names its real relation only while it is on
  an active path. An overview labelling 118 edges would be the gate's pile with
  smaller words.

Exceeding the neighbour budget costs legibility, never data: the labels return
to `"auto"`, every neighbour keeps its mark, and `T-207`'s related list still
names all of them (invariant 13).

### Primitives, and what `T-209` has to look at

Sigma v4's default primitive set is one node shape, two edge paths and no
extremities — a palette with exactly one channel, colour. `sigmaRenderer.ts`
therefore declares the shapes, the `curved` path and the five extremities the
table needs. Three consequences worth knowing:

- The names in `MapNodeShape`/`MapEdgeExtremity` must match the declared
  primitives. Sigma silently substitutes its first declared shape for a name it
  does not know, so a typo is a wrong drawing rather than an error.
- `parallelPath: "curved"` exists because this graph joins one pair of entities
  with a canonical relation *and* a library-synthetic one often enough that two
  straight lines would be one drawn line and one edge the Map counted but
  nobody can see.
- None of this has been drawn in a browser yet. `T-202` proved the *default*
  primitives on this machine; the declared set, the halo's backdrop border and
  the four label numbers are `T-209`'s to walk. The build cost is measured: the
  renderer chunk goes from 362 kB to 377 kB (98 kB gzipped), still loaded by no
  route but the Map.

### Hover must not move the graph

`MapSession.refresh()` is `T-205`'s one addition to the lifecycle, and the
distinction from `update()` is the reason it exists. `update()` re-settles the
whole layout because a *page* arrived and the structure changed (D-128), so the
picture is allowed to move. A change of hover or selection changes no structure
at all — only what the reducers compute from it — so it goes through `refresh`,
which redraws with the positions untouched. `mapStyle.setView` returns whether
anything actually changed, so a pointer moving inside the node it is already on
costs nothing.
