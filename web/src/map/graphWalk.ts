/**
 * The walk that fills a `GraphSnapshot`, and the one thing that may replace it
 * (`T-203`, D-118).
 *
 * The store is deliberately framework-free: no React, no renderer, no DOM. It
 * owns three facts that are easy to get wrong in a component and hard to test
 * there -- which snapshot a page belongs to, what happens to a page that
 * arrives after its question stopped being asked, and what a cancelled load
 * leaves behind.
 *
 * **A filter change is a new question, not more of the old one.** `open`
 * aborts whatever is in flight, retires the generation it belonged to, and
 * starts a fresh snapshot with its own graph. Nothing from the previous walk
 * can reach the new one: a stale response is dropped whole rather than
 * partially applied, because a page's nodes, its edges and its cursor only
 * mean anything together (the lesson D-079 recorded when a stale page appended
 * onto a query the header no longer named). The two snapshots never share a
 * graph object, so "filter snapshots never mix" (ADR 0005 invariant 5) is a
 * property of the structure rather than a rule to remember.
 *
 * **Cursors are carried, never read.** The token from `page.next_cursor` is
 * handed straight back to the API client. This module does not decode it,
 * compare it, or derive a position from it, and it does not synthesise an
 * offset when one is absent (invariant 6).
 *
 * The status vocabulary is the application's existing four, and the meanings
 * are stated because a graph makes two of them ambiguous:
 *
 * - `idle` -- nothing has been asked, or a first page was cancelled before it
 *   arrived. There is no graph, and none is claimed.
 * - `loading` -- the first page of the current snapshot is in flight.
 * - `ready` -- at least one page has been applied. The snapshot's own state
 *   says whether that is the whole graph; `ready` never means complete.
 * - `failed` -- the first page was refused and nothing is drawn.
 *
 * A later page that fails leaves the status `ready` and states the error
 * beside the graph already drawn, because discarding accumulated evidence to
 * report a failed continuation would lose data the server did send.
 */

import { type ApiClient, api } from "../api/client";
import type { Endpoints, GraphResponse } from "../api/contract";
import { ApiFailure } from "../api/errors";
import type { AsyncStatus } from "../api/useAsync";
import { GraphConflictError, type MapGraph } from "./graphProjection";
import { GraphSnapshot, type GraphFilters, type GraphSnapshotState } from "./graphSnapshot";

/**
 * Nodes requested per page.
 *
 * The contract's maximum, so the real sample arrives as one honest page rather
 * than as a walk the user has to drive for no reason, and so the first request
 * is bounded by a number the server declares rather than by a hope.
 * `tests/test_ui_scaffold.py` fails if this stops matching the `limit` maximum
 * in the frozen document.
 */
export const GRAPH_PAGE_LIMIT = 500;

export interface GraphPageRequest {
  filters: GraphFilters;
  limit: number;
  /** The previous page's `next_cursor`, opaque, or `undefined` for the first. */
  cursor: string | undefined;
}

export type GraphPageLoader = (
  request: GraphPageRequest,
  signal: AbortSignal,
) => Promise<GraphResponse>;

/** A refusal the Map can state: the server's, or a page that contradicts one already drawn. */
export type GraphWalkFailure = ApiFailure | GraphConflictError;

export interface GraphWalkState {
  status: AsyncStatus;
  /** A continuation page is in flight. Distinct from `loading`, which is the first. */
  loadingMore: boolean;
  error: GraphWalkFailure | null;
  /** Increments when a filter change replaced the snapshot -- and its graph. */
  snapshotId: number;
  /** `null` until a filter set has been opened. */
  snapshot: GraphSnapshotState | null;
}

export interface GraphWalkOptions {
  /** Nodes per request. Defaults to the contract maximum. */
  limit?: number;
  /** Called after every state change, so a view can re-read `state()`. */
  onChange?: () => void;
}

function toFailure(cause: unknown): GraphWalkFailure {
  if (cause instanceof ApiFailure || cause instanceof GraphConflictError) return cause;
  return new ApiFailure("internal", cause instanceof Error ? cause.message : String(cause));
}

export class GraphWalk {
  private readonly load: GraphPageLoader;
  private limit: number;
  private readonly onChange: (() => void) | undefined;

  private snapshot: GraphSnapshot | null = null;
  private snapshotId = 0;
  private status: AsyncStatus = "idle";
  private loadingMore = false;
  private error: GraphWalkFailure | null = null;

  /** Which question the in-flight request belongs to. Bumped by every replacement. */
  private generation = 0;
  private controller: AbortController | null = null;

  constructor(load: GraphPageLoader, options: GraphWalkOptions = {}) {
    this.load = load;
    this.limit = options.limit ?? GRAPH_PAGE_LIMIT;
    this.onChange = options.onChange;
  }

