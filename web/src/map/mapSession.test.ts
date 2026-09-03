/**
 * The renderer lifecycle, asserted in jsdom -- which has no WebGL, so the
 * renderer here is a fake and the real one is walked in a browser (`T-202`
 * did that walk; `T-209` repeats it for the Map).
 *
 * What these tests are for: ADR 0005 invariant 10 says the renderer is killed
 * on unmount *and on replacement*, and a missed kill is a WebGL context the
 * browser answers by losing the oldest one -- a blank canvas somewhere
 * unrelated, long after the mistake. That is a *sequence* bug, and a fake is
 * the only place the sequence can be checked at all: `creates` and `kills`
 * must finish equal after any order of operations, and nothing may reach a
 * renderer that has already been killed.
 */

import { beforeEach, describe, expect, it } from "vitest";

import { concept, edge, expressesConcept, page, payload, unit } from "../test/graphRecords";
import type { EntityRef, IndexedRelation } from "../api/contract";
import type { MapGraph } from "./graphProjection";
import { GraphSnapshot } from "./graphSnapshot";
import {
  MAP_FOCUS_MARGIN,
  MAP_FOCUS_MIN_RATIO,
  MAP_LAYOUT_ITERATIONS,
  MAP_LAYOUT_MIN_ITERATIONS,
  mapLayoutIterations,
  MapSession,
  type MapCamera,
  type MapCameraTarget,
  type MapNodeEvent,
  type MapPoint,
  type MapRenderer,
  type MapSessionHandlers,
} from "./mapSession";
import { seedPosition } from "./seedPositions";

/** A renderer that records what the session asked of it, in order. */
type FakeRenderer = MapRenderer & {
  calls: string[];
  /** The handlers the session subscribed, by event, so a test can fire them. */
  listeners: Map<string, (globalId: string) => void>;
  /** Every framing target the camera was given, in order (`T-209`). */
  framings: MapCameraTarget[];
  /** Where each node is in the framed space this fake reports (`T-209`). */
  display: Map<string, MapPoint>;
};

function fakeRenderer(): FakeRenderer {
  const calls: string[] = [];
  const listeners = new Map<string, (globalId: string) => void>();
  const framings: MapCameraTarget[] = [];
  const display = new Map<string, MapPoint>();
  const camera: MapCamera = {
    zoomIn: () => calls.push("camera:zoomIn"),
    zoomOut: () => calls.push("camera:zoomOut"),
    reset: () => calls.push("camera:reset"),
    animate: (target: MapCameraTarget, animation?: { duration: number }) => {
      // The animation argument is in the call, because "arrives immediately"
      // is the assertion a reduced-motion preference has to survive.
      calls.push(`camera:animate:${animation === undefined ? "default" : animation.duration}`);
      framings.push(target);
    },
  };
  return {
    calls,
    framings,
    display,
    nodeDisplay: (globalId: string) => display.get(globalId) ?? null,
    resize: (force?: boolean) => calls.push(`resize:${String(force)}`),
    refresh: (options?: { restyleOnly?: boolean }) =>
      calls.push(options?.restyleOnly === true ? "refresh:restyle" : "refresh"),
    kill: () => calls.push("kill"),
    getCamera: () => camera,
    // `T-207`'s adapters. The node handlers are recorded *and kept*, so a test
    // can fire one and prove the session reports it to its current handler
    // rather than to the one that was installed when the renderer was created.
    onNode: (event: MapNodeEvent, handler: (globalId: string) => void) => {
      calls.push(`onNode:${event}`);
      listeners.set(event, handler);
    },
    onRender: (handler: () => void) => {
      calls.push("onRender");
      listeners.set("render", handler);
    },
    // A camera that is not there cannot convert anything, so the fake stands
    // in for one that is: graph units are echoed back with a fixed offset, and
    // the offset is what makes a test able to tell the two spaces apart.
    graphToViewport: (point: MapPoint) => ({ x: point.x + 100, y: point.y + 200 }),
    listeners,
  };
}

/** A graph built the only way the Map is allowed to build one: the snapshot. */
function graphOf(nodes: EntityRef[], edges: IndexedRelation[] = []): MapGraph {
  const snapshot = new GraphSnapshot({});
  snapshot.applyPage(payload({ nodes, edges }), page());
  return snapshot.graph;
}

