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

  if (measured.current.length !== items.length) {
    const next = new Array<number>(items.length);
    for (let index = 0; index < items.length; index += 1) {
      next[index] = measured.current[index] ?? estimateHeight;
    }
    measured.current = next;
  }

  const offsets = useMemo(
    () => prefixSums(measured.current),
    // `version` is bumped whenever a measurement changes a row's height.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [version, items.length],
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

  useEffect(() => {
    if (scrollToIndex === null || container.current === null) return;
    if (scrollToIndex < 0 || scrollToIndex >= items.length) return;
    container.current.scrollTop = offsets[scrollToIndex] ?? 0;
    setScrollTop(offsets[scrollToIndex] ?? 0);
  }, [scrollToIndex, offsets, items.length]);

  const measure = useCallback((index: number, element: HTMLDivElement | null) => {
    if (element === null) return;
    const height = element.offsetHeight;
    if (height > 0 && Math.abs((measured.current[index] ?? 0) - height) > 0.5) {
      measured.current[index] = height;
      setVersion((value) => value + 1);
    }
  }, []);

  const rows: ReactNode[] = [];
  for (let index = first; index < last; index += 1) {
    const item = items[index];
    if (item === undefined) continue;
    rows.push(
      <div key={itemKey(item, index)} ref={(element) => measure(index, element)}>
        {renderItem(item, index)}
      </div>,
    );
  }

  return (
    <div
      className="virtual"
      ref={container}
      style={{ blockSize }}
      onScroll={(event) => setScrollTop(event.currentTarget.scrollTop)}
      role="list"
      aria-label={label}
    >
      <div className="virtual__runway" style={{ blockSize: `${total}px` }}>
        <div className="virtual__window" style={{ transform: `translateY(${windowStart}px)` }}>
          {rows}
        </div>
      </div>
    </div>
  );
}
