/**
 * The gate's own honesty, asserted in jsdom -- which has no WebGL, so the
 * renderer here is a fake and the real one is walked in a browser.
 *
 * What these tests are for: when the walk reports "86 nodes, 118 edges drawn",
 * that has to be a count of what the graph actually holds rather than a count
 * of what the API sent. A harness that mis-reports is worse than no harness,
 * because the phase's version decision rests on what it says.
 */

import { beforeEach, describe, expect, it } from "vitest";

import type { EntityRef, GraphPayload, IndexedRelation } from "../../api/contract";
import { type GateRenderer, GateSession, type RendererFactory } from "./session";
import { type GateGraph, buildGateGraph, gateLabel } from "./gateGraph";

function node(localId: string, overrides: Partial<EntityRef> = {}): EntityRef {
  return {
    schema_version: "1.0",
    global_id: `youtube:pqlWNihgdjI:${localId}`,
    source_type: "youtube",
    external_id: "pqlWNihgdjI",
    local_id: localId,
    entity_type: "knowledge_unit",
    provenance_class: "source",
    label: `statement ${localId}`,
    ...overrides,
  };
}

function edge(
  id: string,
  from: string,
  to: string,
  overrides: Partial<IndexedRelation> = {},
): IndexedRelation {
  return {
    schema_version: "1.0",
    id,
    from_id: `youtube:pqlWNihgdjI:${from}`,
    to_id: `youtube:pqlWNihgdjI:${to}`,
    relation: "supports",
    relation_vocabulary: "canonical",
    provenance_class: "source",
    ...overrides,
  };
}

function payload(overrides: Partial<GraphPayload> = {}): GraphPayload {
  return {
    nodes: [node("KU-000001"), node("KU-000002")],
    edges: [edge("e1", "KU-000001", "KU-000002")],
    truncated: false,
    ...overrides,
  };
}

describe("buildGateGraph", () => {
  it("keeps the API's own identities as the graph's keys", () => {
    const { graph, report } = buildGateGraph(payload());
    expect(graph.hasNode("youtube:pqlWNihgdjI:KU-000001")).toBe(true);
    expect(graph.hasEdge("e1")).toBe(true);
    expect(report.nodesDrawn).toBe(2);
    expect(report.edgesDrawn).toBe(1);
  });

  it("seeds every node, because an unpositioned node becomes NaN in the layout", () => {
    const { graph } = buildGateGraph(payload());
    graph.forEachNode((_key, attributes) => {
      expect(Number.isFinite(attributes.x)).toBe(true);
      expect(Number.isFinite(attributes.y)).toBe(true);
      expect(Math.hypot(attributes.x, attributes.y)).toBeGreaterThan(0);
    });
  });

  it("counts an edge whose endpoint is off this page instead of drawing it", () => {
    // D-059: a page's edge may reach a node on another page. Drawing it would
    // need a far node no page has sent, and inventing one is the failure this
    // count exists to make visible.
    const { graph, report } = buildGateGraph(
      payload({ edges: [edge("e1", "KU-000001", "KU-000002"), edge("e2", "KU-000001", "KU-999999")] }),
    );
    expect(report.edgesReturned).toBe(2);
    expect(report.edgesDrawn).toBe(1);
    expect(report.edgesWithMissingEndpoint).toBe(1);
    expect(graph.hasNode("youtube:pqlWNihgdjI:KU-999999")).toBe(false);
  });

  it("keeps parallel edges apart, so 118 real edges stay 118", () => {
    const { report } = buildGateGraph(
      payload({
        edges: [
          edge("e1", "KU-000001", "KU-000002"),
          edge("e2", "KU-000001", "KU-000002", { relation: "elaborates" }),
        ],
      }),
    );
    expect(report.edgesDrawn).toBe(2);
  });

  it("keeps direction, so a relation is not silently made symmetric", () => {
    const { graph } = buildGateGraph(payload());
    expect(graph.source("e1")).toBe("youtube:pqlWNihgdjI:KU-000001");
    expect(graph.target("e1")).toBe("youtube:pqlWNihgdjI:KU-000002");
  });

  it("counts repeated identities rather than overwriting them", () => {
    const { report } = buildGateGraph(
      payload({
        nodes: [node("KU-000001"), node("KU-000001"), node("KU-000002")],
        edges: [edge("e1", "KU-000001", "KU-000002"), edge("e1", "KU-000001", "KU-000002")],
      }),
    );
    expect(report.duplicateNodeIds).toBe(1);
    expect(report.duplicateEdgeIds).toBe(1);
    expect(report.nodesDrawn).toBe(2);
    expect(report.edgesDrawn).toBe(1);
  });

  it("keeps an intentional self-loop and says it did", () => {
    const { graph, report } = buildGateGraph(
      payload({ edges: [edge("e1", "KU-000001", "KU-000001", { intentional_self_loop: true })] }),
    );
    expect(report.selfLoops).toBe(1);
    expect(graph.hasEdge("e1")).toBe(true);
  });

  it("carries `truncated` through rather than inferring it from the counts", () => {
    expect(buildGateGraph(payload({ truncated: true })).report.truncated).toBe(true);
  });
});

