/**
 * Cursor paging, shared by every list in the UI.
 *
 * The contract pages with opaque keyset cursors bound to their query, so the
 * only honest way to walk a collection is to follow `next_cursor` and never to
 * synthesise an offset. Two details are load-bearing:
 *
 * - `total` is `number | null`, and `null` means *the server did not count*,
 *   never zero. It is kept as `null` here and rendered as "not counted" rather
 *   than folded into a number.
 * - `hasMore` comes from `next_cursor`, not from comparing lengths against a
 *   limit, so a page that happens to be full does not claim there is more and
 *   a short page does not claim there is not.
 */

import { useCallback, useEffect, useRef, useState } from "react";

import { ApiFailure } from "./errors";
import type { AsyncStatus } from "./useAsync";

export interface Page<T> {
  items: T[];
  next: string | null;
  total: number | null;
}

export interface PagedState<T> {
  items: T[];
  total: number | null;
  hasMore: boolean;
  status: AsyncStatus;
  loadingMore: boolean;
  /**
   * Why the **first** page failed, or `null`.
   *
   * The first page failing means there is nothing to show, which is why every
   * call site renders an error panel instead of a list for it. A *later* page
   * failing is a different fact and is reported separately, in
   * :attr:`moreError` — this used to carry both, and all four call sites
   * branch on it before rendering items, so one transient hiccup on "More"
   * replaced fifty loaded records with an error panel and the only way back
   * discarded every page already fetched.
   */
  error: ApiFailure | null;
  /**
   * Why the last "More" failed, or `null`.
   *
   * What is already loaded stays loaded and stays rendered: a page that did
   * not arrive is a gap at the end of a list, not a reason to forget the list.
   * Cleared when another "More" is asked for, and by a new query.
   */
  moreError: ApiFailure | null;
  loadMore: () => void;
  reload: () => void;
}

function toFailure(cause: unknown): ApiFailure {
  return cause instanceof ApiFailure
    ? cause
    : new ApiFailure("internal", cause instanceof Error ? cause.message : String(cause));
}

export function usePaged<T>(
  load: (cursor: string | undefined, signal: AbortSignal) => Promise<Page<T>>,
  deps: readonly unknown[],
  options: { enabled?: boolean } = {},
): PagedState<T> {
  const enabled = options.enabled ?? true;
  const [items, setItems] = useState<T[]>([]);
  const [total, setTotal] = useState<number | null>(null);
  const [next, setNext] = useState<string | null>(null);
  const [status, setStatus] = useState<AsyncStatus>(enabled ? "loading" : "idle");
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<ApiFailure | null>(null);
  const [moreError, setMoreError] = useState<ApiFailure | null>(null);
  const [nonce, setNonce] = useState(0);

  const latest = useRef(load);
  latest.current = load;

  /**
   * D-079: every request belongs to one *generation* of the query.
   *
   * The effect below aborted only its own controller. `loadMore`'s controller
   * was never aborted and its `.then` had no liveness check, so switching
   * query while a "More" page was in flight let the stale page append onto the
   * new query's items and overwrite `next` with the *old* query's cursor — the
   * following "More" then paginated a collection the header no longer named.
   * The `.finally` was also an unconditional `setState`, which runs after
   * unmount and would clear the new query's spinner when a stale page settled.
   *
   * The generation is bumped in the effect's cleanup, which React runs before
   * the next effect and on unmount, so any page already in flight can tell
   * that its query is no longer the one on screen.
   */
  const generation = useRef(0);
  const pending = useRef(new Set<AbortController>());

  useEffect(() => {
    if (!enabled) {
      setStatus("idle");
      setItems([]);
      setTotal(null);
      setNext(null);
      setLoadingMore(false);
      setMoreError(null);
      return;
    }
    const controller = new AbortController();
    let live = true;
    setStatus("loading");
    setError(null);
    // A new query has no failed "More" either.
    setMoreError(null);
    // A new query has no "More" in flight. Without this the spinner could stay
    // on forever, because the stale `loadMore` that owned it no longer clears it.
    setLoadingMore(false);
    latest
      .current(undefined, controller.signal)
      .then((page) => {
        if (!live) return;
        setItems(page.items);
        setTotal(page.total);
        setNext(page.next);
        setStatus("ready");
      })
      .catch((cause: unknown) => {
        if (!live || controller.signal.aborted) return;
        setItems([]);
        setTotal(null);
        setNext(null);
        setError(toFailure(cause));
        setStatus("failed");
      });
    // Captured at setup rather than read in the cleanup. The set is created
    // once and never reassigned, so the two are the same object — but a ref
    // read in a cleanup is a thing `react-hooks/exhaustive-deps` is right to
    // flag in general, and a lint gate that runs is only useful if what it
    // says is acted on rather than silenced (D-203).
    const inFlightPages = pending.current;
    return () => {
      live = false;
      controller.abort();
      // D-079: retire this generation and abort every page still in flight for
      // it, so nothing that resolves later can touch the next query's state.
      generation.current += 1;
      for (const inFlight of inFlightPages) inFlight.abort();
      inFlightPages.clear();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, nonce, ...deps]);

  const loadMore = useCallback(() => {
    if (next === null || loadingMore) return;
    setLoadingMore(true);
    setMoreError(null);
    const controller = new AbortController();
    const mine = generation.current;
    pending.current.add(controller);
    // D-079: this page belongs to the query that was on screen when it was
    // asked for. If that is no longer the query on screen, the page is dropped
    // whole — it is never partially applied, because `next` and `items` only
    // mean anything together.
    const stale = () => mine !== generation.current;
    latest
      .current(next, controller.signal)
      .then((page) => {
        if (stale()) return;
        setItems((current) => [...current, ...page.items]);
        setNext(page.next);
        if (page.total !== null) setTotal(page.total);
      })
      .catch((cause: unknown) => {
        if (stale() || controller.signal.aborted) return;
        // `moreError`, not `error`. This set the same field the first page's
        // failure sets, and every call site branches on that field before
        // rendering items — so a transient hiccup on "More" replaced the
        // fifty records already on screen with an error panel, and the only
        // way back discarded every page already fetched.
        setMoreError(toFailure(cause));
      })
      .finally(() => {
        pending.current.delete(controller);
        if (stale()) return;
        setLoadingMore(false);
      });
  }, [next, loadingMore]);

  const reload = useCallback(() => setNonce((value) => value + 1), []);

  return {
    items,
    total,
    hasMore: next !== null,
    status,
    loadingMore,
    error,
    moreError,
    loadMore,
    reload,
  };
}
