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
  MAP_LAYOUT_ITERATIONS,
  MapSession,
  type MapCamera,
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
};

function fakeRenderer(): FakeRenderer {
  const calls: string[] = [];
  const listeners = new Map<string, (globalId: string) => void>();
  const camera: MapCamera = {
    zoomIn: () => calls.push("camera:zoomIn"),
    zoomOut: () => calls.push("camera:zoomOut"),
    reset: () => calls.push("camera:reset"),
  };
  return {
    calls,
    resize: (force?: boolean) => calls.push(`resize:${String(force)}`),
    refresh: () => calls.push("refresh"),
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
    expect(renderer.calls).toContain("refresh");
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

    expect(renderer.calls.filter((call) => call === "refresh")).toHaveLength(1);
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