function sample(): MapGraph {
  return graphOf(
    [unit("KU-000001"), unit("KU-000002"), concept("C-000001")],
    [
      edge("youtube:pqlWNihgdjI:KU-000001", "youtube:pqlWNihgdjI:KU-000002"),
      expressesConcept("youtube:pqlWNihgdjI:KU-000001", "library:concepts:C-000001"),
    ],
  );
}

describe("MapSession", () => {
  let container: HTMLElement;

  beforeEach(() => {
    container = document.createElement("div");
    document.body.append(container);
  });

  function session(create: () => MapRenderer): MapSession {
    return new MapSession({ container, createRenderer: () => create() });
  }

  it("lays the graph out before the renderer is given it", () => {
    // The order is load-bearing in one direction only: a renderer created
    // first would draw the seeds and then be refreshed, but a *layout* run on
    // an unseeded node writes NaN into a Float32Array and raises nothing, so
    // the positions handed over are checked for being finite rather than for
    // merely existing (ADR 0005, finding 3).
    let handed: MapGraph | null = null;
    let positionedWhenHanded: boolean | null = null;
    const live = new MapSession({
      container,
      createRenderer: (graph) => {
        handed = graph;
        positionedWhenHanded = graph
          .nodes()
          .every((node) => Number.isFinite(graph.getNodeAttribute(node, "x")));
        return fakeRenderer();
      },
    });

    const graph = sample();
    const seeds = new Map(graph.nodes().map((node) => [node, { ...seedPosition(node) }]));
    const layout = live.attach(graph);

    expect(handed).toBe(graph);
    expect(positionedWhenHanded).toBe(true);
    expect(layout.nodes).toBe(3);
    expect(layout.edges).toBe(2);
    expect(layout.iterations).toBe(MAP_LAYOUT_ITERATIONS);

    let moved = 0;
    graph.forEachNode((node, attributes) => {
      expect(Number.isFinite(attributes.x)).toBe(true);
      expect(Number.isFinite(attributes.y)).toBe(true);
      const seed = seeds.get(node);
      if (seed !== undefined && (seed.x !== attributes.x || seed.y !== attributes.y)) moved += 1;
    });
    expect(moved).toBeGreaterThan(0);
  });

  it("writes nothing onto a node but its position", () => {
    // D-124: attributes are the API's record plus `x`/`y`. A session that
    // stored a size or a colour would put presentation inside the data the
    // inspector reads back, and would break the field-by-field comparison
    // D-125's refusal depends on.
    const graph = sample();
    session(fakeRenderer).attach(graph);
    graph.forEachNode((_node, attributes) => {
      expect(Object.keys(attributes).sort()).toEqual(["record", "x", "y"]);
    });
    graph.forEachEdge((_id, attributes) => {
      expect(Object.keys(attributes)).toEqual(["record"]);
    });
  });

  it("is deterministic: the same records lay out the same way twice", () => {
    // Why a reload reproduces the picture the user last saw. The seeds are
    // hashed from each `global_id` and the layout is a pure function of them,
    // so nothing here depends on arrival order or on a clock.
    const first = sample();
    const second = sample();
    session(fakeRenderer).attach(first);
    session(fakeRenderer).attach(second);
    const positions = (graph: MapGraph) =>
      graph
        .nodes()
        .sort()
        .map((node) => [node, graph.getNodeAttribute(node, "x"), graph.getNodeAttribute(node, "y")]);
    expect(positions(second)).toEqual(positions(first));
  });

  it("kills the live renderer before creating its replacement", () => {
    const renderers: FakeRenderer[] = [];
    const live = session(() => {
      const renderer = fakeRenderer();
      renderers.push(renderer);
      return renderer;
    });

    live.attach(sample());
    live.attach(sample());

    expect(live.creates).toBe(2);
    expect(live.kills).toBe(1);
    expect(live.live).toBe(true);
    expect(renderers[0]?.calls).toContain("kill");
    expect(renderers[1]?.calls).not.toContain("kill");
  });

  it("leaves the container empty when a renderer is killed", () => {
    // Sigma appends its own canvases; a killed renderer's leftovers would
    // otherwise sit under the next one's.
    const live = session(() => {
      container.append(document.createElement("canvas"));
      return fakeRenderer();
    });
    live.attach(sample());
    expect(container.childElementCount).toBe(1);
    live.kill();
    expect(container.childElementCount).toBe(0);
  });

  it("releases the context a refused renderer left behind, and empties the stage", () => {
    /*
     * `T-209`'s finding, and it is a leak invariant 10 was already about.
     *
     * Sigma appends its canvases and takes their WebGL context in its
     * constructor, and validates the container *after* that -- so a container
     * with a zero dimension throws with a live context already attached, and
     * this session never receives the object whose `kill()` would release it.
     * Measured in Chrome on the real route before the fix: seven refused
     * attaches, seven contexts created, none lost, seven canvases piling up
     * in the stage. Browsers answer too many live contexts by losing the
     * oldest, so the symptom appears somewhere else entirely.
     *
     * The fake reproduces the *order* -- attach a canvas, then throw -- which
     * is the whole shape of the bug.
     */
    let lost = 0;
    const canvasWithContext = () => {
      const canvas = document.createElement("canvas");
      // jsdom has no WebGL, so the context is a stub that answers the one
      // question this path asks it.
      canvas.getContext = ((kind: string) =>
        kind === "webgl2"
          ? { getExtension: (name: string) => (name === "WEBGL_lose_context" ? { loseContext: () => { lost += 1; } } : null) }
          : null) as HTMLCanvasElement["getContext"];
      return canvas;
    };
    const live = session(() => {
      container.append(canvasWithContext());
      throw new Error("Container has no height.");
    });

    for (let round = 0; round < 3; round += 1) {
      expect(() => live.attach(sample())).toThrow(/no height/);
    }

    expect(container.childElementCount).toBe(0);
    expect(lost).toBe(3);
    // A refusal is not a create: nothing was handed over, so there is nothing
    // to kill and the counters stay honest.
    expect(live.creates).toBe(0);
    expect(live.kills).toBe(0);
    expect(live.live).toBe(false);
    // And the graph is released with it, so a later `nodePosition` answers
    // `null` rather than reporting a position on a stage that has none.
    expect(live.nodePosition("youtube:pqlWNihgdjI:KU-000001")).toBeNull();
  });

  it("recovers on the next attach after a refusal, with one renderer alive", () => {
    // A refused container is usually a stage that has not been laid out yet
    // (D-140), so the next attempt is the normal case and must not inherit
    // anything from the failure.
    let refuse = true;
    const renderer = fakeRenderer();
    const live = session(() => {
      if (refuse) throw new Error("Container has no height.");
      return renderer;
    });
    expect(() => live.attach(sample())).toThrow();
    refuse = false;
    live.attach(sample());
    expect(live.live).toBe(true);
    expect(live.creates).toBe(1);
    live.kill();
    expect(live.kills).toBe(1);
    expect(renderer.calls).toContain("kill");
  });

  it("counts one kill per create, after any sequence", () => {
    const live = session(fakeRenderer);
    for (let round = 0; round < 5; round += 1) {
      live.attach(sample());
      live.update();
      live.resize();
      live.zoomIn();
      live.kill();
      // Idempotent: an unmount can follow a replacement, and both call kill.
      live.kill();
    }
    expect(live.creates).toBe(5);
    expect(live.kills).toBe(5);
    expect(live.live).toBe(false);
  });

  it("does nothing at all once killed, rather than throwing or reviving", () => {
    // A page that merged while the route was closing, or a ResizeObserver
    // callback after unmount, must not reach a dead context -- and must not
    // take the route down with an exception either.
    const renderer = fakeRenderer();
    const live = session(() => renderer);
    live.attach(sample());
    live.kill();
    const after = renderer.calls.length;

    expect(live.update()).toBeNull();
    live.resize();
    live.zoomIn();
    live.zoomOut();
    live.resetView();

    expect(renderer.calls.length).toBe(after);
    expect(live.creates).toBe(1);
    expect(live.kills).toBe(1);
  });

  describe("framing a focus (`T-209`, D-146)", () => {
    /*
     * What the walk found: the camera framed the whole 86-node graph, a
     * focus sat wherever the layout had left it, its neighbourhood spanned
     * about a tenth of the stage -- so every neighbour card was refused for
     * covering the focused one -- and `zoomIn` zooms about the *middle of the
     * stage*, so selecting a node and zooming in pushed it off screen. Two
     * halves of the Map that both knew where the focus was, with nothing
     * carrying it between them.
     */
    function framed(display: Record<string, MapPoint>) {
      const renderer = fakeRenderer();
      for (const [key, point] of Object.entries(display)) renderer.display.set(key, point);
      const live = session(() => renderer);
      live.attach(sample());
      return { live, renderer };
    }

    const KU1 = "youtube:pqlWNihgdjI:KU-000001";
    const KU2 = "youtube:pqlWNihgdjI:KU-000002";
    const C1 = "library:concepts:C-000001";

    it("centres the focus and its drawn neighbours, not the focus alone", () => {
      // A focus at the edge of its own neighbourhood would otherwise leave
      // half of that neighbourhood off the stage.
      const { live, renderer } = framed({
        [KU1]: { x: 0, y: 0 },
        [KU2]: { x: 0.4, y: 0 },
        [C1]: { x: 0.4, y: 0.2 },
      });
      expect(live.frame(KU1, [KU2, C1])).toBe(true);
      expect(renderer.framings).toHaveLength(1);
      // No preference: the renderer keeps its own easing (`motion.ts`).
      expect(renderer.calls).toContain("camera:animate:default");
      const target = renderer.framings[0] as MapCameraTarget;
      expect(target.x).toBeCloseTo(0.2);
      expect(target.y).toBeCloseTo(0.1);
      // The extent to show is 0.4, and the margin is what keeps the outermost
      // marks clear of the inset that refuses a clipped card.
      expect(target.ratio).toBeCloseTo(0.4 * MAP_FOCUS_MARGIN);
    });

    it("frames from the extent the camera can see, not from a bare span", () => {
      /*
       * A camera ratio is not a framed distance. The renderer scales the two
       * axes by the container's aspect and by a correction ratio derived from
       * the graph's bounding box, so the framed extent one ratio shows differs
       * along x and along y — and this used `max(spanX, spanY) * margin`,
       * leaving those terms to whatever `MAP_FOCUS_MARGIN` happened to absorb
       * on the one graph and the one viewport it was calibrated at. On a wide
       * graph in a landscape stage the correction is ~1.69 and the topmost and
       * bottommost neighbours landed off-stage: the failure the margin exists
       * to eliminate.
       */
      const ratioWith = (view: { width: number; height: number; ratio: number } | null) => {
        const renderer = fakeRenderer();
        renderer.display.set(KU1, { x: 0, y: 0 });
        renderer.display.set(KU2, { x: 0, y: 0.4 });
        const live = session(() => ({ ...renderer, visibleExtent: () => view }));
        live.attach(sample());
        expect(live.frame(KU1, [KU2])).toBe(true);
        return (renderer.framings[0] as MapCameraTarget).ratio;
      };

      // A landscape stage: 2.0 framed units across, 0.5 down. The 0.4 span is
      // 80% of the visible height and 20% of the visible width, so the height
      // is the axis that decides.
      const landscape = ratioWith({ width: 2, height: 0.5, ratio: 1 });
      expect(landscape).toBeCloseTo(0.8 * MAP_FOCUS_MARGIN, 5);

      // The same neighbourhood on a taller stage needs less zooming out.
      const portrait = ratioWith({ width: 0.5, height: 2, ratio: 1 });
      expect(portrait).toBeLessThan(landscape);
      expect(portrait).toBeCloseTo(0.2 * MAP_FOCUS_MARGIN, 5);

      // A renderer that cannot answer keeps the old estimate rather than
      // guessing an aspect it has not measured.
      expect(ratioWith(null)).toBeCloseTo(0.4 * MAP_FOCUS_MARGIN, 5);
    });

    it("does not zoom in on a lone mark until the rest of the graph is a rumour", () => {
      const { live, renderer } = framed({ [KU1]: { x: 0.5, y: 0.5 } });
      expect(live.frame(KU1)).toBe(true);
      expect((renderer.framings[0] as MapCameraTarget).ratio).toBe(MAP_FOCUS_MIN_RATIO);
    });

    it("ignores a neighbour the renderer does not hold rather than framing nothing", () => {
      // A neighbour the pages have not reached has no position, and a bounding
      // box that included a zero for it would frame empty space.
      const { live, renderer } = framed({ [KU1]: { x: 0.5, y: 0.5 } });
      expect(live.frame(KU1, [KU2, "youtube:v:absent"])).toBe(true);
      const target = renderer.framings[0] as MapCameraTarget;
      expect(target.x).toBeCloseTo(0.5);
      expect(target.y).toBeCloseTo(0.5);
    });

    it("refuses to move for a focus the renderer has no position for", () => {
      const { live, renderer } = framed({ [KU2]: { x: 0.5, y: 0.5 } });
      expect(live.frame(KU1, [KU2])).toBe(false);
      expect(renderer.framings).toHaveLength(0);
    });

    it("does nothing at all with no live renderer", () => {
      const live = session(fakeRenderer);
      expect(live.frame(KU1)).toBe(false);
      live.attach(sample());
      live.kill();
      expect(live.frame(KU1)).toBe(false);
    });

    it("arrives immediately for a reader who asked for less motion", () => {
      // The same policy as the three gestures beside it: the preference is
      // read at the gesture, and `motion.ts` owns the reading (`T-208`).
      const matchMedia = window.matchMedia;
      window.matchMedia = ((query: string) =>
        ({ matches: query.includes("reduce"), media: query })) as typeof window.matchMedia;
      try {
        const { live, renderer } = framed({ [KU1]: { x: 0.5, y: 0.5 } });
        live.frame(KU1);
        expect(renderer.calls).toContain("camera:animate:0");
      } finally {
        window.matchMedia = matchMedia;
      }
    });
  });

  it("re-settles the layout and refreshes when a page merges into the graph on screen", () => {
    const snapshot = new GraphSnapshot({});
    snapshot.applyPage(payload({ nodes: [unit("KU-000001"), unit("KU-000002")] }), page());
    const renderer = fakeRenderer();
    const live = session(() => renderer);
    live.attach(snapshot.graph);

    // A continuation page: a new node, and the edge that was held until it
    // arrived (D-059).
    snapshot.applyPage(
      payload({
        nodes: [concept("C-000001")],
        edges: [expressesConcept("youtube:pqlWNihgdjI:KU-000001", "library:concepts:C-000001")],
      }),
      page(),
    );
    const layout = live.update();

    expect(layout?.nodes).toBe(3);
    expect(layout?.edges).toBe(1);
    // A *full* refresh here, and that is the distinction: a merged page moved
    // every node, so the renderer's indices really do have to be rebuilt.
    expect(renderer.calls).toContain("refresh");
    expect(renderer.calls).not.toContain("refresh:restyle");
    expect(live.creates).toBe(1);
    snapshot.graph.forEachNode((_node, attributes) => {
      expect(Number.isFinite(attributes.x)).toBe(true);
      expect(Number.isFinite(attributes.y)).toBe(true);
    });
  });

  it("redraws without laying out again when only the view state changed", () => {
    // `T-205`: hover and selection are computed by the style table's reducers
    // at draw time, so a new drawing needs a `refresh` and nothing more. If it
    // went through `update()` instead, D-128's whole-graph relaxation would
    // move the picture under the pointer on every mouse move -- so what is
    // asserted is that the positions are *identical* afterwards, not merely
    // that `refresh` was called.
    const renderer = fakeRenderer();
    const live = session(() => renderer);
    const graph = sample();
    live.attach(graph);
    const before = graph
      .nodes()
      .map((node) => [graph.getNodeAttribute(node, "x"), graph.getNodeAttribute(node, "y")]);

    live.refresh();

    // `restyleOnly`, because a hover changes no structure and moves no node.
    // A bare `refresh()` is a *full* Sigma refresh: both indices cleared,
    // every node and edge re-added, edge groups rebuilt — twice per mark
    // crossed by a pointer sweep.
    expect(renderer.calls.filter((call) => call === "refresh:restyle")).toHaveLength(1);
    expect(renderer.calls.filter((call) => call === "refresh")).toHaveLength(0);
    expect(
      graph
        .nodes()
        .map((node) => [graph.getNodeAttribute(node, "x"), graph.getNodeAttribute(node, "y")]),
    ).toEqual(before);
    expect(live.creates).toBe(1);
    expect(live.kills).toBe(0);
  });

  it("refreshes nothing once killed", () => {
    const renderer = fakeRenderer();
    const live = session(() => renderer);
    live.attach(sample());
    live.kill();
    const after = renderer.calls.length;
    live.refresh();
    expect(renderer.calls.length).toBe(after);
  });

  it("draws an empty graph instead of failing on one", () => {
    // An honest empty Map is a state the Map must render: `total: null` is
    // unknown and never zero (D-123), and `inferSettings` divides by the
    // graph's order.
    const renderer = fakeRenderer();
    const live = session(() => renderer);
    const layout = live.attach(graphOf([]));
    expect(layout.nodes).toBe(0);
    expect(layout.iterations).toBe(0);
    expect(live.live).toBe(true);
  });

  it("bounds the layout pass instead of letting it grow with the graph", () => {
    /*
     * D-121's no-worker decision rests on an 86-node measurement, and nothing
     * bounds the accumulated graph: "Load more" is unbounded and the page
     * limit is 500. This ran 200 iterations whatever the order, on the main
     * thread inside a React effect, where `useGraphWalk`'s own `cancel()`
     * cannot reach it.
     *
     * A graph one page can deliver still gets every iteration; past that the
     * count comes down, and never below the floor that keeps it a layout.
     */
    // The schedule, over orders no unit test should actually lay out.
    expect(mapLayoutIterations(0)).toBe(0);
    expect(mapLayoutIterations(3)).toBe(MAP_LAYOUT_ITERATIONS);
    expect(mapLayoutIterations(500)).toBe(MAP_LAYOUT_ITERATIONS);
    // Above the budget the count falls, monotonically.
    const thousand = mapLayoutIterations(1000);
    const twoThousand = mapLayoutIterations(2000);
    expect(thousand).toBeLessThan(MAP_LAYOUT_ITERATIONS);
    expect(twoThousand).toBeLessThan(thousand);
    expect(twoThousand).toBeGreaterThanOrEqual(MAP_LAYOUT_MIN_ITERATIONS);
    // And never below the floor, however large.
    expect(mapLayoutIterations(40000)).toBe(MAP_LAYOUT_MIN_ITERATIONS);

    // And the session reports the schedule's answer, not the ceiling.
    const live = session(() => fakeRenderer());
    const graph = sample();
    expect(live.attach(graph).iterations).toBe(mapLayoutIterations(graph.order));
  });

  it("forces the resize, because the shrink direction is the one that shows", () => {
    const renderer = fakeRenderer();
    const live = session(() => renderer);
    live.attach(sample());
    live.resize();
    expect(renderer.calls).toContain("resize:true");
  });

  it("drives the camera for zoom and reset", () => {
    const renderer = fakeRenderer();
    const live = session(() => renderer);
    live.attach(sample());
    live.zoomIn();
    live.zoomOut();
    live.resetView();
    expect(renderer.calls.filter((call) => call.startsWith("camera:"))).toEqual([
      "camera:zoomIn",
      "camera:zoomOut",
      "camera:reset",
    ]);
  });
});

