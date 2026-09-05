/**
 * What a page of the source graph becomes, and what it refuses to become.
 *
 * The subject is one rule: a page may not draw a node it has no record of. The
 * graph pages over *nodes* and returns its relations whole, so a bounded page
 * carrying a relation to a source on the next page is the normal case rather
 * than an edge case — and it is exactly the case where inventing a mark would
 * be easiest and most wrong.
 */

import { describe, expect, it } from "vitest";

import { drawnSourceIds, projectSourceGraph } from "./sourceProjection";
import { seedPosition } from "./seedPositions";
import { FAIL, PASS, POST, graphPayload, sourceNode, summary } from "../test/sourceRecords";

describe("projectSourceGraph", () => {
  it("draws one node per source, keyed by its global id", () => {
    const projection = projectSourceGraph(graphPayload([sourceNode(PASS), sourceNode(POST)], []));
    expect(projection.graph.order).toBe(2);
    expect(projection.graph.hasNode(`${PASS}:source`)).toBe(true);
    expect(drawnSourceIds(projection)).toEqual([PASS, POST]);
  });

  it("carries the API's record verbatim and seeds a position from its identity", () => {
    const node = sourceNode(PASS);
    const projection = projectSourceGraph(graphPayload([node], []));
    const attributes = projection.graph.getNodeAttributes(node.global_id);
    expect(attributes.record).toBe(node);
    expect(attributes).toMatchObject(seedPosition(node.global_id));
  });

  it("keys an edge by the relation's own id, never by its endpoints", () => {
    const projection = projectSourceGraph(
      graphPayload([sourceNode(POST), sourceNode(PASS)], [summary(POST, PASS)]),
    );
    expect(projection.graph.size).toBe(1);
    expect(projection.graph.hasEdge("SR-f596992c42435c40")).toBe(true);
  });

  it("keeps two relationships between the same pair, because a pair may have two", () => {
    const projection = projectSourceGraph(
      graphPayload(
        [sourceNode(POST), sourceNode(PASS)],
        [
          summary(POST, PASS, { id: "SR-one", relation_type: "critiques" }),
          summary(POST, PASS, { id: "SR-two", relation_type: "supports" }),
        ],
      ),
    );
    expect(projection.graph.size).toBe(2);
  });

  it("counts a relationship whose other end is not on this page, and draws neither", () => {
    // The page carries one node and a relation naming two: the second source is
    // real, indexed and on a later page. A mark for it would be a node this
    // client has no record of.
    const projection = projectSourceGraph(graphPayload([sourceNode(POST)], [summary(POST, PASS)]));
    expect(projection.graph.order).toBe(1);
    expect(projection.graph.size).toBe(0);
    expect(projection.offPage).toHaveLength(1);
    expect(projection.offPage[0]?.to_source_id).toBe(PASS);
  });

  it("counts both ends: a relation from an absent source is off-page too", () => {
    const projection = projectSourceGraph(graphPayload([sourceNode(PASS)], [summary(POST, PASS)]));
    expect(projection.offPage).toHaveLength(1);
    expect(projection.graph.size).toBe(0);
  });

  it("ignores a duplicate node rather than merging two records into a third", () => {
    const first = sourceNode(PASS, { label: "first" });
    const second = sourceNode(PASS, { label: "second" });
    const projection = projectSourceGraph(graphPayload([first, second], []));
    expect(projection.graph.order).toBe(1);
    expect(projection.graph.getNodeAttributes(first.global_id).record.label).toBe("first");
  });

  it("ignores a duplicate relation id for the same reason", () => {
    const projection = projectSourceGraph(
      graphPayload(
        [sourceNode(POST), sourceNode(PASS)],
        [summary(POST, PASS), summary(POST, PASS, { relation_type: "supports" })],
      ),
    );
    expect(projection.graph.size).toBe(1);
  });

  it("draws a source that relates to nothing, exactly once", () => {
    // D-271's rule seen from the client: the graph pages over nodes, so a
    // source with no relationships is still a node and still appears.
    const projection = projectSourceGraph(graphPayload([sourceNode(FAIL)], []));
    expect(projection.graph.order).toBe(1);
    expect(projection.graph.size).toBe(0);
    expect(projection.offPage).toHaveLength(0);
  });

  it("draws nothing for an empty index, and does not fail doing it", () => {
    const projection = projectSourceGraph(graphPayload([], []));
    expect(projection.graph.order).toBe(0);
    expect(drawnSourceIds(projection)).toEqual([]);
  });
});
