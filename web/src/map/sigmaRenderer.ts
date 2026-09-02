/**
 * The one place the application constructs Sigma (`T-204`, styled by `T-205`).
 *
 * Kept apart from `mapSession.ts` so the lifecycle can be tested in jsdom --
 * which has no WebGL -- against an injected fake, exactly as the `T-202` gate
 * kept `new Sigma` out of its session module. Importing this file is what
 * pulls the renderer into the bundle, and only the Map route does.
 *
 * This module states three kinds of thing, and each one is a decision recorded
 * somewhere else: the *settings*, the *primitives* the style table draws with,
 * and the *reducers* that do the drawing.
 *
 * ## Settings
 *
 * - `allowInvalidContainer: false`. The Map sizes its container in CSS, so a
 *   zero-sized container is a defect to see rather than a graph quietly drawn
 *   into nothing. `MapView` renders the refusal instead of crashing the route
 *   (D-129).
 * - `enableEdgeEvents: false`. Nothing yet responds to a pointer on an edge,
 *   and edge picking costs a hit-test pass per frame. `T-207` turns it on when
 *   there is something for it to select. Note that this does *not* affect edge
 *   styling: an edge's interaction state is derived from its own endpoints, so
 *   the active path lights up without any edge ever being hit-tested.
 * - The label settings come from `MAP_LABEL_SETTINGS`, which is D-122's policy.
 *   `renderLabels` is now `true`, which it was not in `T-204`: the blanket
 *   `false` was holding the door until a truncation and density policy existed,
 *   and `labelPolicy.ts` is that policy. It is spread in rather than restated
 *   so that the four numbers `T-209` re-measures live in one file.
 *
 * ## Primitives
 *
 * Sigma v4's default primitive set is one node shape (a circle), two edge paths
 * and no extremities, which is a palette with exactly one channel: colour. ADR
 * 0005 invariant 9 forbids provenance being a colour-only distinction, and
 * `T-202` recorded that a size difference alone is indistinguishable at real
 * node density -- so the shapes, the parallel-edge path and the extremities the
 * style table needs are declared here. Their *names* are the strings
 * `mapStyle.ts` returns (`MapNodeShape`, `MapEdgeExtremity`); Sigma silently
 * substitutes its first declared shape for a name it does not know, so the two
 * lists are kept in step by hand and by `mapStyle.test.ts`.
 *
 * Everything not named here keeps its default: node layers, the label and
 * backdrop programs, and the depth layers (`nodes`/`topNodes`,
 * `edges`/`topEdges`) the reducers lift a focused mark onto. Sigma resolves
 * each field of a primitives declaration separately, so omitting a field is
 * inheriting it rather than clearing it.
 *
 * ## Reducers
 *
 * D-124 is absolute: the graph carries `x`, `y` and the API's record and
 * nothing else, so every display attribute is computed at draw time from that
 * record. `mapStyle` is the one style table (§8.6), and the two reducers here
 * are its only production caller. Sigma applies a reducer *after* the
 * declarative styles, so the table's output is what is drawn.
 *
 * The style table is a mutable object rather than an argument because hovering
 * a node must not relay out the graph: the view writes the new selection or
 * hover into `mapStyle` and `MapSession.refresh()` redraws with the layout
 * untouched. `sigmaRendererFor` exists so a caller with its own `MapStyle` --
 * a test, or a second view -- can have one without reaching for Sigma itself.
 */

import Sigma from "sigma";
import {
  extremityArrow,
  extremityBar,
  extremityCircle,
  extremityDiamond,
  extremitySquare,
  pathCurved,
  pathLine,
  pathLoop,
  sdfCircle,
  sdfDiamond,
  sdfSquare,
  sdfTriangle,
} from "sigma/rendering";

import { MAP_LABEL_SETTINGS } from "./labelPolicy";
import type { MapGraph } from "./graphProjection";
import type { MapRenderer, MapRendererFactory } from "./mapSession";
import { MapStyle, mapStyle } from "./mapStyle";

/**
 * The shapes, paths and extremities `mapStyle.ts` draws with.
 *
 * Node shapes carry provenance, edge heads carry relation vocabulary and edge
 * tails carry edge provenance -- the three distinctions that must survive
 * greyscale. `curved` is here for parallel edges: this graph joins one pair of
 * entities with a canonical relation *and* a library-synthetic one often
 * enough that two straight lines between the same two points would be one
 * drawn line and one edge the Map counted but nobody can see.
 */
export const MAP_PRIMITIVES = {
  nodes: {
    shapes: [sdfCircle(), sdfDiamond(), sdfSquare(), sdfTriangle()],
  },
  edges: {
    paths: [pathLine(), pathLoop(), pathCurved()],
    extremities: [
      extremityArrow(),
      extremityDiamond(),
      extremityCircle(),
      extremityBar(),
      extremitySquare(),
    ],
    defaultHead: "none",
    defaultTail: "none",
  },
} as const;

/** A renderer factory over one style table. */
export function sigmaRendererFor(style: MapStyle): MapRendererFactory {
  return (graph: MapGraph, container: HTMLElement): MapRenderer =>
    new Sigma(graph, container, {
      primitives: MAP_PRIMITIVES,
      settings: {
        allowInvalidContainer: false,
        enableEdgeEvents: false,
        ...MAP_LABEL_SETTINGS,
      },
      nodeReducer: style.nodeReducer,
      edgeReducer: style.edgeReducer,
    });
}

/** The application's renderer, over the application's one style table. */
export const createSigmaRenderer: MapRendererFactory = sigmaRendererFor(mapStyle);
