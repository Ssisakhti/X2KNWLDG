# `web/src/map/` — the Knowledge Map

Phase 2. Two things live here so far, both from `T-202`
([ADR 0005](../../../docs/adr/0005-knowledge-map-client.md)):

| Path | Holds |
|---|---|
| `seedPositions.ts` | Deterministic, non-zero starting positions, hashed from a node's `global_id` |
| `gate/` | The `T-202` compatibility harness: a single-page graph builder and the renderer lifecycle it exercises |

`#/map`, the graph store that accumulates pages, the style matrix and the
inspector are `T-203`–`T-208`. Nothing here is routed.

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

## The gate is a harness, not the Map

`gate/` answers one question — does the pinned renderer draw and release the
real graph on this machine — and it is deliberately quarantined:

- `web/gate.html` is served only by `npm run dev`. Vite's build input is
  `index.html` alone, so the harness is not in `dist/`.
- No application module imports it, and it defines no route.
  `tests/test_ui_scaffold.py` fails if either changes.
- `gate/gateGraph.ts` converts **one** `/api/graph` page. It is not the `T-203`
  projection and must not grow into it: page accumulation, conflict refusal and
  holding an edge until both endpoints arrive all belong there.

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
