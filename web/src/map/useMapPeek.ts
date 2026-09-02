/**
 * Peek: one transient card, and no history at all (`T-206`, D-133).
 *
 * ADR 0005 invariant 14 is two statements, and this module is the second one.
 * A hover or a keyboard focus over a loaded node shows what that node says --
 * enough information scent to decide whether to open it -- and changes nothing
 * else. It writes no URL entry, no selection, and nothing a reload would
 * restore. That is why it is a separate module from `useMapFocus` rather than
 * a flag inside it: the two cannot be confused if they do not share a code
 * path, and a `navigate` call in this file would be visible as one.
 *
 * The back stack is the reason. Hover-driven history is unusable noise: a
 * pointer crossing eight nodes on its way to the ninth would leave eight
 * entries the user never chose, and Back would walk a path the mouse took
 * rather than the one the reader did.
 *
 * **At most one Peek exists** (invariant 13). Not "at most one per component",
 * and not "one that fades while the next appears": the state is a single
 * value, so a second `open` replaces the first structurally. Nothing here
 * counts cards, because nothing can create a second one.
 *
 * **Only a loaded node can be peeked.** The record is read from the graph the
 * Map has actually accumulated, through the injected `lookup`. A node with no
 * record loaded produces no Peek -- an empty card, or one showing only an id,
 * is the blind choice D-130 exists to remove, and filling it in from anywhere
 * else would be client-authored knowledge (D-131).
 *
 * **A stale leave must not close a newer Peek.** `close(globalId)` closes only
 * if that node is the one being peeked. Pointers generate `leave` for the node
 * they left *after* `enter` for the node they arrived at, so an unconditional
 * close would blank the card the user is actually reading.
 */

import { useCallback, useMemo, useRef, useState } from "react";
import type { FocusEvent } from "react";

import type { EntityRef } from "../api/contract";

/** Where the Peek came from. Recorded so a view can behave differently, not to filter. */
export type PeekOrigin = "pointer" | "keyboard";

export interface MapPeekState {
  globalId: string;
  /** The record the Map has loaded for that node, verbatim. */
  record: EntityRef;
  origin: PeekOrigin;
}

/** The DOM handlers a row or a card spreads to become peekable by both input paths. */
export interface PeekHandlers {
  onMouseEnter: () => void;
  onMouseLeave: () => void;
  onFocus: () => void;
  onBlur: (event: FocusEvent<HTMLElement>) => void;
}

export interface MapPeekBinding {
  /** The one Peek, or `null`. */
  peek: MapPeekState | null;
  /** Open a Peek over a loaded node. A node with no loaded record opens none. */
  open: (globalId: string, origin?: PeekOrigin) => void;
  /** Close the Peek. With an id, only if that node is the one being peeked. */
  close: (globalId?: string) => void;
  /** Pointer *and* keyboard, wired to the same node, from one call. */
  handlers: (globalId: string) => PeekHandlers;
}

/**
 * @param lookup the loaded record for a `global_id`, or `null` when the Map
 * has not loaded that node. `recordLookup` in `useMapSearch` builds one over
 * the accumulated graph.
 */
export function useMapPeek(lookup: (globalId: string) => EntityRef | null): MapPeekBinding {
  const [peek, setPeek] = useState<MapPeekState | null>(null);

  // `lookup` is a fresh closure whenever the graph changes; the latest one is
  // kept in a ref so the handlers below stay stable and a row does not
  // re-render on every accumulated page.
  const latest = useRef(lookup);
  latest.current = lookup;

  const open = useCallback((globalId: string, origin: PeekOrigin = "pointer") => {
    const record = latest.current(globalId);
    if (record === null) {
      // Nothing loaded to show. Leaving the previous Peek up would attribute
      // one node's statement to another, so it closes instead.
      setPeek(null);
      return;
    }
    setPeek({ globalId, record, origin });
  }, []);

  const close = useCallback((globalId?: string) => {
    setPeek((current) => {
      if (current === null) return null;
      if (globalId !== undefined && current.globalId !== globalId) return current;
      return null;
    });
  }, []);

  const handlers = useCallback(
    (globalId: string): PeekHandlers => ({
      onMouseEnter: () => open(globalId, "pointer"),
      onMouseLeave: () => close(globalId),
      onFocus: () => open(globalId, "keyboard"),
      // D-181: this was `() => close(globalId)`, so the very Tab that would
      // move focus *toward* the card unmounted it first. The card's own
      // "Close the peek" button existed in the DOM only while some other
      // element held focus, which made it unreachable from the keyboard --
      // the pointer path was fine and Escape worked, so nothing else showed
      // it. Focus moving into the card is focus staying with this peek.
      onBlur: (event) => {
        const next = event.relatedTarget;
        if (next instanceof Element && next.closest("[data-map-peek]") !== null) return;
        close(globalId);
      },
    }),
    [open, close],
  );

  return useMemo(() => ({ peek, open, close, handlers }), [peek, open, close, handlers]);
}
