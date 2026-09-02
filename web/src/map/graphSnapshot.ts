/**
 * The Map's progressive snapshot: pages in, one graph out (`T-203`, D-118).
 *
 * A page of `/api/graph` is not a drawable graph, and that is a property of
 * the contract rather than an accident. D-059: an edge is returned when both
 * of its endpoints pass the node filter and **at least one** of them is on
 * this page. So a page can carry an edge whose far endpoint arrives two pages
 * later, and the same edge is returned again on that later page. Handing one
 * page straight to a renderer therefore has three failure modes and no fourth:
 * the edge dangles, the far node gets invented, or connectivity is silently
 * dropped and a full walk no longer reproduces the API's graph.
 *
 * This class is the alternative. Pages accumulate into one
 * `MultiDirectedGraph`; nodes dedupe by `global_id`, edges by their own `id`;
 * an edge whose endpoints have not both arrived is **held**, not drawn and not
 * discarded, and is promoted the moment its far node is loaded. Nothing is ever
 * drawn that the API did not return.
 *
 * A repeated identity that carries a *different* record is a `GraphConflict`
 * error rather than a merge: choosing a winner would draw a record no request
 * returned. A page is checked whole before anything is inserted, so a refusal
 * leaves the snapshot exactly as it was rather than half-applied.
 *
 * **What "complete" means here.** `truncated` is the API's statement about a
 * page -- `limit` cut the node list short -- and it is true on *every* page of
 * a multi-page walk, including the last one, because both repository
 * implementations compare the page against the whole filtered node set. So the
 * accumulated graph cannot be called partial merely because a page said
 * `truncated`, and it cannot be called whole merely because the cursor ran out
 * either (ADR 0005 invariant 4). It is whole when the walk has finished, no
 * edge is still pending, and either the API stated that nothing was cut short
 * or the loaded node count has reached the stated `total`. `total` is `null`
 * when the server did not count, which is *unknown* and never zero: a snapshot
 * that cannot prove it is whole says so instead of assuming it.
 */

import type { Endpoints, EntityRef, GraphPayload, IndexedRelation, PageInfo } from "../api/contract";
import {
  GraphConflictError,
  type MapGraph,
  createMapGraph,
  edgeAttributes,
  nodeAttributes,
  recordDifference,
} from "./graphProjection";

/**
 * The filters `GET /api/graph` actually accepts, taken from the generated
 * contract rather than restated.
 *
 * ADR 0005 invariant 7: a control the Map describes as server-backed must
 * exist in this type. `kind` is deliberately not here -- the frozen operation
 * declares no such parameter, so a `kind` filter would be a request the server
 * never receives and a graph the user was told was filtered when it was not.
 * Widening this is an OpenAPI change first.
 */
export type GraphFilters = Omit<Endpoints["getGraph"]["query"], "limit" | "cursor">;

/** What the snapshot knows about itself, and what a view may state about it. */
export interface GraphSnapshotState {
  /** The question this snapshot answers. Two filter sets never share one. */
  filters: GraphFilters;
  /** Pages applied so far. `0` is a snapshot that has not been asked yet. */
  pagesApplied: number;
  /** Nodes drawn. */
  nodes: number;
  /** Edges drawn: both endpoints have arrived. */
  edges: number;
  /** Edges held back until their far endpoint arrives (D-059). Never dropped. */
  pendingEdges: number;
  /** Nodes matching the filters, as the server counted them; `null` is unknown. */
  knownNodeTotal: number | null;
  /** Another page exists. Read from `next_cursor`, never from a page's length. */
  hasMore: boolean;
  /** What the newest page said about itself: `limit` cut its node list short. */
  lastPageTruncated: boolean;
  /** The accumulated graph is the whole graph these filters describe. */
  complete: boolean;
}

export class GraphSnapshot {
  readonly filters: GraphFilters;
  readonly graph: MapGraph;

  /** Edges waiting for an endpoint, by edge `id`. */
  private readonly pending = new Map<string, IndexedRelation>();
  private cursor: string | null = null;
  private pages = 0;
  private truncated = false;
  private total: number | null = null;

