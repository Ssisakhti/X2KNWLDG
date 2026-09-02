# `web/src/map/` — the Knowledge Map

Phase 2: `T-202`'s seeding and compatibility harness, `T-203`'s projection,
`T-204`'s renderer lifecycle, `T-205`'s style table, `T-206`'s URL grammar,
`T-207`'s bounded neighbourhood and `T-208`'s honest states
([ADR 0005](../../../docs/adr/0005-knowledge-map-client.md)):

| Path | Holds |
|---|---|
| `seedPositions.ts` | Deterministic, non-zero starting positions, hashed from a node's `global_id` |
| `graphProjection.ts` | The typed conversion of one `EntityRef`/`IndexedRelation` into graph attributes, and the equality that decides whether a repeated identity is a repeat or a conflict |
| `graphSnapshot.ts` | `GraphSnapshot` — pages accumulate into one `MultiDirectedGraph`, edges wait for their endpoints, and the snapshot states what it does and does not yet hold |
| `graphWalk.ts` | `GraphWalk` — the cancellable, framework-free driver: one question at a time, opaque cursors carried and never read |
| `useGraphWalk.ts` | That walk bound to a component: `deps` name the question, unmount disposes it, and nothing here decides what a page means |
| `mapSession.ts` | `MapSession` — **the** renderer lifecycle: lay out, draw, refresh, resize, zoom, reset, kill, plus the canvas's event and coordinate adapters. Framework-free, and reached through an injected factory |
| `sigmaRenderer.ts` | The only module that imports `sigma`, and the only place the application constructs it |
| `mapState.ts` | What the Map is **allowed to say about itself**: `describeGraph` over the walk's report, `describeCanvas` over the renderer's. Two total functions, no state, and the four pairs they keep apart are the reason they exist |
| `outline.ts` | The drawn graph as a list: the accumulated graph in the API's own order, each row formatted by the one card formatter, with drawn relations counted and the bound's remainder counted too |
| `motion.ts` | The **only** reader of `prefers-reduced-motion` in the application, because the stylesheet cannot reach a camera animated in script on a canvas |
| `gate/` | The `T-202` compatibility harness: a single-page graph builder and the renderer lifecycle it exercises |

The `T-209` browser gate is deliberately **not** in here: it is
[`web/browser/`](../../browser/gate.ts), outside `src` entirely, and it imports
nothing from these modules — a spec that imported the number it is checking
would agree with whatever the module says.

The route itself is [`../views/MapView.tsx`](../views/MapView.tsx), and it is
the join rather than a fourth copy of anything. **Every number in here has now
been walked in a browser** by `T-209` ([`../../browser/`](../../browser/gate.ts)):
most were kept, three were replaced by what Chrome measured, and the walk is
where four defects nothing in jsdom could reach were found. ADR 0005
§ *Walk result* is the record; D-145–D-149 are what changed.

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
inside a data structure. `T-207`'s on-stage cards call the same function
rather than a second policy (§8.6: one card-content formatter).

## What `MapView` wires

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
the URL is the question the walk asks. The canvas's `clickNode` handler calls
`focus.focusEntity(id)` — the *same* function the rail's buttons call, which is
what keeps pointer, keyboard and URL on one identity — and
`enterNode`/`leaveNode` call `peek.open(id)`/`peek.close(id)`, which
`MapSession`'s handler slot routes for it (`T-207`). Render `peek.peek` in
exactly one place: two components reading one binding would draw the same Peek
twice, and it is rendered in the search rail.

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
  the pointer or the keyboard, and up to `MAP_LABEL_NEIGHBOUR_BUDGET` (4)
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
to `"auto"`, every neighbour keeps its mark, and `T-207`'s related list names
all of them (invariant 13).

### Primitives, and what the browser said about them

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
- All of it is drawn now (`T-209`). The declared shapes, the extremities, the
  curved parallel path and the selected mark's halo all render on the real
  86-node graph, in Chrome over the GPU and on a software rasteriser. Three of
  the four label numbers are kept: the overview draws **8 labels over 86
  marks**, which is the quiet overview D-122 asked for, and two zoom presses
  make about twelve speak. The fourth was wrong — see the neighbour budget
  below. The build cost is measured: the renderer chunk goes from 362 kB to
  377 kB (98 kB gzipped), still loaded by no route but the Map.

### Hover must not move the graph

