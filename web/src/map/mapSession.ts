/**
 * The Map's renderer lifecycle: lay out, draw, refresh, resize, zoom, and kill
 * (`T-204`; `refresh` added by `T-205`, the event and coordinate adapters by
 * `T-207`).
 *
 * There is exactly one of these in the application (§8.6 forbids a second
 * Sigma wrapper), and it is deliberately framework-free. React decides *when*
 * a graph is drawn and when the renderer dies; this class owns *what* that
 * means, because the sequence is where the leak lives:
 *
 * - a second `attach` must kill the first renderer before creating another,
 * - `kill` must be idempotent, since an unmount can follow a replacement,
 * - and an operation arriving after the kill -- a `ResizeObserver` callback, a
 *   page that merged while the route was closing -- must do nothing rather
 *   than throw or resurrect a dead context.
 *
 * ADR 0005 invariant 10 is a leak invariant, and the `T-202` gate proved it is
 * observable: Sigma v4's `kill()` calls `WEBGL_lose_context.loseContext()`, so
 * a renderer that is not killed is a WebGL context the browser will eventually
 * answer by losing the *oldest* one -- a blank canvas somewhere unrelated.
 * With React 19's `StrictMode` double-invoking effects, an attach that did not
 * kill its predecessor would leak one context per mount on the first page load.
 *
 * D-182: **that exact scenario is asserted against the jsdom fake and nowhere
 * else.** The browser gate serves `npm run build` through `vite preview`, which
 * is production React, where `<StrictMode>` does not double-invoke — which is
 * why `{ created: 1, live: 1 }` holds there on first load without this class
 * doing anything. What the gate does prove in a real browser is the *other*
 * half: repeated attaches across filter changes and route trips leave one
 * renderer alive and release the contexts of the rest. The two halves together
 * are the invariant; neither harness can state both, and pretending the gate
 * covers the double-invoke would be a claim about coverage this project does
 * not have.
 *
 * The renderer is reached through `MapRenderer`/`MapRendererFactory` rather
 * than by constructing `Sigma` here, for the same reason the gate did it: jsdom
 * has no WebGL, so the *order* of these operations can only be asserted
 * against an injected fake, and the real renderer is walked in a real browser
 * where the question can actually be answered. The seam is a test boundary,
 * not an abstraction over two renderer APIs -- `sigmaRenderer.ts` is its only
 * production implementation.
 */

import forceAtlas2 from "graphology-layout-forceatlas2";

import type { MapGraph } from "./graphProjection";
import { cameraAnimation, type MapCameraAnimation } from "./motion";

// Re-exported because it is part of *this* boundary: `MapRenderer` and
// `MapCamera` are declared here, so a caller writing a renderer -- the real
// one, or the tests' fake -- should not have to know the preference it came
// from is read in `motion.ts`.
export type { MapCameraAnimation };

/**
 * The part of Sigma's camera the Map drives. Sigma's satisfies it structurally.
 *
 * Each gesture takes the animation argument `T-208` reads the reduced-motion
 * preference into (`motion.ts`). It is optional because `undefined` is a real
 * answer -- "use whatever duration the renderer thinks is right" -- and
 * because a camera that cannot animate at all still satisfies this interface.
 */
export interface MapCamera {
  zoomIn(animation?: MapCameraAnimation): unknown;
  zoomOut(animation?: MapCameraAnimation): unknown;
  reset(animation?: MapCameraAnimation): unknown;
  /**
   * Move to a stated camera position (`T-209`).
   *
   * The coordinates are the renderer's *framed* space -- the one
   * `nodeDisplay` answers in -- not graph units and not pixels, because a
   * camera's job is to say which part of the framed graph is on screen.
   */
  animate(target: MapCameraTarget, animation?: MapCameraAnimation): unknown;
}

/** What a camera can see right now, and the ratio it sees it at. */
export interface MapVisibleExtent {
  /** Framed units visible across the container's width. */
  width: number;
  /** Framed units visible down the container's height. */
  height: number;
  /** The camera ratio these two were measured at. */
  ratio: number;
}

/** Where a camera is asked to go: a centre, and how much to show around it. */
export interface MapCameraTarget {
  x: number;
  y: number;
  /** 1 shows the whole framed graph; smaller is closer in. */
  ratio: number;
}

