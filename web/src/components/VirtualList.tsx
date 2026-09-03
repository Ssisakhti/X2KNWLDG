/**
 * A windowed list: only the visible rows exist in the DOM.
 *
 * Canvas plan §13.1 requires long transcripts to be virtualized, and a real
 * run's `transcript.json` holds hundreds to thousands of captions. Rows are
 * *measured* rather than assumed to be a fixed height, because a caption wraps
 * to a different number of lines depending on its text and the UI language,
 * and a fixed-height window would either clip Persian text or leave gaps.
 *
 * Measurement is the only reason this is more than twenty lines: each rendered
 * row reports its height, the prefix sums are recomputed, and rows that have
 * never been on screen keep the estimate until they are. A layoutless
 * environment (jsdom, and therefore the tests) reports zero heights, so the
 * estimate is what holds there -- which is why the tests assert *which rows
 * render*, not where they sit.
 *
 * That blind spot hid D-080 for a release: with `offsetHeight` always `0`,
 * `measure` never bumped `version`, so no test could observe what happened
 * when it did. The tests that cover the scroll request now stub `offsetHeight`
 * to drive real measurement rather than working around its absence.
 */

import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";

export interface VirtualListProps<T> {
  items: readonly T[];
  renderItem: (item: T, index: number) => ReactNode;
  itemKey: (item: T, index: number) => string;
  /** Starting height for a row that has never been measured. */
  estimateHeight: number;
  /** Rows rendered beyond each edge of the viewport. */
  overscan?: number;
  /** CSS block size of the scroll container. */
  blockSize?: string;
  /** Scroll this row into view when it changes. */
  scrollToIndex?: number | null;
  label?: string;
}

function prefixSums(heights: readonly number[]): number[] {
  const offsets = new Array<number>(heights.length + 1);
  offsets[0] = 0;
  for (let index = 0; index < heights.length; index += 1) {
    offsets[index + 1] = (offsets[index] ?? 0) + (heights[index] ?? 0);
  }
  return offsets;
}

function findIndex(offsets: readonly number[], position: number): number {
  let low = 0;
  let high = offsets.length - 1;
  while (low < high) {
    const middle = (low + high) >> 1;
    if ((offsets[middle + 1] ?? 0) <= position) low = middle + 1;
    else high = middle;
  }
  return low;
}

