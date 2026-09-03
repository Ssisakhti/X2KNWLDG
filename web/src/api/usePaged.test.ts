/**
 * D-079 — a stale page must not append onto the query that replaced it.
 *
 * `usePaged`'s effect aborted only its own controller. `loadMore` created a
 * controller nobody ever aborted, and its `.then` had no liveness check, so
 * switching query while a "More" page was in flight let the stale page append
 * onto the new query's items *and* overwrite `next` with the old query's
 * cursor. The next "More" then paginated a collection the header no longer
 * named — silently, with no error and no way for the reader to tell.
 *
 * These tests drive the interleaving directly with deferred promises, because
 * the defect only exists in the order things settle.
 */

import { act, renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { usePaged, type Page } from "./usePaged";

interface Deferred<T> {
  promise: Promise<T>;
  resolve: (value: T) => void;
  reject: (cause: unknown) => void;
}

function defer<T>(): Deferred<T> {
  let resolve!: (value: T) => void;
  let reject!: (cause: unknown) => void;
  const promise = new Promise<T>((settle, fail) => {
    resolve = settle;
    reject = fail;
  });
  return { promise, resolve, reject };
}

function page(items: string[], next: string | null, total: number | null = null): Page<string> {
  return { items, next, total };
}

/**
 * A loader whose every call is captured, so a test can settle calls in any
 * order and see exactly which query each one belonged to.
 */
function recordingLoader() {
  const calls: {
    query: string;
    cursor: string | undefined;
    signal: AbortSignal;
    deferred: Deferred<Page<string>>;
  }[] = [];
  const load = (query: string) => (cursor: string | undefined, signal: AbortSignal) => {
    const deferred = defer<Page<string>>();
    calls.push({ query, cursor, signal, deferred });
    return deferred.promise;
  };
  const of = (query: string, cursor: string | undefined) =>
    calls.filter((call) => call.query === query && call.cursor === cursor);
  return { calls, load, of };
}

describe("usePaged", () => {
  it("pages a single query normally", async () => {
    const loader = recordingLoader();
    const { result } = renderHook(
      ({ query }: { query: string }) => usePaged(loader.load(query), [query]),
      { initialProps: { query: "a" } },
    );

    await act(async () => loader.of("a", undefined)[0]!.deferred.resolve(page(["A1", "A2"], "cur-a2")));
    expect(result.current.items).toEqual(["A1", "A2"]);
    expect(result.current.hasMore).toBe(true);

    act(() => result.current.loadMore());
    await act(async () => loader.of("a", "cur-a2")[0]!.deferred.resolve(page(["A3"], null)));
    expect(result.current.items).toEqual(["A1", "A2", "A3"]);
    expect(result.current.hasMore).toBe(false);
    expect(result.current.loadingMore).toBe(false);
  });

  it("drops a stale page instead of appending it onto the new query", async () => {
    const loader = recordingLoader();
    const { result, rerender } = renderHook(
      ({ query }: { query: string }) => usePaged(loader.load(query), [query]),
      { initialProps: { query: "a" } },
    );

    await act(async () => loader.of("a", undefined)[0]!.deferred.resolve(page(["A1", "A2"], "cur-a2")));
    // "More" on query "a" goes out and does not come back yet.
    act(() => result.current.loadMore());
    expect(loader.of("a", "cur-a2")).toHaveLength(1);

    // The query changes under it and its first page lands.
    rerender({ query: "b" });
    await act(async () => loader.of("b", undefined)[0]!.deferred.resolve(page(["B1", "B2"], "cur-b2")));
    expect(result.current.items).toEqual(["B1", "B2"]);

    // Now the stale page for "a" settles.
    await act(async () => loader.of("a", "cur-a2")[0]!.deferred.resolve(page(["A3", "A4"], "cur-a4")));

    expect(result.current.items).toEqual(["B1", "B2"]);
    expect(result.current.error).toBeNull();
    expect(result.current.loadingMore).toBe(false);

    // And the cursor was not hijacked: the next "More" must page "b".
    act(() => result.current.loadMore());
    expect(loader.of("b", "cur-b2")).toHaveLength(1);
    expect(loader.of("b", "cur-a4")).toHaveLength(0);
  });

  it("aborts a page still in flight when the query changes", async () => {
    const loader = recordingLoader();
    const { result, rerender } = renderHook(
      ({ query }: { query: string }) => usePaged(loader.load(query), [query]),
      { initialProps: { query: "a" } },
    );
    await act(async () => loader.of("a", undefined)[0]!.deferred.resolve(page(["A1"], "cur-a1")));
    act(() => result.current.loadMore());
    const stale = loader.of("a", "cur-a1")[0]!;
    expect(stale.signal.aborted).toBe(false);

    rerender({ query: "b" });
    expect(stale.signal.aborted).toBe(true);
  });

  it("clears the More spinner when the query changes under it", async () => {
    const loader = recordingLoader();
    const { result, rerender } = renderHook(
      ({ query }: { query: string }) => usePaged(loader.load(query), [query]),
      { initialProps: { query: "a" } },
    );
    await act(async () => loader.of("a", undefined)[0]!.deferred.resolve(page(["A1"], "cur-a1")));
    act(() => result.current.loadMore());
    expect(result.current.loadingMore).toBe(true);

    rerender({ query: "b" });
    await act(async () => loader.of("b", undefined)[0]!.deferred.resolve(page(["B1"], null)));
    expect(result.current.loadingMore).toBe(false);
  });

  it("does not report a stale page's failure against the new query", async () => {
    const loader = recordingLoader();
    const { result, rerender } = renderHook(
      ({ query }: { query: string }) => usePaged(loader.load(query), [query]),
      { initialProps: { query: "a" } },
    );
    await act(async () => loader.of("a", undefined)[0]!.deferred.resolve(page(["A1"], "cur-a1")));
    act(() => result.current.loadMore());

    rerender({ query: "b" });
    await act(async () => loader.of("b", undefined)[0]!.deferred.resolve(page(["B1"], null)));
    await act(async () => {
      loader.of("a", "cur-a1")[0]!.deferred.reject(new Error("stale query failed"));
      await Promise.resolve();
    });

    expect(result.current.error).toBeNull();
    expect(result.current.status).toBe("ready");
    expect(result.current.items).toEqual(["B1"]);
  });

  it("does not touch state after unmount", async () => {
    const loader = recordingLoader();
    const { result, unmount } = renderHook(
      ({ query }: { query: string }) => usePaged(loader.load(query), [query]),
      { initialProps: { query: "a" } },
    );
    await act(async () => loader.of("a", undefined)[0]!.deferred.resolve(page(["A1"], "cur-a1")));
    act(() => result.current.loadMore());
    const inFlight = loader.of("a", "cur-a1")[0]!;

    unmount();
    expect(inFlight.signal.aborted).toBe(true);
    // The `.finally` used to `setLoadingMore(false)` unconditionally here.
    await act(async () => inFlight.deferred.resolve(page(["A2"], "cur-a2")));
  });

  it("reports a failed later page without destroying the pages already loaded", async () => {
    /*
     * `loadMore`'s catch set the same `error` the *first* page's failure sets,
     * and all four call sites branch on that field before rendering items — so
     * one transient hiccup on "More" replaced fifty loaded records with an
     * error panel, and the only way back discarded every page already
     * fetched. The two facts are separate fields now: `error` means "there is
     * nothing to show", `moreError` means "there is a gap at the end".
     */
    const loader = recordingLoader();
    const { result } = renderHook(
      ({ query }: { query: string }) => usePaged(loader.load(query), [query]),
      { initialProps: { query: "a" } },
    );
    await act(async () => loader.of("a", undefined)[0]!.deferred.resolve(page(["A1"], "cur-a1")));
    expect(result.current.items).toEqual(["A1"]);

    act(() => result.current.loadMore());
    await act(async () => {
      loader.of("a", "cur-a1")[0]!.deferred.reject(new Error("the server said no"));
      await Promise.resolve();
    });

    expect(result.current.moreError?.message).toContain("the server said no");
    expect(result.current.error).toBeNull();
    expect(result.current.items).toEqual(["A1"]);
    // And the cursor is still there, so the reader can try the same page again.
    expect(result.current.hasMore).toBe(true);
    expect(result.current.loadingMore).toBe(false);
  });

  it("clears a failed page when another is asked for", async () => {
    const loader = recordingLoader();
    const { result } = renderHook(
      ({ query }: { query: string }) => usePaged(loader.load(query), [query]),
      { initialProps: { query: "a" } },
    );
    await act(async () => loader.of("a", undefined)[0]!.deferred.resolve(page(["A1"], "cur-a1")));
    act(() => result.current.loadMore());
    await act(async () => {
      loader.of("a", "cur-a1")[0]!.deferred.reject(new Error("the server said no"));
      await Promise.resolve();
    });
    expect(result.current.moreError).not.toBeNull();

    act(() => result.current.loadMore());
    expect(result.current.moreError).toBeNull();
    await act(async () =>
      loader.of("a", "cur-a1")[1]!.deferred.resolve(page(["A2"], null)),
    );
    expect(result.current.items).toEqual(["A1", "A2"]);
    expect(result.current.moreError).toBeNull();
  });

  it("still reports a failed first page as the reason there is nothing to show", async () => {
    const loader = recordingLoader();
    const { result } = renderHook(
      ({ query }: { query: string }) => usePaged(loader.load(query), [query]),
      { initialProps: { query: "a" } },
    );
    await act(async () => {
      loader.of("a", undefined)[0]!.deferred.reject(new Error("the server said no"));
      await Promise.resolve();
    });
    expect(result.current.error?.message).toContain("the server said no");
    expect(result.current.moreError).toBeNull();
    expect(result.current.items).toEqual([]);
  });
});