/**
 * The node events the Map listens for (`T-207`).
 *
 * Three, and no edge event. An edge has no address in the Map's URL grammar --
 * `focus` is an entity's `global_id` (D-119) -- so a pointer on an edge would
 * have nowhere to go, and `enableEdgeEvents` stays off (D-135). Edge
 * *styling* needs no event at all: an edge's interaction state is derived from
 * its own endpoints in `mapStyle`.
 */
export type MapNodeEvent = "clickNode" | "enterNode" | "leaveNode";

/** A point in either coordinate system. Graph units going in, container pixels coming out. */
export interface MapPoint {
  x: number;
  y: number;
}

/** What a redraw may skip, because nothing it depends on has changed. */
export interface MapRefreshOptions {
  /**
   * The graph's structure and every node's position are unchanged, so the
   * renderer's spatial and edge-group indices do not have to be rebuilt --
   * only the reducers re-run and the picture repainted.
   */
  restyleOnly?: boolean;
}

/** The part of the renderer the Map uses, and nothing wider. */
export interface MapRenderer {
  resize(force?: boolean): unknown;
  refresh(options?: MapRefreshOptions): unknown;
  kill(): unknown;
  getCamera(): MapCamera;
  /**
   * Subscribe to a node event (`T-207`). Released by `kill()`, which is why
   * there is no unsubscribe: the renderer's life *is* the subscription's.
   */
  onNode(event: MapNodeEvent, handler: (globalId: string) => void): void;
  /** Subscribe to "the picture has just been drawn" -- pan, zoom, resize, refresh. */
  onRender(handler: () => void): void;
  /** Graph coordinates to pixels inside the container. */
  graphToViewport(point: MapPoint): MapPoint;
  /**
   * What the camera can currently see, in the framed space `nodeDisplay`
   * answers in, and the ratio it is seeing it at (`T-209`).
   *
   * `frame()` needs this because a camera ratio is **not** a framed distance:
   * the renderer scales the two axes by the container's own aspect and by a
   * correction ratio derived from the graph's bounding box, so the framed
   * extent one ratio shows is different along x and along y and different on
   * every stage. Reading one measured (extent, ratio) pair and scaling from it
   * needs none of those terms and cannot go stale when they change.
   *
   * `null` for a renderer that cannot say — which is any renderer with no
   * viewport yet, and the fake ones in the unit suites.
   */
  visibleExtent?(): MapVisibleExtent | null;
  /**
   * A node's position in the renderer's framed space, or `null` (`T-209`).
   *
   * The camera's own coordinate system, which is neither graph units nor
   * pixels: the framed space is what `MapCamera.animate` is addressed in, so
   * "put this node in the middle of the stage" is a question only the
   * renderer can answer. `null` for a node it does not hold.
   */
  nodeDisplay(globalId: string): MapPoint | null;
}

export type MapRendererFactory = (graph: MapGraph, container: HTMLElement) => MapRenderer;

/**
 * What the view wants to know when the canvas is used (`T-207`).
 *
 * Every one of these is a *report*, never a decision: the session says a node
 * was clicked, and the view calls the same `focusEntity` the search rail's
 * button calls. That is what keeps pointer, keyboard and URL on one selection
 * identity (ADR 0005 invariant 8, §8.6) -- a handler here that navigated
 * would be the second one.
 *
 * Held in a mutable slot rather than captured at construction, because these
 * close over React state and change identity on nearly every render, while the
 * renderer's own subscription must be made once when it is created. `attach`
 * subscribes a trampoline that reads the current slot.
 */
export interface MapSessionHandlers {
  /** A node was clicked. The argument is its `global_id`, which is its node key. */
  onSelectNode?: (globalId: string) => void;
  /** The pointer entered a node. */
  onEnterNode?: (globalId: string) => void;
  /** The pointer left a node. */
  onLeaveNode?: (globalId: string) => void;
  /** The picture was drawn, so anything anchored to a node has moved. */
  onRender?: () => void;
}