/**
 * The event and coordinate adapters (`T-207`, §8.6).
 *
 * Two properties are the whole point of routing them through the session
 * rather than wiring Sigma to React directly: the subscription is made once
 * when the renderer is created and dies with it, and what a click *does* can
 * change on every render without the renderer being rebuilt -- because
 * rebuilding it would kill the live one and take the accumulated picture with
 * it (D-126).
 */
describe("MapSession's canvas adapters", () => {
  let container: HTMLElement;

  beforeEach(() => {
    container = document.createElement("div");
    document.body.append(container);
  });

  function withHandlers(
    renderer: FakeRenderer,
    handlers: MapSessionHandlers = {},
  ): MapSession {
    return new MapSession({ container, createRenderer: () => renderer, handlers });
  }

  it("subscribes to the three node events and to the frame, once per renderer", () => {
    const renderer = fakeRenderer();
    const live = withHandlers(renderer);
    live.attach(sample());
    expect(renderer.calls.filter((call) => call.startsWith("onNode:"))).toEqual([
      "onNode:clickNode",
      "onNode:enterNode",
      "onNode:leaveNode",
    ]);
    expect(renderer.calls.filter((call) => call === "onRender")).toHaveLength(1);
  });

  it("reports a click, an enter and a leave with the node's own `global_id`", () => {
    const seen: string[] = [];
    const renderer = fakeRenderer();
    const live = withHandlers(renderer, {
      onSelectNode: (id) => seen.push(`select:${id}`),
      onEnterNode: (id) => seen.push(`enter:${id}`),
      onLeaveNode: (id) => seen.push(`leave:${id}`),
    });
    live.attach(sample());
    renderer.listeners.get("clickNode")?.("youtube:pqlWNihgdjI:KU-000001");
    renderer.listeners.get("enterNode")?.("youtube:pqlWNihgdjI:KU-000002");
    renderer.listeners.get("leaveNode")?.("youtube:pqlWNihgdjI:KU-000002");
    expect(seen).toEqual([
      "select:youtube:pqlWNihgdjI:KU-000001",
      "enter:youtube:pqlWNihgdjI:KU-000002",
      "leave:youtube:pqlWNihgdjI:KU-000002",
    ]);
  });

  it("reports to the handlers it has *now*, not the ones it was built with", () => {
    // This is why the subscription is a trampoline. A React view's callbacks
    // close over the current URL and change identity nearly every render; a
    // session that captured them would answer a click with a stale selection.
    const seen: string[] = [];
    const renderer = fakeRenderer();
    const live = withHandlers(renderer, { onSelectNode: () => seen.push("first") });
    live.attach(sample());
    live.setHandlers({ onSelectNode: () => seen.push("second") });
    renderer.listeners.get("clickNode")?.("youtube:pqlWNihgdjI:KU-000001");
    expect(seen).toEqual(["second"]);
  });

  it("does nothing for an event with no handler at all", () => {
    const renderer = fakeRenderer();
    const live = withHandlers(renderer);
    live.attach(sample());
    expect(() => renderer.listeners.get("clickNode")?.("youtube:pqlWNihgdjI:KU-000001")).not.toThrow();
  });

  it("resubscribes on a replacement, and the dead renderer's handlers are its own", () => {
    // The subscription lives and dies with the renderer, so a replacement
    // subscribes again rather than sharing the first one's listeners.
    const first = fakeRenderer();
    const second = fakeRenderer();
    const renderers = [first, second];
    let index = 0;
    const live = new MapSession({
      container,
      createRenderer: () => renderers[index++] as MapRenderer,
      handlers: {},
    });
    live.attach(sample());
    live.attach(sample());
    expect(second.calls.filter((call) => call.startsWith("onNode:"))).toHaveLength(3);
    expect(live.creates).toBe(2);
    expect(live.kills).toBe(1);
  });

  it("converts a node's graph position into container pixels", () => {
    // The fake offsets the point, so the answer proves the *renderer* was
    // asked rather than the graph attributes being handed back as if they were
    // already screen coordinates.
    const renderer = fakeRenderer();
    const live = withHandlers(renderer);
    const graph = sample();
    live.attach(graph);
    const key = "youtube:pqlWNihgdjI:KU-000001";
    const attributes = graph.getNodeAttributes(key);
    expect(live.nodePosition(key)).toEqual({ x: attributes.x + 100, y: attributes.y + 200 });
  });

  it("answers `null` rather than a guess for a node it cannot place", () => {
    const renderer = fakeRenderer();
    const live = withHandlers(renderer);
    live.attach(sample());
    // A node the graph does not hold.
    expect(live.nodePosition("youtube:pqlWNihgdjI:KU-999999")).toBeNull();
    // And after the renderer is gone, because a card anchored to a dead
    // renderer's last known position would point at a graph nobody is looking
    // at.
    live.kill();
    expect(live.nodePosition("youtube:pqlWNihgdjI:KU-000001")).toBeNull();
  });

  it("answers `null` before anything has been drawn", () => {
    const live = withHandlers(fakeRenderer());
    expect(live.nodePosition("youtube:pqlWNihgdjI:KU-000001")).toBeNull();
  });
});
