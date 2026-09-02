/**
 * The three things a component would get wrong about a paged graph.
 *
 * Which snapshot a page belongs to; what happens to a page that arrives after
 * its question stopped being asked; and what a cancelled or failed load leaves
 * on screen. Each is asserted here against an injected loader, because each is
 * a race that a rendered test can only observe by luck.
 */

import { describe, expect, it, vi } from "vitest";

import { ApiClient } from "../api/client";
import type { GraphResponse } from "../api/contract";
import { ApiFailure } from "../api/errors";
import { GraphConflictError } from "./graphProjection";
import {
  GRAPH_PAGE_LIMIT,
  GraphWalk,
  type GraphPageLoader,
  type GraphPageRequest,
  apiGraphPages,
} from "./graphWalk";
import { VIDEO, concept, edge, expressesConcept, page, payload, unit } from "../test/graphRecords";

const KU1 = `youtube:${VIDEO}:KU-000001`;
const KU2 = `youtube:${VIDEO}:KU-000002`;
const C1 = "library:concepts:122c822b7bbf";

function response(
  data: Partial<Parameters<typeof payload>[0]> = {},
  info: Partial<Parameters<typeof page>[0]> = {},
): GraphResponse {
  return {
    api_version: "v1",
    schema_version: "1.0",
    data: payload(data),
    page: page(info),
  };
}

/** A loader whose pages are released by hand, so a race can be written down. */
function deferredLoader(): {
  load: GraphPageLoader;
  requests: GraphPageRequest[];
  signals: AbortSignal[];
  release: (index: number, value: GraphResponse) => void;
  refuse: (index: number, cause: unknown) => void;
} {
  const requests: GraphPageRequest[] = [];
  const signals: AbortSignal[] = [];
  const settlers: { resolve: (value: GraphResponse) => void; reject: (cause: unknown) => void }[] =
    [];
  const load: GraphPageLoader = (request, signal) => {
    requests.push(request);
    signals.push(signal);
    return new Promise<GraphResponse>((resolve, reject) => {
      settlers.push({ resolve, reject });
    });
  };
  return {
    load,
    requests,
    signals,
    release: (index, value) => settlers[index]?.resolve(value),
    refuse: (index, cause) => settlers[index]?.reject(cause),
  };
}