/**
 * ForceAtlas2 iterations per pass, for a graph small enough to afford them.
 *
 * The number the `T-202` gate measured on the real 86-node/118-edge graph:
 * 2.7-3.4 ms steady and 8.5-9.0 ms cold, against a 16.7 ms frame. That
 * measurement is why the layout is synchronous and there is no worker (D-121),
 * so changing the iteration count here invalidates the measurement the
 * decision rests on.
 *
 * It is a *ceiling* rather than the count, because 86 nodes is not the bound.
 * "Load more" is unbounded and the page limit is 500, so the accumulated graph
 * grows without any limit while this runs on the main thread inside a React
 * effect — where `useGraphWalk`'s own `cancel()` cannot reach it. See
 * :data:`MAP_LAYOUT_NODE_ITERATIONS`.
 */
export const MAP_LAYOUT_ITERATIONS = 200;

/**
 * Where Barnes-Hut approximation starts paying for itself, measured.
 *
 * `forceAtlas2.inferSettings` turns it on above **2,000** nodes, and below
 * that every iteration is all-pairs repulsion: O(n²) on the main thread.
 * Measured here at 200 iterations over a graph with the real one's edge ratio
 * (1.37 edges per node), plain against Barnes-Hut:
 *
 * | nodes | all-pairs | Barnes-Hut |
 * |---|---|---|
 * | 86 | 7.6 ms | 23.7 ms |
 * | 250 | 30.9 ms | 53.0 ms |
 * | 500 | 113 ms | 133 ms |
 * | **1,000** | **387 ms** | **345 ms** |
 * | 2,000 | 1,434 ms | 835 ms |
 * | 4,000 | 5,880 ms | 1,893 ms |
 *
 * So the crossover is near 1,000, not 2,000: at the library's threshold the
 * approximation would already have saved 600 ms. Below the crossover the tree
 * costs more than it saves *and* approximates, which is why this is a
 * threshold rather than always-on.
 */
export const MAP_LAYOUT_BARNES_HUT_ORDER = 1000;

/**
 * The work one layout pass is allowed: node-iterations, not iterations.
 *
 * 200 iterations at 500 nodes — the largest graph one page can deliver — is
 * the unit, and above that the iteration count comes down so the pass stays
 * roughly flat instead of growing with the accumulated graph. Measured, with
 * Barnes-Hut where the threshold above enables it:
 *
 * | nodes | iterations | pass |
 * |---|---|---|
 * | ≤ 500 | 200 | 8–121 ms |
 * | 1,000 | 100 | ~172 ms |
 * | 2,000 | 50 | ~271 ms |
 * | 4,000 | 25 | ~240 ms |
 * | 8,000 | 20 (the floor) | ~448 ms |
 *
 * A rougher layout of a very large graph, rather than a settled layout nobody
 * can interact with while it settles. The floor is what keeps it a layout at
 * all, and it is also the honest limit of this design: past it the pass grows
 * again, and what a graph that size needs is the worker D-121 decided against
 * on an 86-node measurement. `MapLayoutMeasurement` reports the real numbers
 * on every pass, so that decision can be revisited from data rather than
 * from this comment.
 */
export const MAP_LAYOUT_NODE_ITERATIONS = MAP_LAYOUT_ITERATIONS * 500;

/** The fewest iterations a pass will run, however large the graph. */
export const MAP_LAYOUT_MIN_ITERATIONS = 20;

/**
 * How many iterations a graph of *order* nodes gets, and *ceiling* is the most.
 *
 * Pure, and exported, so the schedule can be asserted over a range of orders
 * without laying out a 40,000-node graph to read one number off it.
 */
export function mapLayoutIterations(
  order: number,
  ceiling: number = MAP_LAYOUT_ITERATIONS,
): number {
  if (order <= 0) return 0;
  const budgeted = Math.round(MAP_LAYOUT_NODE_ITERATIONS / order);
  return Math.max(MAP_LAYOUT_MIN_ITERATIONS, Math.min(ceiling, budgeted));
}