  constructor(filters: GraphFilters, graph: MapGraph = createMapGraph()) {
    this.filters = filters;
    this.graph = graph;
  }

  /**
   * The token for the next page, or `null`.
   *
   * Opaque: it is stored and handed back to the API client, never parsed,
   * compared, or shown (ADR 0005 invariant 6). It is exposed for the walk to
   * pass along and for nothing else, which is why it is not in
   * `GraphSnapshotState`.
   */
  get nextCursor(): string | null {
    return this.cursor;
  }

  /** Whether a first request has been answered at all. */
  get started(): boolean {
    return this.pages > 0;
  }

  /**
   * Merge one page.
   *
   * Checked whole, then applied whole. A page that would conflict is refused
   * before a single node is inserted, so the snapshot after a refusal is the
   * snapshot before the request -- there is no half-merged state to reason
   * about, and retrying is a decision rather than a repair.
   */
  applyPage(payload: GraphPayload, page: PageInfo): void {
    this.check(payload);

    for (const record of payload.nodes) {
      if (!this.graph.hasNode(record.global_id)) {
        this.graph.addNode(record.global_id, nodeAttributes(record));
      }
    }

    // Every edge this page carried, plus every edge already waiting: this
    // page's nodes may be exactly what a held edge was waiting for.
    for (const record of payload.edges) {
      if (!this.graph.hasEdge(record.id)) this.pending.set(record.id, record);
    }
    for (const [id, record] of [...this.pending]) {
      if (!this.graph.hasNode(record.from_id) || !this.graph.hasNode(record.to_id)) continue;
      this.graph.addDirectedEdgeWithKey(id, record.from_id, record.to_id, edgeAttributes(record));
      this.pending.delete(id);
    }

    this.pages += 1;
    this.cursor = page.next_cursor;
    this.truncated = payload.truncated;
    // The last page to state a total wins. Both repositories report the same
    // total on every page of a walk; a walk that spans a rebuild is the only
    // way they differ, and the newest count is the one that is still true.
    this.total = page.total ?? null;
  }

  state(): GraphSnapshotState {
    const nodes = this.graph.order;
    const pendingEdges = this.pending.size;
    const hasMore = this.cursor !== null;
    const reachedTotal = this.total !== null && nodes === this.total;
    return {
      filters: this.filters,
      pagesApplied: this.pages,
      nodes,
      edges: this.graph.size,
      pendingEdges,
      knownNodeTotal: this.total,
      hasMore,
      lastPageTruncated: this.truncated,
      complete:
        this.pages > 0 && !hasMore && pendingEdges === 0 && (!this.truncated || reachedTotal),
    };
  }

  /**
   * Refuse a page that contradicts what is already known, naming the field.
   *
   * The same record arriving again is expected and silent -- D-059 repeats a
   * straddling edge on both of its pages, and a reload or a duplicate response
   * repeats everything. Only a genuine disagreement is an error.
   */
  private check(payload: GraphPayload): void {
    const nodes = new Map<string, EntityRef>();
    for (const record of payload.nodes) {
      const known = this.graph.hasNode(record.global_id)
        ? this.graph.getNodeAttribute(record.global_id, "record")
        : nodes.get(record.global_id);
      if (known === undefined) {
        nodes.set(record.global_id, record);
        continue;
      }
      const field = recordDifference(known, record);
      if (field !== null) throw new GraphConflictError("node", record.global_id, field);
    }

    const edges = new Map<string, IndexedRelation>();
    for (const record of payload.edges) {
      const known = this.graph.hasEdge(record.id)
        ? this.graph.getEdgeAttribute(record.id, "record")
        : (this.pending.get(record.id) ?? edges.get(record.id));
      if (known === undefined) {
        edges.set(record.id, record);
        continue;
      }
      const field = recordDifference(known, record);
      if (field !== null) throw new GraphConflictError("edge", record.id, field);
    }
  }
}