`MapSession.refresh()` is `T-205`'s one addition to the lifecycle, and the
distinction from `update()` is the reason it exists. `update()` re-settles the
whole layout because a *page* arrived and the structure changed (D-128), so the
picture is allowed to move. A change of hover or selection changes no structure
at all — only what the reducers compute from it — so it goes through `refresh`,
which redraws with the positions untouched. `mapStyle.setView` returns whether
anything actually changed, so a pointer moving inside the node it is already on
costs nothing.

## A selection asks two questions (`T-207`)

| Path | Holds |
|---|---|
| `neighbourhood.ts` | One `/api/graph/neighborhood/{id}` response, projected: hops from the centre, each relation's own direction, and the complete related list in a deterministic order |
| `constellation.ts` | D-132's stated density policy: which cards the stage may carry, and a **counted reason** for every neighbour it refuses |
| `useNeighbourhood.ts` | The two requests bound to a component — the entity and its neighbourhood, failing separately |
| `../components/MapConstellation.tsx` | The overlay itself: presentation over the marks, and nothing else |
| `../components/MapRelatedList.tsx` | The surface that cannot omit anything |
| `../components/MapQuickRead.tsx` | The complete stored record, in D-131's order |
| `../components/MapRelation.tsx` | The one place a connection is named |

`/api/entities/{entity_id}` says what the selected entity **is** — even when
the loaded pages do not hold it, which happens whenever a focus arrives from a
URL, from a search hit no page has reached, or under a filter that excludes the
entity's own provenance class. It is also the only way a `404 not_found` can be
*stated*: "this id names nothing" and "this Map has not loaded it" are
different answers, and until now the rail could not tell them apart.

### The neighbourhood is not the graph

It goes through the same projection — `nodeAttributes`, `edgeAttributes` and
`recordDifference`, refusal included — but into a structure of its own, which
is replaced whole when the selection or the depth changes and is never handed
to a renderer (D-134). `GraphSnapshot` answers one question, the pages the
URL's three filters describe, and its counts are read against the `total` the
server counted *for that question*. A neighbourhood ignores those filters and
reaches whatever is within `depth` hops, so merging it would draw nodes the
filters exclude and turn `complete` into a claim about a set nobody asked for.

A `MultiDirectedGraph` is still used, for adjacency and nothing else: hop
distance is a walk over the returned edges, and the walk is **undirected**,
because a reader following `supports` backwards has still reached the
neighbour. Direction is not lost — it is stated per relation, where it belongs.

A neighbour more than one hop out therefore states *that* rather than
borrowing the near neighbour's relation, which would be an edge no request
returned.

### Every returned neighbour is listed, always

The stage can only place the cards that fit, so the list that cannot omit
anything is the one that carries completeness (invariant 13, R20). Nothing in
`neighbourhood.ts` filters, slices or caps, and `MapRelatedList` renders all of
it. The order is a **sort key, not a score**: hops, then the relation as the
record spells it, then the `global_id` — three stated facts compared in a fixed
order, so the list is identical on every run and on every machine and says
nothing about importance (invariant 15). `localeCompare` is deliberately not
used: it is locale dependent, and the Map's order must not change when the UI
language does.

The list is **not windowed**, deliberately, and `T-208` settled that trade in
the same direction for the outline (D-142): a row outside the DOM is a row no
screen reader and no in-page search can reach, which costs exactly the claim
these lists exist to make. Length is bounded instead — by the neighbourhood's
own `limit` and by `depth` here, by a stated page of 25 in the outline — and
the real graph's widest fan-out is eight. `VirtualList` exists and measures its
rows; it is the Reader's tool, not this one's, and a scaffold guard fails if it
appears here.

### The density policy is five clauses, each of them counted

`placeConstellation` walks the related list in its own order and answers, for
each entity: no mark on this Map (`not_loaded`), a mark outside the stage at
this camera position (`off_stage`), a mark on the stage with no room for a
card beside it in any of the four ways one can open (`no_room`), a card that
would cover one already placed in every direction that does fit (`crowded`),
or beyond the four-card budget (`budget`). The order is the order of the
questions: no room at all is not the same answer as a neighbour already
there, and crowding is checked *before* the budget, so the budget is spent on
cards a reader can actually read.