/**
 * How much room a framed focus leaves around itself, as a multiplier on the
 * extent it has to show (`T-209`, D-146).
 *
 * It now means exactly that. `frame()` measures the framed extent the camera
 * can currently see and scales the ratio to fit the neighbourhood on the worse
 * axis, so this multiplies a *fit*: 1.2 shows the neighbourhood with a fifth
 * of it again as clearance. It used to multiply `max(spanX, spanY)` as though
 * a camera ratio were a framed distance, and Sigma's aspect and correction
 * terms — ≈1.69 for a wide graph in a landscape stage — were whatever this
 * number happened to absorb on the one graph and the one viewport it was
 * calibrated at.
 *
 * **What the calibration table said, and why it is not reproduced here.** The
 * original was a walk of 23 focuses of the real graph at five candidate values,
 * scored on "neighbour cards placed / crowded out / marks off the stage", and
 * it read 1.2 as the tightest framing at which no neighbour's mark fell outside
 * `MAP_STAGE_CARD_INSET`. Two of its three columns have since stopped being
 * measurable: `T-213` replaced the pinned overlay with the Directional Orbit,
 * whose cards are laid out from the field, the neighbourhood and the chrome and
 * read **no camera at all** — so "cards placed at margin *m*" and "crowded out
 * at margin *m*" are no longer functions of this constant. The one live column
 * is marks off the stage, and that is now the whole justification: a gesture
 * whose purpose is to show a neighbourhood must not push part of it off the
 * field.
 *
 * Zero off-stage marks is also what the ratio arithmetic above now *computes*
 * rather than what this number was tuned to reach, which is why the value is
 * unchanged and the reasoning is not. Re-measuring it belongs to the browser
 * gate, over the geometry clauses that already assert the invariant.
 *
 * A focus with a single neighbour still gets no second card at any value: two
 * 320 px cards need more clearance than a pair 175 px apart can give, and that
 * omission is counted and the neighbour is in the related list (R20).
 */
export const MAP_FOCUS_MARGIN = 1.2;

/**
 * The closest a framing gesture will ever go, as a camera ratio.
 *
 * A focus with one neighbour beside it -- or none at all -- has an extent at
 * or near zero, and a ratio computed from it alone would zoom until one mark
 * filled the stage and the rest of the graph was a rumour. This is the floor,
 * and it is what an isolated node is framed at.
 */
export const MAP_FOCUS_MIN_RATIO = 0.12;

export interface MapLayoutMeasurement {
  nodes: number;
  edges: number;
  iterations: number;
  milliseconds: number;
}

export interface MapSessionOptions {
  container: HTMLElement;
  createRenderer: MapRendererFactory;
  /** Overridden only to re-measure D-121; defaults to what the gate measured. */
  iterations?: number;
  /** Injected for tests; `performance.now` in the browser. */
  now?: () => number;
  /** What to report to (`T-207`). Replaceable through `setHandlers`. */
  handlers?: MapSessionHandlers;
}

/**
 * One renderer over one graph.
 *
 * Not a graph store: it never inserts, removes or restyles anything. The graph
 * it is handed is `GraphSnapshot`'s, and the only attributes this class writes
 * are the `x`/`y` that ForceAtlas2 refines -- the two the projection seeds at
 * insertion and the layout exists to improve (D-124).
 */
export class MapSession {
  private readonly options: MapSessionOptions;
  private readonly iterations: number;
  private readonly now: () => number;

  private renderer: MapRenderer | null = null;
  private graph: MapGraph | null = null;
  private handlers: MapSessionHandlers;

  /** Every create and every kill, counted, so a leak shows up as a mismatch. */
  private created = 0;
  private killed = 0;

  constructor(options: MapSessionOptions) {
    this.options = options;
    this.iterations = options.iterations ?? MAP_LAYOUT_ITERATIONS;
    this.now = options.now ?? (() => performance.now());
    this.handlers = options.handlers ?? {};
  }

  /**
   * Replace what the canvas reports to (`T-207`).
   *
   * Called on render rather than at construction: the handlers close over the
   * view's current state, and re-creating the session to change them would
   * kill a live renderer -- and with it the accumulated picture -- every time
   * a callback's identity changed.
   */
  setHandlers(next: MapSessionHandlers): void {
    this.handlers = next;
  }

  get live(): boolean {
    return this.renderer !== null;
  }

  get creates(): number {
    return this.created;
  }

  get kills(): number {
    return this.killed;
  }