describe("GraphWalk", () => {
  it("claims no graph before a filter set is opened", () => {
    const walk = new GraphWalk(deferredLoader().load);
    const state = walk.state();
    expect(state.status).toBe("idle");
    expect(state.snapshot).toBeNull();
    expect(walk.graph).toBeNull();
  });

  it("asks for the first page with no cursor and the contract's maximum", async () => {
    const pages = deferredLoader();
    const walk = new GraphWalk(pages.load);
    const opened = walk.open({ source_id: `youtube:${VIDEO}` });
    expect(walk.state().status).toBe("loading");
    expect(pages.requests[0]).toEqual({
      filters: { source_id: `youtube:${VIDEO}` },
      limit: GRAPH_PAGE_LIMIT,
      cursor: undefined,
    });
    pages.release(0, response({ nodes: [unit("KU-000001")] }, { total: 1 }));
    await opened;
    expect(walk.state().status).toBe("ready");
    expect(walk.state().snapshot?.nodes).toBe(1);
    expect(walk.graph?.hasNode(KU1)).toBe(true);
  });

  it("hands the cursor back exactly as it arrived, and never reads it", async () => {
    // The token is bound to the query and to the process. Anything this module
    // derived from it would be a position the server never issued.
    const opaque = "eyJmIjoiMDVmNjkzYmU5NjQ5ODdmNyJ9.32894f8d6423b63a9c44b4f1df0044ec";
    const pages = deferredLoader();
    const walk = new GraphWalk(pages.load);
    const opened = walk.open({});
    pages.release(0, response({ nodes: [unit("KU-000001")], truncated: true }, { next_cursor: opaque, total: 2 }));
    await opened;
    const more = walk.loadMore();
    expect(pages.requests[1]?.cursor).toBe(opaque);
    pages.release(1, response({ nodes: [unit("KU-000002")], truncated: true }, { next_cursor: null, total: 2 }));
    await more;
    const state = walk.state();
    expect(state.snapshot?.nodes).toBe(2);
    expect(state.snapshot?.hasMore).toBe(false);
    expect(state.snapshot?.complete).toBe(true);
  });

  it("does not continue a walk that has no next page", async () => {
    const pages = deferredLoader();
    const walk = new GraphWalk(pages.load);
    const opened = walk.open({});
    pages.release(0, response({ nodes: [unit("KU-000001")] }, { next_cursor: null, total: 1 }));
    await opened;
    await walk.loadMore();
    expect(pages.requests).toHaveLength(1);
  });

  it("asks for one continuation at a time", async () => {
    const pages = deferredLoader();
    const walk = new GraphWalk(pages.load);
    const opened = walk.open({});
    pages.release(0, response({ nodes: [unit("KU-000001")], truncated: true }, { next_cursor: "c1", total: 2 }));
    await opened;
    const first = walk.loadMore();
    void walk.loadMore();
    expect(pages.requests).toHaveLength(2);
    expect(walk.state().loadingMore).toBe(true);
    pages.release(1, response({ nodes: [unit("KU-000002")], truncated: true }, { next_cursor: null, total: 2 }));
    await first;
    expect(walk.state().loadingMore).toBe(false);
  });

  it("accumulates a D-059 edge across the pages of a walk", async () => {
    const pages = deferredLoader();
    const walk = new GraphWalk(pages.load);
    const straddling = expressesConcept(KU1, C1);
    const opened = walk.open({});
    pages.release(
      0,
      response({ nodes: [unit("KU-000001")], edges: [straddling], truncated: true }, { next_cursor: "c1", total: 2 }),
    );
    await opened;
    expect(walk.state().snapshot?.pendingEdges).toBe(1);
    expect(walk.graph?.size).toBe(0);
    const more = walk.loadMore();
    pages.release(
      1,
      response({ nodes: [concept("122c822b7bbf")], edges: [straddling], truncated: true }, { next_cursor: null, total: 2 }),
    );
    await more;
    expect(walk.state().snapshot?.pendingEdges).toBe(0);
    expect(walk.graph?.edges()).toEqual([straddling.id]);
  });

  it("aborts the walk in flight when the filters change", async () => {
    const pages = deferredLoader();
    const walk = new GraphWalk(pages.load);
    const first = walk.open({ provenance_class: "source" });
    expect(pages.signals[0]?.aborted).toBe(false);
    const second = walk.open({ provenance_class: "derived" });
    expect(pages.signals[0]?.aborted).toBe(true);
    expect(walk.state().snapshotId).toBe(2);
    expect(walk.state().snapshot?.filters).toEqual({ provenance_class: "derived" });
    pages.release(1, response({ nodes: [concept("122c822b7bbf")] }, { total: 1 }));
    await second;
    // The abandoned page answers late, as an aborted request still can.
    pages.release(0, response({ nodes: [unit("KU-000001"), unit("KU-000002")] }, { total: 2 }));
    await first;
    const state = walk.state();
    expect(state.snapshot?.nodes).toBe(1);
    expect(walk.graph?.hasNode(C1)).toBe(true);
    expect(walk.graph?.hasNode(KU1)).toBe(false);
  });

  it("gives the new question its own graph, so two snapshots cannot mix", async () => {
    const pages = deferredLoader();
    const walk = new GraphWalk(pages.load);
    const first = walk.open({});
    pages.release(0, response({ nodes: [unit("KU-000001")] }, { total: 1 }));
    await first;
    const before = walk.graph;
    const second = walk.open({ relation_vocabulary: "canonical" });
    expect(walk.graph).not.toBe(before);
    expect(walk.graph?.order).toBe(0);
    pages.release(1, response({ nodes: [unit("KU-000002")] }, { total: 1 }));
    await second;
    expect(before?.hasNode(KU1)).toBe(true);
    expect(walk.graph?.hasNode(KU1)).toBe(false);
  });

  it("reports a refused first page as a failure and draws nothing", async () => {
    const pages = deferredLoader();
    const walk = new GraphWalk(pages.load);
    const opened = walk.open({});
    pages.refuse(0, new ApiFailure("index_unavailable", "The index is being built."));
    await opened;
    const state = walk.state();
    expect(state.status).toBe("failed");
    expect(state.error).toBeInstanceOf(ApiFailure);
    expect(state.snapshot?.nodes).toBe(0);
    expect(state.snapshot?.pagesApplied).toBe(0);
  });

  it("keeps the drawn graph when a continuation fails, and states the failure", async () => {
    const pages = deferredLoader();
    const walk = new GraphWalk(pages.load);
    const opened = walk.open({});
    pages.release(0, response({ nodes: [unit("KU-000001")], truncated: true }, { next_cursor: "c1", total: 2 }));
    await opened;
    const more = walk.loadMore();
    pages.refuse(1, new ApiFailure("invalid_request", "That cursor did not survive a restart."));
    await more;
    const state = walk.state();
    expect(state.status).toBe("ready");
    expect(state.loadingMore).toBe(false);
    expect(state.error).toBeInstanceOf(ApiFailure);
    expect(state.snapshot?.nodes).toBe(1);
    expect(state.snapshot?.complete).toBe(false);
  });

  it("turns a page that contradicts the graph into a stated refusal", async () => {
    const pages = deferredLoader();
    const walk = new GraphWalk(pages.load);
    const opened = walk.open({});
    pages.release(0, response({ nodes: [unit("KU-000001")], truncated: true }, { next_cursor: "c1", total: 2 }));
    await opened;
    const more = walk.loadMore();
    pages.release(
      1,
      response({ nodes: [unit("KU-000001", { label: "a different statement" })] }, { next_cursor: null }),
    );
    await more;
    const state = walk.state();
    expect(state.error).toBeInstanceOf(GraphConflictError);
    expect((state.error as GraphConflictError).field).toBe("label");
    expect(state.snapshot?.nodes).toBe(1);
    expect(walk.graph?.getNodeAttribute(KU1, "record").label).toBe(unit("KU-000001").label);
  });

  it("wraps a loader that throws something that is not an API failure", async () => {
    const pages = deferredLoader();
    const walk = new GraphWalk(pages.load);
    const opened = walk.open({});
    pages.refuse(0, new TypeError("graph is not iterable"));
    await opened;
    const error = walk.state().error;
    expect(error).toBeInstanceOf(ApiFailure);
    expect((error as ApiFailure).code).toBe("internal");
  });

  it("keeps what a cancelled walk had already drawn", async () => {
    const pages = deferredLoader();
    const walk = new GraphWalk(pages.load);
    const opened = walk.open({});
    pages.release(0, response({ nodes: [unit("KU-000001")], truncated: true }, { next_cursor: "c1", total: 2 }));
    await opened;
    const more = walk.loadMore();
    walk.cancel();
    expect(pages.signals[1]?.aborted).toBe(true);
    pages.release(1, response({ nodes: [unit("KU-000002")] }, { next_cursor: null, total: 2 }));
    await more;
    const state = walk.state();
    expect(state.status).toBe("ready");
    expect(state.loadingMore).toBe(false);
    expect(state.snapshot?.nodes).toBe(1);
    expect(state.snapshot?.hasMore).toBe(true);
    expect(state.snapshot?.complete).toBe(false);
  });

  it("returns to idle when the first page is cancelled before it arrives", async () => {
    const pages = deferredLoader();
    const walk = new GraphWalk(pages.load);
    const opened = walk.open({});
    walk.cancel();
    expect(walk.state().status).toBe("idle");
    pages.release(0, response({ nodes: [unit("KU-000001")] }));
    await opened;
    expect(walk.state().snapshot?.pagesApplied).toBe(0);
  });

  it("releases everything on dispose", async () => {
    const pages = deferredLoader();
    const walk = new GraphWalk(pages.load);
    const opened = walk.open({});
    walk.dispose();
    expect(pages.signals[0]?.aborted).toBe(true);
    expect(walk.graph).toBeNull();
    expect(walk.state().snapshot).toBeNull();
    pages.release(0, response({ nodes: [unit("KU-000001")] }));
    await opened;
    expect(walk.state().snapshot).toBeNull();
  });

  it("tells a view when to look again", async () => {
    const pages = deferredLoader();
    const onChange = vi.fn();
    const walk = new GraphWalk(pages.load, { onChange });
    const opened = walk.open({});
    expect(onChange).toHaveBeenCalled();
    const afterOpen = onChange.mock.calls.length;
    pages.release(0, response({ nodes: [unit("KU-000001")] }, { total: 1 }));
    await opened;
    expect(onChange.mock.calls.length).toBeGreaterThan(afterOpen);
  });

  it("honours a smaller page size when one is asked for", async () => {
    const pages = deferredLoader();
    const walk = new GraphWalk(pages.load, { limit: 2 });
    void walk.open({});
    expect(pages.requests[0]?.limit).toBe(2);
  });
});