`no_room` is `T-209`'s, and it came from looking at the running UI rather than
from the gate: two cards hung 21 and 69 px out of the top of the stage with
the first line of their statements behind the search rail. The overlay is a
*sibling* of the renderer's container, so nothing clips a card that leaves the
stage — and a statement whose first line is hidden is the one cut D-131
forbids, since nothing on screen says it was cut.

The crowding clause used to be a 240 px grid cell, the same device Sigma's
`labelDensity` uses for labels, and `T-209` measured what that cost on the real
graph: it refused **7 of 8** neighbour cards that would have fitted *and*
placed two that overlapped by two thirds of a card, because a grid answers
"same cell?" when the question is "same pixels?" (D-145). It is now an overlap
test over the card's measured footprint — 320×296 for a neighbour, 416×176 for
the primary, which is what Chrome laid them out at, the height being the
*tallest* card seen across eighteen focuses rather than the first one measured
— and the rectangle it reserves is the card, its gap, **and the mark it points
at**, because two cards
opening in opposite directions from marks four pixels apart overlap nothing and
still point into the same four pixels. Four orientations are tried in a stated
order before a refusal, since a card prefers to open towards the middle of the
stage and two marks either side of the middle would otherwise grow into each
other.

The card budget is four and the *forced* label budget is also four now, and the
two remain deliberately separate numbers for different things: a label is a
line of text beside a mark, a card is a block with a statement, a relation and
a badge row. Twelve forced labels was the value `T-205` argued for, and the
walk showed why it was wrong — ForceAtlas2 pulls a node's neighbours towards
it, so a fan-out is the densest part of the picture and nine sentences landed
in a cluster 250 px across.

None of this works at all unless the camera goes to the selection, which it did
not until `T-209` (D-146): the camera framed the whole graph, a neighbourhood
was about a tenth of the stage wide, and every neighbour card was refused for
covering the focused one. `MapSession.frame` centres a new focus with its drawn
neighbours; `MAP_FOCUS_MARGIN` is calibrated over 23 real focuses, and its
table is in `mapSession.ts`.

Cards placed plus omissions counted equals the neighbours returned. That is
tested, on fixtures and on the real fan-out, and it is the whole answer to
"does a viewport budget become silent omission".

### The overlay owns nothing

No button, no link, no field, `pointer-events: none`, `aria-hidden` (D-137).
Every card on the stage is a second view of a row in the related list, so
hiding it from the accessibility tree costs nothing and avoids building a
second tree over the same entities; taking no pointer events means a click
reaches the *mark*, which is what keeps selection on one identity.

Two consequences worth knowing:

- The overlay is a **sibling** of the stage, never a child. `MapSession.kill()`
  calls `container.replaceChildren()` — it has to, because Sigma appends its own
  canvases there — so a React subtree inside the container would be removed
  from under React the first time a filter replaced the renderer.
- Cards are positioned in **physical** `left`/`top` pixels, which is the one
  place in this codebase that is deliberate rather than a lapse from D-012's
  logical properties: the coordinates come out of the renderer's viewport, and
  a logical inset would mirror a card away from its own mark in Persian.

### Cards move when the camera stops

Anchoring is per node, and the placement feeds the omission report, so
re-placing on every frame would re-render the related list and the search rail
sixty times a second for one pan. `hideLabelsOnMove: true` already answers this
question for labels; cards follow the same rule (D-138). `MAP_STAGE_SETTLE_MS`
is the trailing delay, and the first placement does not wait for it — the draw
effect marks the graph as placed as soon as the renderer holds it, because a
placement computed *before* `attach` would report every neighbour as "not
drawn", which is a true statement about the wrong situation.

### The canvas is a third caller, not a second identity

`MapSession` reports; it never decides. `onNode("clickNode")` reaches
`useMapFocus.focusEntity` — the same function the rail's buttons call —
`enterNode`/`leaveNode` reach the one `useMapPeek` binding, and `onRender` says
only that a frame was drawn. The handlers live in a mutable slot read by a
trampoline subscribed once per renderer, so what a click does can change on
every render without the renderer being rebuilt; rebuilding it would kill the
live one and the accumulated picture with it (D-126).

`enableEdgeEvents` is still `false`. `T-204` left it off "until something
selects an edge", and `T-207` is the task that would have: it does not, because
an edge has no address in `mapLink`'s grammar (D-119) and a pointer target with
nowhere to go is worse than none. The relation is named in words instead, in
`MapRelation.tsx` (D-135).