  /**
   * Lay the graph out and hand it to a renderer, replacing any live one.
   *
   * Seed *then* lay out, in that order and never the reverse: the projection
   * has already positioned every node from its own `global_id`, and
   * `graphology-layout-forceatlas2` reads `attr.x` straight into a
   * `Float32Array`, so a node that reached this point unpositioned would
   * become `NaN`, raise nothing, and simply not be drawn (ADR 0005, finding 3).
   *
   * The layout is a pure function of those seeds, which is what makes a reload
   * reproduce the picture the user last saw rather than a new arrangement of
   * the same graph.
   */
  attach(graph: MapGraph): MapLayoutMeasurement {
    if (this.renderer !== null) this.kill();
    const layout = this.relax(graph);
    this.graph = graph;
    let renderer: MapRenderer;
    try {
      renderer = this.options.createRenderer(graph, this.options.container);
    } catch (cause) {
      // A renderer that *refused* still built something first (`T-209`).
      //
      // Sigma appends its canvases to the container and takes their WebGL
      // context in its constructor, and only then validates the container --
      // so a container with a zero dimension throws *after* a live context
      // exists, and this class never receives the object whose `kill()` would
      // release it. Measured in Chrome on the real route: seven refused
      // attaches left seven contexts alive and seven canvases in the stage,
      // with no `webglcontextlost` for any of them. Browsers cap live
      // contexts at around sixteen and answer an excess by losing the
      // *oldest*, so the symptom is a different Map going blank later --
      // which is precisely what ADR 0005 invariant 10 exists to prevent, and
      // what the jsdom suites could not see, because a fake factory throws
      // without having created anything.
      this.releaseContainer();
      this.graph = null;
      throw cause;
    }
    // Subscribed once, here, and released with the renderer by `kill()`. Each
    // one reads the *current* handler slot, so a re-render can change what a
    // click does without touching the renderer that reports it.
    renderer.onNode("clickNode", (id) => this.handlers.onSelectNode?.(id));
    renderer.onNode("enterNode", (id) => this.handlers.onEnterNode?.(id));
    renderer.onNode("leaveNode", (id) => this.handlers.onLeaveNode?.(id));
    renderer.onRender(() => this.handlers.onRender?.());
    this.renderer = renderer;
    this.created += 1;
    return layout;
  }

  /**
   * Where a node's mark is on screen, in pixels inside the container, or
   * `null` (`T-207`).
   *
   * The coordinate half of D-132: a card is anchored to its node by asking the
   * renderer where that node currently is, so a pan or a zoom moves the card
   * with the mark rather than leaving it behind. `null` is returned rather than
   * a guess in every case where there is no answer -- no live renderer, a node
   * the graph does not hold, or coordinates that are not finite -- because a
   * card placed at an invented position would claim to point at a mark that is
   * somewhere else entirely.
   */
  nodePosition(globalId: string): MapPoint | null {
    const renderer = this.renderer;
    const graph = this.graph;
    if (renderer === null || graph === null || !graph.hasNode(globalId)) return null;
    const { x, y } = graph.getNodeAttributes(globalId);
    if (!Number.isFinite(x) || !Number.isFinite(y)) return null;
    const point = renderer.graphToViewport({ x, y });
    if (!Number.isFinite(point.x) || !Number.isFinite(point.y)) return null;
    return point;
  }

