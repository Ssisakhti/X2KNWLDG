/**
 * What a page of `/api/graph` may legitimately contain, and what the Map is
 * allowed to draw from it.
 *
 * D-059 is the whole reason this class exists, so it is the first thing
 * asserted: a page carries edges whose far endpoint is on another page, and a
 * renderer handed that page directly would dangle the edge, invent the missing
 * node, or drop connectivity that a full walk is supposed to reproduce. The
 * invariant these tests keep returning to is that at *no* point -- not after
 * one page, not after a refusal, not after a duplicate -- does the graph hold
 * an edge whose endpoints it does not hold.
 */

import { describe, expect, it } from "vitest";

import { GraphConflictError } from "./graphProjection";
import { GraphSnapshot } from "./graphSnapshot";
import { VIDEO, concept, edge, expressesConcept, page, payload, unit } from "../test/graphRecords";

const KU1 = `youtube:${VIDEO}:KU-000001`;
const KU2 = `youtube:${VIDEO}:KU-000002`;
const KU3 = `youtube:${VIDEO}:KU-000003`;
const C1 = "library:concepts:122c822b7bbf";

/** No rendered edge may reach a node the graph does not hold (ADR 0005 invariant 3). */
function expectNoDanglingEdge(snapshot: GraphSnapshot): void {
  snapshot.graph.forEachEdge((_id, _attributes, source, target) => {
    expect(snapshot.graph.hasNode(source)).toBe(true);
    expect(snapshot.graph.hasNode(target)).toBe(true);
  });
}