export function VirtualList<T>({
  items,
  renderItem,
  itemKey,
  estimateHeight,
  overscan = 6,
  blockSize = "60vh",
  scrollToIndex = null,
  label,
}: VirtualListProps<T>) {
  const container = useRef<HTMLDivElement | null>(null);
  const measured = useRef<number[]>([]);
  const [version, setVersion] = useState(0);
  const [scrollTop, setScrollTop] = useState(0);
  const [viewport, setViewport] = useState(600);

  // D-094: the rebuild was keyed on `items.length` alone, so a changed
  // `estimateHeight` was ignored for the life of the list -- five rows at 44px
  // re-rendered as five rows at 99px kept a 220px runway instead of 495px,
  // because every entry was already filled in at the old estimate and no
  // length had changed. The estimate is part of what the array *is*, so it is
  // part of what decides whether the array is still valid. Measured rows are
  // still carried over: a real height beats any estimate, old or new.
  const estimatedAt = useRef(estimateHeight);
  if (measured.current.length !== items.length || estimatedAt.current !== estimateHeight) {
    const previousEstimate = estimatedAt.current;
    const next = new Array<number>(items.length);
    for (let index = 0; index < items.length; index += 1) {
      const stored = measured.current[index];
      // An entry still sitting at the *old* estimate was never measured, so it
      // takes the new one.
      next[index] = stored === undefined || stored === previousEstimate ? estimateHeight : stored;
    }
    measured.current = next;
    estimatedAt.current = estimateHeight;
  }

  const offsets = useMemo(
    () => prefixSums(measured.current),
    // `version` is bumped whenever a measurement changes a row's height.
    // `items` by identity rather than by length, and `estimateHeight`, because
    // the rebuild above reacts to both and the sums have to be re-read after it
    // (D-094) — with `items.length` alone, a new estimate rebuilt the array and
    // this memo went on returning the previous prefix sums.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [version, items, estimateHeight],
  );

  const total = offsets[offsets.length - 1] ?? 0;
  const first = Math.max(0, findIndex(offsets, scrollTop) - overscan);
  const last = Math.min(items.length, findIndex(offsets, scrollTop + viewport) + 1 + overscan);
  const windowStart = offsets[first] ?? 0;

  useLayoutEffect(() => {
    const element = container.current;
    if (element === null) return;
    const update = () => setViewport(element.clientHeight || 600);
    update();
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(update);
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  /**
   * D-080: `scrollToIndex` is a *request*, and answering it takes more than one
   * pass — `offsets[scrollToIndex]` is only an estimate until the rows above
   * the target have been on screen and measured, so the position has to be
   * re-applied as measurements land. That is why the effect below depends on
   * `offsets`.
   *
   * What it must not do is keep re-applying for the life of the list. `offsets`
   * is a `useMemo` keyed on `version`, and `measure` bumps `version` on every
   * row whose height changes, so the effect re-fired and forced `scrollTop`
   * back each time — a user who scrolled away from a deep-linked caption was
   * dragged back to it, repeatedly. `pending` holds the request until the
   * reader scrolls somewhere we did not put them, and `enforced` is how their
   * scroll is told apart from the event our own assignment provokes.
   */
  const pending = useRef<number | null>(scrollToIndex);
  const enforced = useRef<number | null>(null);

  useEffect(() => {
    pending.current = scrollToIndex;
    enforced.current = null;
  }, [scrollToIndex]);

  useEffect(() => {
    const target = pending.current;
    if (target === null || container.current === null) return;
    if (target < 0 || target >= items.length) return;
    const top = offsets[target] ?? 0;
    enforced.current = top;
    container.current.scrollTop = top;
    setScrollTop(top);
  }, [scrollToIndex, offsets, items.length]);

  const handleScroll = useCallback((top: number) => {
    setScrollTop(top);
    if (pending.current === null) return;
    if (enforced.current !== null && Math.abs(top - enforced.current) <= 1) return;
    // Somewhere we did not put them. The request is answered; stop enforcing it.
    pending.current = null;
    enforced.current = null;
  }, []);

  const measure = useCallback((index: number, element: HTMLDivElement | null) => {
    if (element === null) return;
    const height = element.offsetHeight;
    if (height > 0 && Math.abs((measured.current[index] ?? 0) - height) > 0.5) {
      measured.current[index] = height;
      setVersion((value) => value + 1);
    }
  }, []);

  /*
   * The list contract lives here, and it did not (D-203).
   *
   * Two things were wrong, and both are about a windowed list telling the
   * truth about a collection it only partly holds:
   *
   * 1. **Three generic elements stood between `role="list"` and each
   *    `role="listitem"`** — the runway, the window and this per-row wrapper.
   *    Several screen readers resolve that by dropping the items out of the
   *    list entirely, so a transcript announced as a list with nothing in it.
   *    `role="presentation"` on the intervening generics takes them out of the
   *    accessibility tree instead, which makes the items the list's own
   *    children again.
   * 2. **Only the windowed rows existed, with no `aria-setsize`.** A
   *    1,200-caption transcript announced as "list, 20 items" while the
   *    paragraph above it said 1,200. `aria-setsize` is the whole collection
   *    and `aria-posinset` is where this row sits in it, which is exactly the
   *    pair ARIA defines for a set the DOM does not hold all of.
   *
   * The `listitem` role is on this wrapper rather than on whatever
   * `renderItem` returns, because the position in the set is this component's
   * fact and not the row's — the caller does not know it is being windowed.
   */
  const rows: ReactNode[] = [];
  for (let index = first; index < last; index += 1) {
    const item = items[index];
    if (item === undefined) continue;
    rows.push(
      <div
        key={itemKey(item, index)}
        ref={(element) => measure(index, element)}
        role="listitem"
        aria-setsize={items.length}
        aria-posinset={index + 1}
      >
        {renderItem(item, index)}
      </div>,
    );
  }

  return (
    <div
      className="virtual"
      ref={container}
      style={{ blockSize }}
      onScroll={(event) => handleScroll(event.currentTarget.scrollTop)}
      role="list"
      aria-label={label}
      data-virtual-size={items.length}
    >
      <div
        className="virtual__runway"
        style={{ blockSize: `${total}px` }}
        role="presentation"
      >
        <div
          className="virtual__window"
          style={{ transform: `translateY(${windowStart}px)` }}
          role="presentation"
        >
          {rows}
        </div>
      </div>
    </div>
  );
}
