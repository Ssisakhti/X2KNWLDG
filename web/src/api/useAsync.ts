/**
 * One request, four states, no invention.
 *
 * `idle` is not folded into `loading`, and `failed` is not folded into "no
 * data": a view that cannot tell a refusal from an empty answer will render
 * `503 index_unavailable` as an empty library, which is exactly the mistake
 * D-030 added that code to prevent.
 */

import { useCallback, useEffect, useRef, useState } from "react";

import { ApiFailure } from "./errors";

export type AsyncStatus = "idle" | "loading" | "ready" | "failed";

export interface AsyncState<T> {
  status: AsyncStatus;
  data: T | null;
  error: ApiFailure | null;
  reload: () => void;
}

export function useAsync<T>(
  run: (signal: AbortSignal) => Promise<T>,
  deps: readonly unknown[],
  options: { enabled?: boolean } = {},
): AsyncState<T> {
  const enabled = options.enabled ?? true;
  const [status, setStatus] = useState<AsyncStatus>(enabled ? "loading" : "idle");
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<ApiFailure | null>(null);
  const [nonce, setNonce] = useState(0);

  // `run` is usually a fresh closure on every render; the caller's `deps` are
  // the real identity of the request, so the latest closure is kept in a ref
  // and the effect keys off `deps` alone.
  const latest = useRef(run);
  latest.current = run;

  useEffect(() => {
    if (!enabled) {
      setStatus("idle");
      return;
    }
    const controller = new AbortController();
    let live = true;
    setStatus("loading");
    setError(null);
    latest
      .current(controller.signal)
      .then((value) => {
        if (!live) return;
        setData(value);
        setStatus("ready");
      })
      .catch((cause: unknown) => {
        if (!live || controller.signal.aborted) return;
        setData(null);
        setError(
          cause instanceof ApiFailure
            ? cause
            : new ApiFailure("internal", cause instanceof Error ? cause.message : String(cause)),
        );
        setStatus("failed");
      });
    return () => {
      live = false;
      controller.abort();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, nonce, ...deps]);

  const reload = useCallback(() => setNonce((value) => value + 1), []);

  return { status, data, error, reload };
}
