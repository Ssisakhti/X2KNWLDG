/**
 * The projection against the **real** server, where D-059 is a fact rather
 * than a fixture.
 *
 * The property this file exists for is the one no unit test can establish:
 * **page size does not change the graph.** Walking the served graph one or two
 * nodes at a time must accumulate exactly the nodes and edges that a single
 * unpaged request returns -- same identities, no edge lost to a page boundary,
 * none left dangling, and none invented to fill one. A mock would agree with
 * whatever this client assumed about paging; the server does not.
 *
 * Skipped unless `X2KNWLDG_API_BASE` names a running server, so `npm test`
 * stays hermetic:
 *
 *     npm run dev:api                                  # terminal one
 *     X2KNWLDG_API_BASE=http://127.0.0.1:8931 npm test # terminal two
 */

import { describe, expect, it } from "vitest";

import { ApiClient } from "../api/client";
import { GraphWalk, apiGraphPages } from "./graphWalk";

declare const process: { env: Record<string, string | undefined> };

const BASE = process.env.X2KNWLDG_API_BASE;
const client = new ApiClient({ baseUrl: BASE ?? "" });

/** A walk cannot be unbounded: a bug in `hasMore` would otherwise hang the suite. */
const MAX_PAGES = 500;

describe.skipIf(BASE === undefined || BASE === "")("the Map's snapshot against a running server", () => {
  it("accumulates page by page into the graph one whole request returns", async () => {
    const whole = await client.call("getGraph", { query: { limit: 500 } });
    // If this ever fires, the comparison below is against a cut graph and the
    // fixtures have outgrown one page -- not a failure of the projection.
    expect(whole.data.truncated).toBe(false);

    const walk = new GraphWalk(apiGraphPages(client), { limit: 1 });
    await walk.open({});
    let sawPending = false;
    let pages = 1;
    while (walk.state().snapshot?.hasMore === true && pages < MAX_PAGES) {
      if ((walk.state().snapshot?.pendingEdges ?? 0) > 0) sawPending = true;
      await walk.loadMore();
      pages += 1;
      expect(walk.state().error).toBeNull();
    }
    if ((walk.state().snapshot?.pendingEdges ?? 0) > 0) sawPending = true;

    const graph = walk.graph;
    expect(graph).not.toBeNull();
    expect(new Set(graph?.nodes())).toEqual(new Set(whole.data.nodes.map((node) => node.global_id)));
    expect(new Set(graph?.edges())).toEqual(new Set(whole.data.edges.map((relation) => relation.id)));

    const state = walk.state().snapshot;
    expect(state?.pendingEdges).toBe(0);
    expect(state?.nodes).toBe(whole.data.nodes.length);
    expect(state?.edges).toBe(whole.data.edges.length);
    expect(state?.complete).toBe(true);

    // One node per page makes every edge that is not a self-loop straddle two
    // pages, so the holding rule was either exercised on real data or the
    // served graph has no such edge at all. Written as an equality rather than
    // a conditional assertion, so neither half can pass by not happening.
    expect(sawPending).toBe(whole.data.edges.some((edge) => edge.from_id !== edge.to_id));
  });

  it("draws no edge to a node it does not hold, at any point in the walk", async () => {
    const walk = new GraphWalk(apiGraphPages(client), { limit: 1 });
    await walk.open({});
    let pages = 1;
    for (;;) {
      const graph = walk.graph;
      expect(graph).not.toBeNull();
      graph?.forEachEdge((_id, _attributes, source, target) => {
        expect(graph.hasNode(source)).toBe(true);
        expect(graph.hasNode(target)).toBe(true);
      });
      if (walk.state().snapshot?.hasMore !== true || pages >= MAX_PAGES) break;
      await walk.loadMore();
      pages += 1;
    }
  });

  it("answers a filter the contract declares, and states the smaller graph honestly", async () => {
    const walk = new GraphWalk(apiGraphPages(client), { limit: 500 });
    await walk.open({ provenance_class: "source" });
    const state = walk.state();
    expect(state.status).toBe("ready");
    expect(state.error).toBeNull();
    walk.graph?.forEachNode((_key, attributes) => {
      expect(attributes.record.provenance_class).toBe("source");
    });
    expect(state.snapshot?.pendingEdges).toBe(0);
  });
});
