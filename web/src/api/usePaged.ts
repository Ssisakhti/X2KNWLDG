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
  error: ApiFailure | null;
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
  const [nonce, setNonce] = useState(0);

  const latest = useRef(load);
  latest.current = load;

  useEffect(() => {
    if (!enabled) {
      setStatus("idle");
      setItems([]);
      setTotal(null);
      setNext(null);
      return;
    }
    const controller = new AbortController();
    let live = true;
    setStatus("loading");
    setError(null);
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
    return () => {
      live = false;
      controller.abort();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, nonce, ...deps]);

  const loadMore = useCallback(() => {
    if (next === null || loadingMore) return;
    setLoadingMore(true);
    const controller = new AbortController();
    latest
      .current(next, controller.signal)
      .then((page) => {
        setItems((current) => [...current, ...page.items]);
        setNext(page.next);
        if (page.total !== null) setTotal(page.total);
      })
      .catch((cause: unknown) => setError(toFailure(cause)))
      .finally(() => setLoadingMore(false));
  }, [next, loadingMore]);

  const reload = useCallback(() => setNonce((value) => value + 1), []);

  return { items, total, hasMore: next !== null, status, loadingMore, error, loadMore, reload };
}