Depth is a view control rather than a fifth URL parameter (D-136), for the same
reason the search query is not in the grammar: it bounds one request and
changes nothing about which graph is drawn. The bound is the contract's own
1–3, and `parseDepth` **ignores** anything outside it rather than clamping —
the response echoes `depth` back, so a clamped value would report a bound the
reader never set.

### Quick Read shows the record, in a stated order

The complete stored statement, the recorded excerpt and locator, the active
relations, the derivation, provenance and source, and only then the identifiers.
The order is D-131's and is asserted *as an order*. Nothing is summarised,
nothing absent is filled in, and `readerPath` carries the locator's real
`start_sec` where one exists and none where it does not (D-069).

It is not `EntityCard`: the Reader's card renders the same record correctly for
the Reader, leading with the provenance badge row, and D-131 fixes a different
order here. Two components, one record, two stated orders — and the atoms are
shared.

## What the Map may say about itself (`T-208`)

Five states were already rendered on this route — a loading line, an empty
note, a partial extent, an `ApiFailure` panel and a renderer refusal — and each
was decided at its own render site. `mapState.ts` is those decisions as two
total functions, and what they exist for is the *pairs* a per-site condition
collapses into one true-sounding sentence:

- **Unasked is not empty.** A snapshot with no page applied has nothing to
  count, so nothing is counted for it: `counted: false`, and the counts panel
  does not appear. Printing zeros there is D-068's shape — an empty answer to a
  question nobody asked, presented as an answer.
- **Partial is not whole.** `complete` is `GraphSnapshot`'s conclusion over the
  cursor, the held edges and the API's own `truncated` (D-123). It is read, and
  never recomputed here.
- **Refused is not empty.** A failure outranks a count, and the pages that did
  arrive stay countable while the view says out loud that they are not an
  answer to the request that failed.
- **Undrawn is not absent.** The graph can be whole and undrawable at once.

`describeCanvas` answers the second question, which is a different question:
`unavailable` (the renderer module never loaded — no WebGL2, and nothing on
that canvas will ever work), `refused` (a renderer was reached and refused this
container, almost always its size, and the next layout usually fixes it),
`pending`, `nothing`, `drawing`. The two faults were one message until `T-208`
split them (D-140), and the single message had been telling readers of the
second case to go and find a different browser.

**`drawing` means a live renderer is holding this graph** — not "a factory
arrived and a page exists" (D-141). React runs a render and then its effects,
so the render that first sees a page precedes the effect that draws it; a
canvas described as drawing during that render is describing something that has
not happened. That is why the view keeps the snapshot the renderer holds in
*state* rather than in the ref beside it: a ref cannot say "there is a picture
now", because it changes without a render. The visible cost is that the zoom
and reset controls arrive one render after the counts, which is honest — there
is no camera until there is a renderer.

## The outline is the DOM half of the pair (`T-208`)

D-120 pairs the WebGL surface with a DOM one, and until `T-208` the DOM half
could only be reached through a *query*: the search rail lists what matches and
the related list lists a selection's neighbourhood, and both need something
typed or something selected first. `outline.ts` and `MapOutline` are the list
that needs neither (D-142).

The order is `forEachNode`'s, which is insertion order, which is the order the
pages arrived, which is the order the server returned. Sorting by how connected
a node is would be the invented importance invariant 15 forbids — and it would
reorder the list under the reader every time another page arrived. Each row
states its **drawn** relations, a count that grows as pages arrive and is
smaller than the neighbourhood's answer whenever a far endpoint has not loaded
(D-059); a relation the pipeline recorded onto the entity itself counts once,
because `degree` in a directed multigraph counts a loop twice.

## Motion the stylesheet cannot reach (`T-208`)

The stylesheet's `prefers-reduced-motion` block covers everything the browser
animates and nothing the Map animates: zoom, zoom out and reset are eased by
Sigma's camera, in JavaScript, on a canvas. `motion.ts` reads the same
preference and turns it into the camera's own argument, which is why
`MapCamera` grew an optional animation parameter rather than the Map growing a
second camera path.

It answers `undefined` when motion is welcome, deliberately: a duration of our
own would override whatever the renderer decides is right for its own gesture,
and would be a fifth Map number chosen by argument and measured by nobody. The
preference is read *at the gesture* rather than cached, because it can change
while the page is open.
