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
 * - `enableEdgeEvents: false`. `T-207` looked at this and **kept it off**
 *   (D-135). The Map's selection is an entity's `global_id` and the URL
 *   grammar can address nothing else (D-119), so a click on an edge has
 *   nowhere to go; turning the events on would buy a hit-test pass per frame
 *   and a pointer target that cannot be selected. Note that this does *not*
 *   affect edge styling: an edge's interaction state is derived from its own
 *   endpoints, so the active path lights up without any edge ever being
 *   hit-tested, and `T-207`'s cards name the relation in words.
 * - The label settings come from `MAP_LABEL_SETTINGS`, which is D-122's policy.
 *   `renderLabels` is now `true`, which it was not in `T-204`: the blanket
 *   `false` was holding the door until a truncation and density policy existed,
 *   and `labelPolicy.ts` is that policy. It is spread in rather than restated
 *   so that the four numbers `T-209` measured live in one file.
 * - The size settings come from `MAP_SIZE_SETTINGS`, which is D-197's, and are
 *   spread in for the same reason. They are the answer to the largest thing
 *   `T-215`'s comparison found: with Sigma's defaults a mark's size is a
 *   distance in *graph units*, multiplied at draw time by the pixels-per-unit
 *   of the current framing, so the same 86-node graph drew marks several times
 *   larger on a 2852 px field than on a 1440 px one and the approved quiet
 *   overview was quiet only at the narrow end (`SPEC.md` §16).
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
 *
 * ## The adapter (`T-207`)
 *
 * The factory returns an *adapter* over the Sigma instance rather than the
 * instance itself, which is new. `MapRenderer` used to be a structural subset
 * Sigma happened to satisfy; `onNode`, `onRender` and `graphToViewport` are
 * where that stops being free -- Sigma's emitter is typed per event name, so
 * spelling the events here is what keeps `sigma`'s types inside the one module
 * that is allowed to name them (D-127) and keeps the injected fakes in the
 * tests down to four small functions.
 *
 * The adapter adds no behaviour and no state. It renames three calls and
 * unwraps one event payload, so that the Map's own boundary says `onNode` and
 * a `global_id` where Sigma says `clickNode` and `{ node }`.
 *
 * `T-209` added the last member for the same reason: `nodeDisplay` is
 * `getNodeDisplayData` narrowed to a point, because a camera is addressed in
 * the *framed* space rather than in graph units or pixels, and framing a
 * focus is therefore a question only the renderer can answer (D-146).
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
import type { MapNodeEvent, MapPoint, MapRenderer, MapRendererFactory } from "./mapSession";
import { MAP_SIZE_SETTINGS, MapStyle, mapStyle } from "./mapStyle";

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
  return (graph: MapGraph, container: HTMLElement): MapRenderer => {
    const sigma = new Sigma(graph, container, {
      primitives: MAP_PRIMITIVES,
      settings: {
        allowInvalidContainer: false,
        enableEdgeEvents: false,
        ...MAP_SIZE_SETTINGS,
        ...MAP_LABEL_SETTINGS,
      },
      nodeReducer: style.nodeReducer,
      edgeReducer: style.edgeReducer,
    });
    return {
      resize: (force?: boolean) => sigma.resize(force),
      refresh: () => sigma.refresh(),
      kill: () => sigma.kill(),
      getCamera: () => sigma.getCamera(),
      // The node key *is* the `global_id` (D-124), so no lookup is needed and
      // none is done: an adapter that resolved a record here would be a second
      // place the Map decides what a mark means.
      onNode: (event: MapNodeEvent, handler: (globalId: string) => void) => {
        sigma.on(event, ({ node }) => handler(node));
      },
      onRender: (handler: () => void) => {
        sigma.on("afterRender", handler);
      },
      graphToViewport: (point: MapPoint) => sigma.graphToViewport(point),
      // The camera's own coordinates (`T-209`): `getNodeDisplayData` answers
      // in the framed space `Camera.animate` is addressed in, which is why
      // framing a focus is asked of the renderer rather than computed from
      // the graph's `x`/`y`. `undefined` for a node it does not hold, which
      // becomes the `null` the boundary states.
      nodeDisplay: (globalId: string) => {
        const display = sigma.getNodeDisplayData(globalId);
        if (display === undefined) return null;
        return Number.isFinite(display.x) && Number.isFinite(display.y)
          ? { x: display.x, y: display.y }
          : null;
      },
    };
  };
}

/** The application's renderer, over the application's one style table. */
export const createSigmaRenderer: MapRendererFactory = sigmaRendererFor(mapStyle);
