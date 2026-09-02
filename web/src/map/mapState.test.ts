/**
 * `T-208`: the four pairs the Map must never collapse.
 *
 * Every test here is a *pair* rather than a state, because the defect this
 * module exists to prevent is not "the wrong message" -- it is two different
 * situations rendered as one true-sounding sentence. Empty and absent both
 * count zero nodes; refused and empty both draw nothing; partial and whole
 * both hold a real graph; undrawn and absent both show no picture.
 */

import { describe, expect, it } from "vitest";

import { ApiFailure } from "../api/errors";
import { GraphConflictError } from "./graphProjection";
import type { GraphSnapshotState } from "./graphSnapshot";
import type { GraphWalkState } from "./graphWalk";
import { describeCanvas, describeGraph } from "./mapState";

function snapshot(overrides: Partial<GraphSnapshotState> = {}): GraphSnapshotState {
  return {
    filters: {},
    pagesApplied: 1,
    nodes: 86,
    edges: 118,
    pendingEdges: 0,
    knownNodeTotal: 86,
    hasMore: false,
    lastPageTruncated: false,
    complete: true,
    ...overrides,
  };
}

function walk(overrides: Partial<GraphWalkState> = {}): GraphWalkState {
  return {
    status: "ready",
    loadingMore: false,
    error: null,
    snapshotId: 1,
    snapshot: snapshot(),
    ...overrides,
  };
}

describe("what the Map may say about its graph", () => {
  it("does not call an unanswered question an empty library", () => {
    // The pair. Both count zero nodes; only one of them is a statement about
    // what the library holds.
    const unasked = describeGraph(
      walk({ status: "idle", snapshot: snapshot({ pagesApplied: 0, nodes: 0, edges: 0 }) }),
    );
    expect(unasked.kind).toBe("unasked");
    expect(unasked.counted).toBe(false);

    const empty = describeGraph(
      walk({ snapshot: snapshot({ nodes: 0, edges: 0, knownNodeTotal: 0 }) }),
    );
    expect(empty.kind).toBe("empty");
    expect(empty.counted).toBe(true);
  });

  it("does not call a page of the graph the graph", () => {
    expect(describeGraph(walk({ snapshot: snapshot({ complete: true }) })).kind).toBe("whole");
    expect(
      describeGraph(walk({ snapshot: snapshot({ complete: false, hasMore: true }) })).kind,
    ).toBe("partial");
  });

  it("reads `complete` rather than deciding it from the counts", () => {
    // A snapshot that has reached the counted total and still says it is not
    // complete -- held edges, or a truncated last page -- is reported as
    // partial. The conclusion is the snapshot's (D-123).
    const reading = describeGraph(
      walk({ snapshot: snapshot({ nodes: 86, knownNodeTotal: 86, complete: false }) }),
    );
    expect(reading.kind).toBe("partial");
  });

  it("does not call a refused question an empty answer", () => {
    const refused = describeGraph(
      walk({
        status: "failed",
        error: new ApiFailure("index_unavailable", "not built"),
        snapshot: snapshot({ pagesApplied: 0, nodes: 0, edges: 0 }),
      }),
    );
    expect(refused.kind).toBe("refused");
    expect(refused.counted).toBe(false);
  });

  it("keeps the pages that did arrive countable, and does not call them the answer", () => {
    const refused = describeGraph(
      walk({ status: "failed", error: new ApiFailure("internal", "boom") }),
    );
    expect(refused.kind).toBe("refused");
    // The counts stay true and are still shown; the view adds the sentence
    // saying they are not an answer to the request that failed.
    expect(refused.counted).toBe(true);
    expect(refused.nodes).toBe(86);
  });

  it("names a refused page as a conflict rather than as a failed request", () => {
    const conflict = describeGraph(
      walk({
        status: "failed",
        error: new GraphConflictError("node", "youtube:v:KU-000001", "label"),
      }),
    );
    expect(conflict.kind).toBe("conflict");
  });

  it("reports loading over a graph that is already drawn", () => {
    const reading = describeGraph(walk({ status: "loading" }));
    expect(reading.kind).toBe("loading");
    expect(reading.counted).toBe(true);
  });

  it("does not treat a continuation in flight as a state of the graph", () => {
    // `loadingMore` is reported beside its own control. A drawn graph with a
    // continuation in flight is still that drawn graph.
    expect(describeGraph(walk({ loadingMore: true })).kind).toBe("whole");
  });

  it("copies the server's own total, and keeps `null` distinct from zero", () => {
    expect(describeGraph(walk({ snapshot: snapshot({ knownNodeTotal: null }) })).knownNodeTotal).toBe(
      null,
    );
    expect(describeGraph(walk({ snapshot: snapshot({ knownNodeTotal: 0, nodes: 0 }) })).knownNodeTotal).toBe(
      0,
    );
  });
});

describe("what the Map may say about its picture", () => {
  it("separates a browser that cannot draw from a renderer that refused a container", () => {
    // The pair `T-208` split. One message for both sent a reader with an
    // unsized stage looking for a different browser.
    const unavailable = describeCanvas({
      fault: { phase: "module", detail: "WebGL2RenderingContext is not defined" },
      holding: false,
      nodes: 2,
    });
    expect(unavailable.kind).toBe("unavailable");
    expect(unavailable.detail).toBe("WebGL2RenderingContext is not defined");
    expect(unavailable.interactive).toBe(false);

    const refused = describeCanvas({
      fault: { phase: "create", detail: "Container has no height." },
      // A renderer that refused is not holding anything, and the fault
      // outranks that anyway: a fault is *why* there is no picture.
      holding: false,
      nodes: 2,
    });
    expect(refused.kind).toBe("refused");
    expect(refused.interactive).toBe(false);
  });

  it("does not call a picture that has not been drawn a failure", () => {
    expect(describeCanvas({ fault: null, holding: false, nodes: 0 }).kind).toBe("pending");
    // The one that matters: a page has arrived and its nodes are counted, and
    // the effect that hands the graph to the renderer has not run yet. This
    // is a render, every time a page arrives.
    expect(describeCanvas({ fault: null, holding: false, nodes: 2 }).kind).toBe("pending");
  });

  it("calls an empty stage empty rather than broken, and keeps its camera", () => {
    const nothing = describeCanvas({ fault: null, holding: true, nodes: 0 });
    expect(nothing.kind).toBe("nothing");
    expect(nothing.interactive).toBe(true);
  });

  it("is drawing only when a live renderer holds a node", () => {
    const drawing = describeCanvas({ fault: null, holding: true, nodes: 86 });
    expect(drawing.kind).toBe("drawing");
    expect(drawing.detail).toBe(null);
    expect(drawing.interactive).toBe(true);
  });
});