  /** The graph a renderer draws, or `null` before the first `open`. */
  get graph(): MapGraph | null {
    return this.snapshot === null ? null : this.snapshot.graph;
  }

  state(): GraphWalkState {
    return {
      status: this.status,
      loadingMore: this.loadingMore,
      error: this.error,
      snapshotId: this.snapshotId,
      snapshot: this.snapshot === null ? null : this.snapshot.state(),
    };
  }

  /** Ask a new question. Replaces the snapshot, its graph, and any in-flight page. */
  async open(filters: GraphFilters): Promise<void> {
    this.retire();
    this.snapshot = new GraphSnapshot(filters);
    this.snapshotId += 1;
    this.status = "loading";
    this.loadingMore = false;
    this.error = null;
    this.changed();
    await this.fetchPage(this.snapshot, undefined);
  }

  /**
   * Load the next page of the current snapshot.
   *
   * Deliberate, never automatic: the Map shows an overview first and grows it
   * when asked, which is the reason the API is paged at all. A no-op when
   * there is no next page, when one is already in flight, or when the first
   * page has not arrived yet.
   */
  async loadMore(): Promise<void> {
    const snapshot = this.snapshot;
    if (snapshot === null || !snapshot.started) return;
    if (this.loadingMore || this.status === "loading") return;
    const cursor = snapshot.nextCursor;
    if (cursor === null) return;
    this.loadingMore = true;
    this.error = null;
    this.changed();
    await this.fetchPage(snapshot, cursor);
  }

  /**
   * Stop the request in flight and keep what has already been drawn.
   *
   * A cancelled continuation leaves a smaller graph that still says, through
   * `hasMore` and `complete`, that it is not the whole one.
   */
  cancel(): void {
    this.retire();
    this.loadingMore = false;
    this.status = this.snapshot !== null && this.snapshot.started ? "ready" : "idle";
    this.changed();
  }

  /**
   * Change the page size the next request will ask for.
   *
   * Not `readonly`, because `limit` is part of the *question* and a question
   * can change: `useGraphWalk` read it once at construction, so a caller that
   * changed it was silently given the old page size for the life of the hook.
   * The walk is not rebuilt for it — that would drop the drawn graph — so the
   * new value applies from the next `open`, which is what the hook triggers.
   */
  setLimit(limit: number): void {
    this.limit = limit;
  }

  /**
   * Release the walk: nothing in flight, nothing drawn, no snapshot.
   *
   * The one operation that does **not** report. Every other transition ends in
   * `changed()` because something is still watching, and this one is called
   * from an unmount cleanup — the single path where the change callback fires
   * with no consumer left, which in React means a `setState` on a component
   * that has gone. The state it would report is unreachable by construction:
   * after `dispose` there is nothing to render and nothing to render it.
   *
   * `cancel()` is the operation that *does* report, and it is the one a filter
   * change and a `Load more` refusal go through.
   */
  dispose(): void {
    this.retire();
    this.snapshot = null;
    this.status = "idle";
    this.loadingMore = false;
    this.error = null;
  }

  private retire(): void {
    this.generation += 1;
    this.controller?.abort();
    this.controller = null;
  }

  private async fetchPage(snapshot: GraphSnapshot, cursor: string | undefined): Promise<void> {
    const mine = this.generation;
    const controller = new AbortController();
    this.controller = controller;
    const first = cursor === undefined;
    try {
      const response = await this.load(
        { filters: snapshot.filters, limit: this.limit, cursor },
        controller.signal,
      );
      // The question moved on while this page was in flight. Drop it whole.
      if (mine !== this.generation) return;
      snapshot.applyPage(response.data, response.page);
      this.status = "ready";
    } catch (cause) {
      if (mine !== this.generation || controller.signal.aborted) return;
      this.error = toFailure(cause);
      if (first) this.status = "failed";
    } finally {
      if (mine === this.generation) {
        this.controller = null;
        this.loadingMore = false;
        this.changed();
      }
    }
  }

  private changed(): void {
    this.onChange?.();
  }
}

/**
 * The default loader: the typed client, calling the frozen operation.
 *
 * Every filter reaches the server through `Endpoints["getGraph"]["query"]`, so
 * a parameter the contract does not declare is a compile error rather than a
 * query string the server ignores while the UI claims a filtered graph.
 */
export function apiGraphPages(client: ApiClient = api): GraphPageLoader {
  return (request, signal) => {
    const query: Endpoints["getGraph"]["query"] = {
      ...request.filters,
      limit: request.limit,
      cursor: request.cursor,
    };
    return client.call("getGraph", { query, signal });
  };
}