describe("GraphSnapshot", () => {
  it("starts empty, and does not claim to be a graph before it is asked", () => {
    const snapshot = new GraphSnapshot({});
    const state = snapshot.state();
    expect(state.pagesApplied).toBe(0);
    expect(state.nodes).toBe(0);
    expect(state.hasMore).toBe(false);
    expect(state.complete).toBe(false);
    expect(snapshot.started).toBe(false);
    expect(snapshot.nextCursor).toBeNull();
  });

  it("keeps the API's own identities as the graph's keys", () => {
    const snapshot = new GraphSnapshot({});
    const link = edge(KU1, KU2);
    snapshot.applyPage(
      payload({ nodes: [unit("KU-000001"), unit("KU-000002")], edges: [link] }),
      page({ total: 2 }),
    );
    expect(snapshot.graph.nodes()).toEqual([KU1, KU2]);
    expect(snapshot.graph.edges()).toEqual([link.id]);
    expect(snapshot.graph.getEdgeAttribute(link.id, "record")).toBe(link);
    expect(snapshot.graph.source(link.id)).toBe(KU1);
    expect(snapshot.graph.target(link.id)).toBe(KU2);
  });

  it("draws an empty graph as empty rather than as unfinished", () => {
    const snapshot = new GraphSnapshot({ source_id: "youtube:nothing" });
    snapshot.applyPage(payload(), page({ total: 0 }));
    const state = snapshot.state();
    expect(state.nodes).toBe(0);
    expect(state.edges).toBe(0);
    expect(state.pendingEdges).toBe(0);
    expect(state.knownNodeTotal).toBe(0);
    expect(state.complete).toBe(true);
  });

  it("keeps parallel relations apart instead of collapsing them into one", () => {
    // Two entities may be joined by more than one relation, and each is a
    // separate row of `relationships.json` with its own evidence.
    const snapshot = new GraphSnapshot({});
    const supports = edge(KU1, KU2, "supports");
    const elaborates = edge(KU1, KU2, "elaborates");
    snapshot.applyPage(
      payload({
        nodes: [unit("KU-000001"), unit("KU-000002")],
        edges: [supports, elaborates],
      }),
      page(),
    );
    expect(snapshot.state().edges).toBe(2);
    expect(new Set(snapshot.graph.edges())).toEqual(new Set([supports.id, elaborates.id]));
  });

  it("draws an intentional self-loop, because the pipeline marks it as a design", () => {
    const snapshot = new GraphSnapshot({});
    const loop = edge(KU1, KU1, "refines", { intentional_self_loop: true });
    snapshot.applyPage(payload({ nodes: [unit("KU-000001")], edges: [loop] }), page());
    expect(snapshot.state().edges).toBe(1);
    expect(snapshot.graph.getEdgeAttribute(loop.id, "record").intentional_self_loop).toBe(true);
    expectNoDanglingEdge(snapshot);
  });

  it("holds a D-059 edge whose far endpoint is on a later page", () => {
    const snapshot = new GraphSnapshot({});
    const straddling = expressesConcept(KU1, C1);
    // Page one: the unit, and an edge that reaches a concept still to come.
    snapshot.applyPage(
      payload({ nodes: [unit("KU-000001")], edges: [straddling], truncated: true }),
      page({ next_cursor: "opaque-1", total: 2 }),
    );
    let state = snapshot.state();
    expect(state.nodes).toBe(1);
    expect(state.edges).toBe(0);
    expect(state.pendingEdges).toBe(1);
    expect(state.complete).toBe(false);
    expectNoDanglingEdge(snapshot);

    // Page two: the far endpoint arrives, and the held edge is drawn -- with
    // no second copy, though the API returned it on both pages.
    snapshot.applyPage(
      payload({ nodes: [concept("122c822b7bbf")], edges: [straddling], truncated: true }),
      page({ next_cursor: null, total: 2 }),
    );
    state = snapshot.state();
    expect(state.nodes).toBe(2);
    expect(state.edges).toBe(1);
    expect(state.pendingEdges).toBe(0);
    expect(snapshot.graph.edges()).toEqual([straddling.id]);
    expectNoDanglingEdge(snapshot);
  });

  it("never drops a pending edge, however many pages arrive without its endpoint", () => {
    const snapshot = new GraphSnapshot({});
    const far = edge(KU1, KU3);
    snapshot.applyPage(payload({ nodes: [unit("KU-000001")], edges: [far] }), page({ next_cursor: "c1" }));
    snapshot.applyPage(payload({ nodes: [unit("KU-000002")] }), page({ next_cursor: "c2" }));
    expect(snapshot.state().pendingEdges).toBe(1);
    snapshot.applyPage(payload({ nodes: [unit("KU-000003")] }), page({ next_cursor: null }));
    expect(snapshot.state().pendingEdges).toBe(0);
    expect(snapshot.state().edges).toBe(1);
  });

  it("is unchanged by the same page arriving twice", () => {
    const snapshot = new GraphSnapshot({});
    const one = payload({
      nodes: [unit("KU-000001"), concept("122c822b7bbf")],
      edges: [expressesConcept(KU1, C1)],
    });
    snapshot.applyPage(one, page({ total: 2 }));
    const first = { ...snapshot.state(), pagesApplied: 0 };
    snapshot.applyPage(one, page({ total: 2 }));
    expect({ ...snapshot.state(), pagesApplied: 0 }).toEqual(first);
    expect(snapshot.state().pagesApplied).toBe(2);
    expect(snapshot.graph.order).toBe(2);
    expect(snapshot.graph.size).toBe(1);
  });

  it("refuses two pages that disagree about one node, and names the field", () => {
    const snapshot = new GraphSnapshot({});
    snapshot.applyPage(payload({ nodes: [unit("KU-000001")] }), page({ next_cursor: "c1" }));
    expect(() =>
      snapshot.applyPage(
        payload({ nodes: [unit("KU-000001", { confidence: 0.2 })] }),
        page({ next_cursor: null }),
      ),
    ).toThrowError(GraphConflictError);
    try {
      snapshot.applyPage(
        payload({ nodes: [unit("KU-000001", { confidence: 0.2 })] }),
        page({ next_cursor: null }),
      );
    } catch (cause) {
      expect(cause).toBeInstanceOf(GraphConflictError);
      const conflict = cause as GraphConflictError;
      expect(conflict.kind).toBe("node");
      expect(conflict.id).toBe(KU1);
      expect(conflict.field).toBe("confidence");
    }
  });

  it("refuses a page whole, leaving the snapshot exactly as it was", () => {
    // Half of a refused page is a graph that no request returned.
    const snapshot = new GraphSnapshot({});
    snapshot.applyPage(payload({ nodes: [unit("KU-000001")] }), page({ next_cursor: "c1" }));
    const before = snapshot.state();
    expect(() =>
      snapshot.applyPage(
        payload({
          nodes: [unit("KU-000002"), unit("KU-000001", { label: "a different statement" })],
          edges: [edge(KU1, KU2)],
        }),
        page({ next_cursor: null }),
      ),
    ).toThrowError(GraphConflictError);
    expect(snapshot.state()).toEqual(before);
    expect(snapshot.graph.order).toBe(1);
    expect(snapshot.graph.size).toBe(0);
    expect(snapshot.nextCursor).toBe("c1");
  });

  it("refuses two pages that disagree about one edge, drawn or still pending", () => {
    const drawn = new GraphSnapshot({});
    drawn.applyPage(
      payload({ nodes: [unit("KU-000001"), unit("KU-000002")], edges: [edge(KU1, KU2)] }),
      page({ next_cursor: "c1" }),
    );
    expect(() =>
      drawn.applyPage(
        payload({ edges: [edge(KU1, KU2, "supports", { confidence: 0.1 })] }),
        page({ next_cursor: null }),
      ),
    ).toThrowError(/disagree about edge/);

    // The same refusal for an edge that is still waiting for its endpoint: a
    // held edge is evidence too, and a second version of it is still a conflict.
    const pending = new GraphSnapshot({});
    pending.applyPage(
      payload({ nodes: [unit("KU-000001")], edges: [edge(KU1, KU3)] }),
      page({ next_cursor: "c1" }),
    );
    expect(pending.state().pendingEdges).toBe(1);
    expect(() =>
      pending.applyPage(
        payload({ edges: [edge(KU1, KU3, "supports", { provenance_class: "user" })] }),
        page({ next_cursor: null }),
      ),
    ).toThrowError(GraphConflictError);
  });

  it("reads `hasMore` from the cursor, never from how full a page looked", () => {
    const snapshot = new GraphSnapshot({});
    snapshot.applyPage(
      payload({ nodes: [unit("KU-000001")], truncated: true }),
      page({ limit: 500, next_cursor: "opaque", total: 86 }),
    );
    expect(snapshot.state().hasMore).toBe(true);
    expect(snapshot.nextCursor).toBe("opaque");
    expect(snapshot.state().complete).toBe(false);
  });

  it("calls one honest page the whole graph when the API says nothing was cut", () => {
    // The real sample: 86 nodes under the contract maximum, `truncated: false`,
    // `next_cursor: null`.
    const snapshot = new GraphSnapshot({});
    snapshot.applyPage(
      payload({ nodes: [unit("KU-000001"), unit("KU-000002")], edges: [edge(KU1, KU2)] }),
      page({ next_cursor: null, total: 2 }),
    );
    expect(snapshot.state().lastPageTruncated).toBe(false);
    expect(snapshot.state().complete).toBe(true);
  });

  it("calls a fully walked graph complete even though every page said `truncated`", () => {
    // Both repositories compute `truncated` against the whole filtered node
    // set, so the *last* page of a walk reports it too. Treating that as
    // partiality would mark a graph that holds every node the filter matched
    // as forever incomplete.
    const snapshot = new GraphSnapshot({});
    snapshot.applyPage(
      payload({ nodes: [unit("KU-000001")], truncated: true }),
      page({ limit: 1, next_cursor: "c1", total: 2 }),
    );
    expect(snapshot.state().complete).toBe(false);
    snapshot.applyPage(
      payload({ nodes: [unit("KU-000002")], truncated: true }),
      page({ limit: 1, next_cursor: null, total: 2 }),
    );
    const state = snapshot.state();
    expect(state.lastPageTruncated).toBe(true);
    expect(state.nodes).toBe(state.knownNodeTotal);
    expect(state.complete).toBe(true);
  });

  it("keeps a cut graph partial when the walk ends short of the stated total", () => {
    // The case ADR 0005 invariant 4 is about: reaching a null cursor is not
    // permission to call a truncated graph whole.
    const snapshot = new GraphSnapshot({});
    snapshot.applyPage(
      payload({ nodes: [unit("KU-000001")], truncated: true }),
      page({ next_cursor: null, total: 86 }),
    );
    expect(snapshot.state().hasMore).toBe(false);
    expect(snapshot.state().complete).toBe(false);
  });

  it("does not claim wholeness from a total the server did not count", () => {
    // `total: null` is unknown, never zero.
    const snapshot = new GraphSnapshot({});
    snapshot.applyPage(
      payload({ nodes: [unit("KU-000001")], truncated: true }),
      page({ next_cursor: null, total: null }),
    );
    expect(snapshot.state().knownNodeTotal).toBeNull();
    expect(snapshot.state().complete).toBe(false);
  });

  it("is not complete while an edge is still waiting for its endpoint", () => {
    const snapshot = new GraphSnapshot({});
    snapshot.applyPage(
      payload({ nodes: [unit("KU-000001")], edges: [edge(KU1, KU3)] }),
      page({ next_cursor: null, total: 1 }),
    );
    const state = snapshot.state();
    expect(state.pendingEdges).toBe(1);
    expect(state.complete).toBe(false);
    expectNoDanglingEdge(snapshot);
  });

  it("remembers which question it answers", () => {
    const filters = { source_id: `youtube:${VIDEO}`, provenance_class: "derived" } as const;
    const snapshot = new GraphSnapshot(filters);
    expect(snapshot.state().filters).toEqual(filters);
  });
});