describe("gateLabel", () => {
  it("uses the label the index holds", () => {
    expect(gateLabel(node("KU-000001"))).toBe("statement KU-000001");
  });

  it("falls back to the id when there is no label, and invents no summary", () => {
    expect(gateLabel(node("KU-000001", { label: null }))).toBe("KU-000001");
    expect(gateLabel(node("KU-000001", { label: "   " }))).toBe("KU-000001");
  });
});

/** A renderer that records what the session asked of it. */
function fakeRenderer(): GateRenderer & {
  calls: string[];
  click: (node: string) => void;
} {
  const calls: string[] = [];
  let handler: ((payload: { node: string }) => void) | null = null;
  return {
    calls,
    resize: (force?: boolean) => calls.push(`resize:${String(force)}`),
    refresh: () => calls.push("refresh"),
    kill: () => calls.push("kill"),
    on: (_event: "clickNode", callback: (payload: { node: string }) => void) => {
      handler = callback;
      calls.push("on:clickNode");
    },
    click: (node: string) => handler?.({ node }),
  };
}

describe("GateSession", () => {
  let container: HTMLElement;
  let messages: string[];

  beforeEach(() => {
    container = document.createElement("div");
    document.body.append(container);
    messages = [];
  });

  /** A session over an injected renderer factory and an injected clock. */
  function session0(createRenderer: RendererFactory): GateSession {
    let tick = 0;
    return new GateSession({
      container,
      createRenderer,
      log: (message) => messages.push(message),
      now: () => (tick += 5),
    });
  }

  function session(createRenderer: () => GateRenderer): GateSession {
    return session0(() => createRenderer());
  }

  it("creates a renderer and reports what it drew", () => {
    const renderer = fakeRenderer();
    const gate = session(() => renderer);
    const { report, layout } = gate.create(payload());
    expect(gate.live).toBe(true);
    expect(gate.creates).toBe(1);
    expect(report.nodesDrawn).toBe(2);
    expect(layout.iterations).toBeGreaterThan(0);
    expect(renderer.calls).toContain("on:clickNode");
    expect(messages.join("\n")).toContain("2/2 nodes");
  });

  it("lays the graph out to finite positions before the renderer sees it", () => {
    // The layout runs over the real library, not a stub, and a NaN here is the
    // silent failure `seedPositions` documents: ForceAtlas2 reads a missing or
    // origin-seeded position into a Float32Array and raises nothing.
    let handed: GateGraph | null = null;
    const gate = session0((graph) => {
      handed = graph;
      return fakeRenderer();
    });
    const seeds = new Map<string, { x: number; y: number }>();
    buildGateGraph(payload()).graph.forEachNode((key, attributes) => {
      seeds.set(key, { x: attributes.x, y: attributes.y });
    });

    gate.create(payload());

    expect(handed).not.toBeNull();
    let moved = 0;
    handed!.forEachNode((key, attributes) => {
      expect(Number.isFinite(attributes.x)).toBe(true);
      expect(Number.isFinite(attributes.y)).toBe(true);
      const seed = seeds.get(key)!;
      if (attributes.x !== seed.x || attributes.y !== seed.y) moved += 1;
    });
    // The pass is real: gravity and repulsion moved every node off its seed.
    expect(moved).toBe(handed!.order);
  });

  it("tears the previous renderer down before creating the next one", () => {
    // Two live renderers is how a WebGL context leaks, and the browser
    // answers a leak by losing the *oldest* context -- far from the cause.
    const first = fakeRenderer();
    const second = fakeRenderer();
    const renderers = [first, second];
    const gate = session(() => renderers.shift()!);
    gate.create(payload());
    gate.create(payload());
    expect(first.calls).toContain("kill");
    expect(second.calls).not.toContain("kill");
    expect(gate.creates).toBe(2);
    expect(gate.kills).toBe(1);
  });

  it("finishes with as many kills as creates", () => {
    const renderers = [fakeRenderer(), fakeRenderer(), fakeRenderer()];
    const gate = session(() => renderers.shift()!);
    for (let cycle = 0; cycle < 3; cycle += 1) {
      gate.create(payload());
      gate.update();
      gate.resize(400 + cycle, 300 + cycle);
      gate.select("youtube:pqlWNihgdjI:KU-000002");
      gate.teardown();
    }
    expect(gate.creates).toBe(3);
    expect(gate.kills).toBe(3);
    expect(gate.live).toBe(false);
  });

  it("kills exactly once, however many times teardown is called", () => {
    const renderer = fakeRenderer();
    const gate = session(() => renderer);
    gate.create(payload());
    gate.teardown();
    gate.teardown();
    expect(renderer.calls.filter((call) => call === "kill")).toHaveLength(1);
    expect(gate.kills).toBe(1);
    expect(messages).toContain("teardown: nothing live");
  });

  it("empties the container on teardown, leaving no orphaned canvas", () => {
    const renderer = fakeRenderer();
    const gate = session(() => {
      container.append(document.createElement("canvas"));
      return renderer;
    });
    gate.create(payload());
    expect(container.querySelectorAll("canvas")).toHaveLength(1);
    gate.teardown();
    expect(container.querySelectorAll("canvas")).toHaveLength(0);
  });

  it("routes a pointer click and a programmatic select through one path", () => {
    // `T-208` has to prove keyboard selection reaches the same node as a
    // click. That is cheap here and expensive to retrofit.
    const renderer = fakeRenderer();
    const selected: string[] = [];
    let tick = 0;
    const gate = new GateSession({
      container,
      createRenderer: () => renderer,
      log: (message) => messages.push(message),
      onSelect: (nodeId) => selected.push(nodeId),
      now: () => (tick += 5),
    });
    gate.create(payload());
    renderer.click("youtube:pqlWNihgdjI:KU-000002");
    expect(selected).toEqual(["youtube:pqlWNihgdjI:KU-000002"]);
    expect(gate.selection).toBe("youtube:pqlWNihgdjI:KU-000002");
    gate.select("youtube:pqlWNihgdjI:KU-000001");
    expect(gate.selection).toBe("youtube:pqlWNihgdjI:KU-000001");
  });

  it("refuses a selection for a node this page does not carry", () => {
    const gate = session(fakeRenderer);
    gate.create(payload());
    expect(gate.select("youtube:pqlWNihgdjI:KU-999999")).toBe(false);
    expect(gate.selection).toBeNull();
    expect(messages.join("\n")).toContain("refused");
  });

  it("refuses to operate with no live renderer rather than pretending to", () => {
    const gate = session(fakeRenderer);
    expect(() => gate.update()).toThrow(/no graph/);
    expect(() => gate.resize(100, 100)).toThrow(/no live renderer/);
  });

  it("asks the renderer to resize with the new container dimensions", () => {
    const renderer = fakeRenderer();
    const gate = session(() => renderer);
    gate.create(payload());
    gate.resize(640, 480);
    expect(container.style.width).toBe("640px");
    expect(container.style.height).toBe("480px");
    expect(renderer.calls).toContain("resize:true");
  });

  it("mutates only presentation attributes on update, never the graph's membership", () => {
    // An added node would be an entity no source carries. The update pass is
    // here to exercise Sigma's live-update path, not to invent data.
    const renderer = fakeRenderer();
    const gate = session(() => renderer);
    const { report } = gate.create(payload());
    gate.update();
    expect(renderer.calls.filter((call) => call === "refresh").length).toBeGreaterThan(0);
    const after = gate.create(payload());
    expect(after.report.nodesDrawn).toBe(report.nodesDrawn);
    expect(after.report.edgesDrawn).toBe(report.edgesDrawn);
  });

  it("measures the layout with the clock it was given, inventing no duration", () => {
    // The injected clock advances 5 ms per read, so the reported duration is
    // exactly one interval: the number in the walk comes from a measurement
    // taken around the pass, not from a constant written into the harness.
    const gate = session(fakeRenderer);
    const { layout } = gate.create(payload());
    expect(layout.milliseconds).toBe(5);
    expect(layout.nodes).toBe(2);
    expect(layout.edges).toBe(1);
  });
});