describe("apiGraphPages", () => {
  it("sends the filters, the limit and the cursor the contract declares", async () => {
    const seen: string[] = [];
    const fetchStub = (async (input: string) => {
      seen.push(String(input));
      return new Response(JSON.stringify(response({ nodes: [unit("KU-000001")] })), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }) as unknown as typeof fetch;
    const load = apiGraphPages(new ApiClient({ fetch: fetchStub }));
    await load(
      {
        filters: { source_id: `youtube:${VIDEO}`, relation_vocabulary: "library_synthetic" },
        limit: GRAPH_PAGE_LIMIT,
        cursor: "opaque-token",
      },
      new AbortController().signal,
    );
    const url = new URL(seen[0] ?? "", "http://127.0.0.1");
    expect(url.pathname).toBe("/api/graph");
    expect(url.searchParams.get("source_id")).toBe(`youtube:${VIDEO}`);
    expect(url.searchParams.get("relation_vocabulary")).toBe("library_synthetic");
    expect(url.searchParams.get("limit")).toBe(String(GRAPH_PAGE_LIMIT));
    expect(url.searchParams.get("cursor")).toBe("opaque-token");
  });

  it("omits the cursor on a first page rather than spelling it as empty", async () => {
    const seen: string[] = [];
    const fetchStub = (async (input: string) => {
      seen.push(String(input));
      return new Response(JSON.stringify(response()), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }) as unknown as typeof fetch;
    const load = apiGraphPages(new ApiClient({ fetch: fetchStub }));
    await load({ filters: {}, limit: 50, cursor: undefined }, new AbortController().signal);
    expect(seen[0]).toBe("/api/graph?limit=50");
  });
});

describe("the walk against a graph that is one honest page", () => {
  it("draws the whole sample and states that it is whole", async () => {
    const nodes = [unit("KU-000001"), unit("KU-000002"), concept("122c822b7bbf")];
    const edges = [edge(KU1, KU2), expressesConcept(KU2, C1)];
    const walk = new GraphWalk(async () => response({ nodes, edges }, { total: nodes.length }));
    await walk.open({});
    const state = walk.state();
    expect(state.snapshot?.nodes).toBe(3);
    expect(state.snapshot?.edges).toBe(2);
    expect(state.snapshot?.pendingEdges).toBe(0);
    expect(state.snapshot?.complete).toBe(true);
    expect(state.snapshot?.lastPageTruncated).toBe(false);
  });
});