  /**
   * Bring a focus and its drawn neighbours onto the stage (`T-209`, D-146).
   *
   * This exists because the walk found the two halves of the Map's selection
   * arriving at the camera as nothing at all. The camera framed the whole
   * 86-node graph; a focus therefore sat wherever the layout had put it, its
   * neighbourhood spanned about a tenth of the stage, and every neighbour
   * card was refused for covering the focused one. Worse, `zoomIn` zooms
   * about the *centre of the stage* rather than about the selection, so a
   * reader who selected a node and zoomed in pushed it off the stage
   * entirely -- after two presses the focus itself was gone, with the route
   * still saying, correctly, that the graph was drawn. Selection knew where
   * it was and the camera was never told.
   *
   * What it frames is the focus **and its neighbours in the drawn graph**,
   * because those are the marks that can carry a card and the ones an active
   * path runs to. It is not the bounded neighbourhood (`T-207`): that answer
   * arrives later, may name entities these pages never loaded, and would make
   * the camera move a second time after the reader had started reading.
   *
   * Returns whether it moved, so a caller can tell "framed" from "there was
   * nothing to frame" -- a node the renderer does not hold has no position,
   * and inventing one would point the camera at empty space.
   */
  frame(centreId: string, neighbours: Iterable<string> = []): boolean {
    const renderer = this.renderer;
    if (renderer === null) return false;
    const centre = renderer.nodeDisplay(centreId);
    if (centre === null) return false;

    let minX = centre.x;
    let maxX = centre.x;
    let minY = centre.y;
    let maxY = centre.y;
    for (const neighbour of neighbours) {
      const point = renderer.nodeDisplay(neighbour);
      if (point === null) continue;
      minX = Math.min(minX, point.x);
      maxX = Math.max(maxX, point.x);
      minY = Math.min(minY, point.y);
      maxY = Math.max(maxY, point.y);
    }
    /*
     * The ratio that actually *fits* the neighbourhood, on both axes.
     *
     * This used to be `max(spanX, spanY) * MAP_FOCUS_MARGIN`, which treats a
     * camera ratio as a framed distance. It is not one: the renderer scales
     * the two axes by the container's aspect and by a correction ratio derived
     * from the graph's bounding box, so the framed extent one ratio shows
     * differs along x and along y and differs on every stage. On a wide graph
     * in a landscape stage the correction is ≈1.69, and the topmost and
     * bottommost neighbours landed off-stage: the failure the margin exists to
     * eliminate.
     *
     * Measured rather than derived. One (visible extent, ratio) pair from the
     * renderer is enough, because the visible extent is linear in the ratio —
     * so the ratio needed to show a span is the current one scaled by how many
     * times that span exceeds what is visible now, taken over the worse axis.
     * No aspect term, no correction ratio, and nothing to go stale when either
     * changes. A renderer that cannot answer keeps the old estimate, which is
     * what the fake renderers in the unit suites do.
     */
    const spanX = maxX - minX;
    const spanY = maxY - minY;
    const view = renderer.visibleExtent?.() ?? null;
    const needed =
      view !== null && view.width > 0 && view.height > 0 && view.ratio > 0
        ? view.ratio * Math.max(spanX / view.width, spanY / view.height)
        : Math.max(spanX, spanY);
    const ratio = Math.max(needed * MAP_FOCUS_MARGIN, MAP_FOCUS_MIN_RATIO);
    // The middle of what has to be visible, not the focus itself: a focus at
    // the edge of its own neighbourhood would otherwise leave half of it off
    // the stage, which is the state this method exists to end.
    renderer
      .getCamera()
      .animate({ x: (minX + maxX) / 2, y: (minY + maxY) / 2, ratio }, cameraAnimation());
    return true;
  }

  /**
   * Re-settle the layout after a page merged into the graph already on screen.
   *
   * A continuation page arrives as nodes sitting on their identity seeds, which
   * say nothing about the structure the layout has already found -- drawn
   * as-is, a second page is a scatter of dots over a settled graph. So the
   * whole graph is relaxed again and the picture moves. That is the honest
   * trade: the alternative is pinning the placed nodes, and the only way to
   * pin one is a third node attribute, which D-124 does not allow the graph to
   * carry.
   *
   * A no-op with no live renderer: a page can settle after the route closed.
   */
  update(): MapLayoutMeasurement | null {
    if (this.renderer === null || this.graph === null) return null;
    const layout = this.relax(this.graph);
    this.renderer.refresh();
    return layout;
  }

  /**
   * Redraw the graph exactly as it is laid out (`T-205`).
   *
   * The distinction from `update()` is the whole reason this method exists,
   * and it is D-128's other half: `update()` re-settles the layout because a
   * *page* arrived and the structure changed, so the picture is allowed to
   * move. A change of hover or selection changes no structure at all -- only
   * what the style table computes from it -- so relaxing the layout there
   * would make the graph jump under the pointer on every mouse move.
   *
   * Sigma re-runs the reducers on `refresh()`, which is how a mutable style
   * table becomes a new drawing without a new renderer and without a second
   * lifecycle to kill.
   *
   * `restyleOnly`, because this path changes no structure and moves no node.
   * A bare `refresh()` is a *full* one: Sigma clears both indices, re-adds
   * every node and every edge, and rebuilds its edge groups before running the
   * reducers. This method is called on every `enterNode` and every
   * `leaveNode`, so sweeping the pointer across 86 marks cost two full
   * re-indexations per mark crossed, and at a few thousand nodes that is a
   * visible stall per pointer move. What actually changes is `size`, `color`,
   * `label` and opacity -- and `size` is not one of Sigma's own
   * layout-impacting fields either (`x`, `y`, `zIndex`, `type`), which is the
   * same judgement its internal graph handlers make.
   *
   * A no-op with no live renderer, like every other operation here.
   */
  refresh(): void {
    this.renderer?.refresh({ restyleOnly: true });
  }

