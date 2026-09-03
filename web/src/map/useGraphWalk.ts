/**
 * `GraphWalk` bound to a React component (`T-204`).
 *
 * A binding, not a store. Every rule about pages, cursors, generations and
 * conflicts stays in `GraphWalk` and `GraphSnapshot`; this hook decides only
 * *when* a question is asked and makes sure the walk is released when the
 * route closes. §8.6 forbids a second graph store, and the reason is D-118: a
 * component that accumulated pages itself would reintroduce the dangling edge,
 * the invented node and the mixed filter the snapshot exists to prevent.
 *
 * The walk instance is held in a ref rather than in state, because it is
 * mutable and long-lived: re-creating it on a re-render would abandon a
 * request in flight and lose the accumulated graph. Its `onChange` is what
 * pulls a fresh `state()` into React, so the view re-renders on the same four
 * statuses every other list in this application uses.
 *
 * `deps` follows `useAsync` and `usePaged`: the caller names the values that
 * make this a different question, and a change to any of them opens a new
 * snapshot with its own graph. `T-205` passes its three real filters here;
 * `T-204` asks one unfiltered question.
 *
 * Two things this hook does *not* do. It never calls `loadMore` on its own --
 * a continuation is a deliberate act (D-118), which is the whole reason the
 * API is paged. And it never reports the graph as a value React can compare:
 * the graph is mutated in place, so `snapshotId` (a new graph) and
 * `pagesApplied` (more of the same graph) are the two facts a renderer can
 * actually key off.
 */

import { useCallback, useEffect, useRef, useState } from "react";

import type { GraphFilters } from "./graphSnapshot";
import { GraphWalk, type GraphPageLoader, type GraphWalkState } from "./graphWalk";
import type { MapGraph } from "./graphProjection";

export interface GraphWalkBinding {
  state: GraphWalkState;
  /** The graph a renderer draws. Mutated in place; never a render dependency. */
  graph: MapGraph | null;
  loadMore: () => void;
  cancel: () => void;
  /** Ask the same question again, from the first page. */
  reload: () => void;
}

export function useGraphWalk(
  load: GraphPageLoader,
  filters: GraphFilters,
  deps: readonly unknown[],
  options: { limit?: number } = {},
): GraphWalkBinding {
  const [nonce, setNonce] = useState(0);

  // `load` and `filters` are usually fresh closures and fresh objects on every
  // render; `deps` is the real identity of the question, so the latest values
  // are kept in refs and the effect keys off `deps` alone.
  const latestLoad = useRef(load);
  latestLoad.current = load;
  const latestFilters = useRef(filters);
  latestFilters.current = filters;

  const walkRef = useRef<GraphWalk | null>(null);
  const [state, setState] = useState<GraphWalkState>(() => ({
    status: "idle",
    loadingMore: false,
    error: null,
    snapshotId: 0,
    snapshot: null,
  }));

  /*
   * The walk is built once and `limit` was read once with it, so a later
   * change to `options.limit` was silently ignored — a page size the caller
   * asked for and never got, with nothing to say so. It is part of the
   * *question*, like the filters, so a change to it re-opens the walk: added
   * to the effect's keys below, where a filter change already is.
   *
   * Rebuilding the walk instead would drop the drawn graph on every change,
   * which is the failure the `cancel`-not-`dispose` comment below is about.
   */
  const limit = options.limit;

  if (walkRef.current === null) {
    walkRef.current = new GraphWalk((request, signal) => latestLoad.current(request, signal), {
      ...(limit === undefined ? {} : { limit }),
      onChange: () => {
        const current = walkRef.current;
        if (current !== null) setState(current.state());
      },
    });
  }
  const walk = walkRef.current;

  useEffect(() => {
    if (limit !== undefined) walk.setLimit(limit);
    void walk.open(latestFilters.current);
    // Not `dispose`: a filter change replaces the snapshot through the next
    // `open`, and disposing here would drop the graph between the two.
    // `cancel` retires the request in flight and keeps what was drawn.
    return () => walk.cancel();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [walk, nonce, limit, ...deps]);

  // Unmount is the only place the walk is released for good. Separate from the
  // effect above so a filter change cannot take the graph with it.
  useEffect(() => () => walk.dispose(), [walk]);

  const loadMore = useCallback(() => void walk.loadMore(), [walk]);
  const cancel = useCallback(() => walk.cancel(), [walk]);
  const reload = useCallback(() => setNonce((value) => value + 1), []);

  return { state, graph: walk.graph, loadMore, cancel, reload };
}