  /**
   * Pick up the container's current size.
   *
   * `force`, because the case that matters is the one Sigma cannot infer: the
   * container shrank, and a renderer holding the old dimensions draws the
   * graph outside its own box.
   */
  resize(): void {
    this.renderer?.resize(true);
  }

  /*
   * The three camera gestures, and the one thing they all pass on.
   *
   * `cameraAnimation()` is read at the gesture rather than held, because the
   * reduced-motion preference can change while the page is open and because
   * nothing here should own a copy of it (`T-208`). A reader who asked for
   * less motion gets the new view immediately; everyone else gets the
   * renderer's own easing, since the argument is then `undefined`.
   */
  zoomIn(): void {
    this.renderer?.getCamera().zoomIn(cameraAnimation());
  }

  zoomOut(): void {
    this.renderer?.getCamera().zoomOut(cameraAnimation());
  }

  /** Back to the framed whole graph, which is where a reload starts. */
  resetView(): void {
    this.renderer?.getCamera().reset(cameraAnimation());
  }

  /**
   * Kill the renderer and release the graph. Idempotent.
   *
   * `creates` and `kills` must finish equal after any sequence of operations.
   * A double kill would be as much of a defect as a missed one, which is why
   * the counters are read by the tests rather than only the state.
   */
  kill(): void {
    const renderer = this.renderer;
    this.renderer = null;
    this.graph = null;
    if (renderer === null) return;
    renderer.kill();
    this.killed += 1;
    // Sigma appends its own canvases to the container; a killed renderer's
    // leftovers would otherwise sit under the next one's.
    this.options.container.replaceChildren();
  }

  /**
   * Empty the container, releasing any WebGL context left in it (`T-209`).
   *
   * Only reached when a renderer refused this container, which is the one
   * path where a context exists and nothing this class holds can kill it.
   * Removing the canvas would leave the context to the garbage collector --
   * with no `webglcontextlost` and no promise about when -- so the context is
   * lost explicitly, which is what Sigma's own `kill()` does and what makes
   * the release observable rather than hoped for.
   *
   * Every step is defensive on purpose: this runs while another failure is
   * already being reported, and throwing here would replace a stated renderer
   * refusal (D-140) with an exception that takes the route down.
   */
  private releaseContainer(): void {
    const container = this.options.container;
    for (const canvas of Array.from(container.querySelectorAll("canvas"))) {
      try {
        const context =
          canvas.getContext("webgl2") ?? canvas.getContext("webgl");
        // `getContext` returns the context the canvas already holds, so this
        // asks for the live one rather than creating a second.
        const lose = (
          context as { getExtension?: (name: string) => unknown } | null
        )?.getExtension?.("WEBGL_lose_context") as { loseContext?: () => void } | null;
        lose?.loseContext?.();
      } catch {
        // A canvas that cannot answer has no context to release.
      }
    }
    container.replaceChildren();
  }

  /**
   * The synchronous ForceAtlas2 pass, measured.
   *
   * `inferSettings` is the library's own advice for a graph of this order; the
   * Map does not hand-tune it, because a tuned constant measured once would
   * describe the tuning rather than the layout.
   */
  private relax(graph: MapGraph): MapLayoutMeasurement {
    const started = this.now();
    // An empty graph has nothing to relax, and `inferSettings` divides by its
    // order. An honest empty Map is a state the Map has to render (D-123's
    // `total: null` is *unknown*, never zero), so it must not be a crash.
    const iterations = mapLayoutIterations(graph.order, this.iterations);
    if (iterations > 0) {
      forceAtlas2.assign(graph, {
        iterations,
        settings: {
          ...forceAtlas2.inferSettings(graph),
          // Not the library's own threshold. `inferSettings` turns this on
          // above 2,000 nodes, and the measurement in
          // `MAP_LAYOUT_BARNES_HUT_ORDER` puts the crossover near 1,000 —
          // below which the tree costs more than it saves, and above which
          // all-pairs repulsion is what the main thread pays for.
          barnesHutOptimize: graph.order >= MAP_LAYOUT_BARNES_HUT_ORDER,
        },
      });
    }
    return {
      nodes: graph.order,
      edges: graph.size,
      iterations,
      milliseconds: this.now() - started,
    };
  }

}
