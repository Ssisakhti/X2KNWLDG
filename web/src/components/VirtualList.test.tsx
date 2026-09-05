/**
 * Virtualization: a long transcript must not become a long DOM.
 *
 * jsdom performs no layout, so every measurement is zero and the estimate is
 * what the window is computed from. That is enough to assert the property that
 * matters -- the rendered row count is bounded by the viewport, not by the
 * item count -- without asserting pixel positions a layoutless environment
 * cannot produce.
 */

import { fireEvent } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { renderApp } from "../test/render";
import { VirtualList } from "./VirtualList";

const ITEMS = Array.from({ length: 2000 }, (_, index) => ({ id: `row-${index}` }));

describe("VirtualList", () => {
  it("renders a window rather than every row", () => {
    renderApp(
      <VirtualList
        items={ITEMS}
        estimateHeight={40}
        itemKey={(item) => item.id}
        renderItem={(item) => <span>{item.id}</span>}
        label="rows"
      />,
    );
    const rendered = document.querySelectorAll(".virtual__window > div");
    expect(rendered.length).toBeGreaterThan(0);
    expect(rendered.length).toBeLessThan(ITEMS.length / 10);
  });

  it("starts at the beginning of the collection", () => {
    renderApp(
      <VirtualList
        items={ITEMS}
        estimateHeight={40}
        itemKey={(item) => item.id}
        renderItem={(item) => <span>{item.id}</span>}
      />,
    );
    expect(document.body.textContent).toContain("row-0");
    expect(document.body.textContent).not.toContain("row-1999");
  });

  it("reserves the full scroll height so the scrollbar is honest", () => {
    renderApp(
      <VirtualList
        items={ITEMS}
        estimateHeight={40}
        itemKey={(item) => item.id}
        renderItem={(item) => <span>{item.id}</span>}
      />,
    );
    const runway = document.querySelector(".virtual__runway") as HTMLElement;
    expect(runway.style.blockSize).toBe(`${ITEMS.length * 40}px`);
  });

  it("renders nothing for an empty collection without failing", () => {
    renderApp(
      <VirtualList
        items={[]}
        estimateHeight={40}
        itemKey={() => "none"}
        renderItem={() => <span />}
      />,
    );
    expect(document.querySelectorAll(".virtual__window > div")).toHaveLength(0);
  });
});

/**
 * D-080 — a deep link must land once, not drag the reader back forever.
 *
 * `offsets` is a `useMemo` keyed on `version`, and `measure` bumps `version`
 * on every row whose height changes. The `scrollToIndex` effect depended on
 * `offsets`, so it re-fired on *every* measurement and forced `scrollTop`
 * back — for the life of the list. The module's own header comment named the
 * reason no test could see it: jsdom reports `offsetHeight === 0`, so
 * `measure` never bumped `version`.
 *
 * These tests stub `offsetHeight` to drive real measurement, which is what
 * closes that blind spot rather than working around it.
 */
describe("VirtualList scrollToIndex", () => {
  const ROWS = Array.from({ length: 300 }, (_, index) => ({ id: `row-${index}` }));

  /** Make every row report `height`, so `measure` bumps `version` for real. */
  function measuringRows(height: number): () => void {
    const original = Object.getOwnPropertyDescriptor(HTMLElement.prototype, "offsetHeight");
    Object.defineProperty(HTMLElement.prototype, "offsetHeight", {
      configurable: true,
      get() {
        return this.parentElement?.classList.contains("virtual__window") ? height : 0;
      },
    });
    return () => {
      if (original) Object.defineProperty(HTMLElement.prototype, "offsetHeight", original);
      else delete (HTMLElement.prototype as unknown as Record<string, unknown>).offsetHeight;
    };
  }

  function mount(scrollToIndex: number | null) {
    return renderApp(
      <VirtualList
        items={ROWS}
        estimateHeight={40}
        itemKey={(item) => item.id}
        renderItem={(item) => <span>{item.id}</span>}
        scrollToIndex={scrollToIndex}
        label="rows"
      />,
    );
  }

  it("measures rows in this suite, so the blind spot is actually closed", () => {
    const restore = measuringRows(99);
    try {
      mount(null);
      const runway = document.querySelector(".virtual__runway") as HTMLElement;
      // 300 * 40 = 12000 if nothing measured; measurement must move it.
      expect(runway.style.blockSize).not.toBe(`${ROWS.length * 40}px`);
    } finally {
      restore();
    }
  });

  /**
   * jsdom's `scrollTop` is a plain data property: it neither clamps to
   * `scrollHeight - clientHeight` nor fires a `scroll` event, which is exactly
   * why the defect below survived a suite that measures rows. This installs the
   * half of the browser that matters — a clamp, and the event a clamp provokes.
   */
  function clampingScroll(viewport: number): () => void {
    const proto = HTMLElement.prototype as unknown as Record<string, unknown>;
    const original = Object.getOwnPropertyDescriptor(HTMLElement.prototype, "scrollTop");
    const stored = new WeakMap<HTMLElement, number>();
    Object.defineProperty(HTMLElement.prototype, "scrollTop", {
      configurable: true,
      get(this: HTMLElement) {
        return stored.get(this) ?? 0;
      },
      set(this: HTMLElement, value: number) {
        const runway = this.querySelector(".virtual__runway") as HTMLElement | null;
        const height = runway === null ? 0 : Number.parseFloat(runway.style.blockSize) || 0;
        const clamped = Math.max(0, Math.min(value, height - viewport));
        stored.set(this, clamped);
        // A real browser reports the clamped value back, asynchronously.
        this.dispatchEvent(new Event("scroll"));
      },
    });
    return () => {
      if (original) Object.defineProperty(HTMLElement.prototype, "scrollTop", original);
      else delete proto.scrollTop;
    };
  }

  it("reaches a row near the end even though the browser clamps the first try", () => {
    /*
     * D-080 re-applies the position as rows are measured, because
     * `offsets[target]` under-estimates until the rows above the target have
     * been on screen. The re-application was retired on the *first* attempt:
     * `enforced` held the value we asked for, the browser stored the clamped
     * one and fired `scroll` with it, and `handleScroll` read the difference as
     * the reader scrolling away. A deep link to a late caption landed short and
     * stayed there.
     */
    const restoreRows = measuringRows(120);
    const restoreScroll = clampingScroll(600);
    try {
      mount(ROWS.length - 1);
      const container = document.querySelector(".virtual") as HTMLElement;
      const runway = document.querySelector(".virtual__runway") as HTMLElement;
      const honest = Number.parseFloat(runway.style.blockSize) - 600;
      // Within one row of the true bottom, rather than at the 40px-estimate
      // position the first clamped attempt would have left it at.
      expect(container.scrollTop).toBeGreaterThan(honest - 120);
    } finally {
      restoreScroll();
      restoreRows();
    }
  });

  it("scrolls to the linked row", () => {
    const restore = measuringRows(50);
    try {
      mount(100);
      const container = document.querySelector(".virtual") as HTMLElement;
      expect(container.scrollTop).toBeGreaterThan(0);
    } finally {
      restore();
    }
  });

  it("does not drag the reader back after they scroll away", () => {
    const restore = measuringRows(50);
    try {
      mount(100);
      const container = document.querySelector(".virtual") as HTMLElement;
      const landed = container.scrollTop;
      expect(landed).toBeGreaterThan(0);

      // The reader scrolls somewhere else, then more rows report their heights
      // as they come into view — which is what used to re-fire the effect.
      const moved = landed + 2500;
      fireEvent.scroll(container, { target: { scrollTop: moved } });
      fireEvent.scroll(container, { target: { scrollTop: moved + 400 } });

      expect(container.scrollTop).toBe(moved + 400);
      expect(container.scrollTop).not.toBe(landed);
    } finally {
      restore();
    }
  });

  it("honours a new link after the reader has scrolled away", () => {
    const restore = measuringRows(50);
    try {
      const { rerender } = mount(100);
      const container = document.querySelector(".virtual") as HTMLElement;
      fireEvent.scroll(container, { target: { scrollTop: 9000 } });
      expect(container.scrollTop).toBe(9000);

      rerender(
        <VirtualList
          items={ROWS}
          estimateHeight={40}
          itemKey={(item) => item.id}
          renderItem={(item) => <span>{item.id}</span>}
          scrollToIndex={20}
          label="rows"
        />,
      );
      expect(container.scrollTop).not.toBe(9000);
    } finally {
      restore();
    }
  });

  it("leaves the position alone when there is no link", () => {
    const restore = measuringRows(50);
    try {
      mount(null);
      const container = document.querySelector(".virtual") as HTMLElement;
      fireEvent.scroll(container, { target: { scrollTop: 1234 } });
      expect(container.scrollTop).toBe(1234);
    } finally {
      restore();
    }
  });

  it("ignores an out-of-range index rather than inventing a position", () => {
    const restore = measuringRows(50);
    try {
      mount(ROWS.length + 500);
      const container = document.querySelector(".virtual") as HTMLElement;
      expect(container.scrollTop).toBe(0);
    } finally {
      restore();
    }
  });
});

/**
 * D-094 — a changed `estimateHeight` must change the runway.
 *
 * The measured-heights array was rebuilt only when `items.length` changed, so
 * a new estimate was ignored for the life of the list: five rows at 44px
 * re-rendered as five rows at 99px kept a 220px runway instead of 495px,
 * because every entry was already filled in at the old estimate and no length
 * had changed. In-app trigger: navigating between two transcripts with equal
 * caption counts.
 */
describe("VirtualList estimateHeight", () => {
  const FIVE = Array.from({ length: 5 }, (_, index) => ({ id: `row-${index}` }));

  function runway(): string {
    return (document.querySelector(".virtual__runway") as HTMLElement).style.blockSize;
  }

  function list(estimateHeight: number, items: readonly { id: string }[] = FIVE) {
    return (
      <VirtualList
        items={items}
        estimateHeight={estimateHeight}
        itemKey={(item) => item.id}
        renderItem={(item) => <span>{item.id}</span>}
        label="rows"
      />
    );
  }

  it("reserves the height the estimate asks for", () => {
    renderApp(list(44));
    expect(runway()).toBe("220px");
  });

  it("re-reserves when the estimate changes and the length does not", () => {
    const { rerender } = renderApp(list(44));
    expect(runway()).toBe("220px");
    rerender(list(99));
    expect(runway()).toBe("495px");
  });

  it("re-reserves for a different list of the same length", () => {
    const other = Array.from({ length: 5 }, (_, index) => ({ id: `other-${index}` }));
    const { rerender } = renderApp(list(44));
    rerender(list(99, other));
    expect(runway()).toBe("495px");
  });

  it("keeps a measured height in preference to either estimate", () => {
    const original = Object.getOwnPropertyDescriptor(HTMLElement.prototype, "offsetHeight");
    Object.defineProperty(HTMLElement.prototype, "offsetHeight", {
      configurable: true,
      get() {
        return this.parentElement?.classList.contains("virtual__window") ? 70 : 0;
      },
    });
    try {
      const { rerender } = renderApp(list(44));
      const measured = runway();
      // All five rows are on screen and measured at 70px, not 44px.
      expect(measured).toBe("350px");
      rerender(list(99));
      expect(runway()).toBe(measured);
    } finally {
      if (original) Object.defineProperty(HTMLElement.prototype, "offsetHeight", original);
      else delete (HTMLElement.prototype as unknown as Record<string, unknown>).offsetHeight;
    }
  });
});

describe("what a windowed list announces about the collection", () => {
  /*
   * D-203: three generic elements stood between `role="list"` and each
   * `role="listitem"` — the runway, the window and the per-row wrapper —
   * which several screen readers resolve by dropping the items out of the
   * list entirely. And only the windowed rows existed with no
   * `aria-setsize`, so a 1,200-caption transcript announced as "list, 20
   * items" while the paragraph above it said 1,200.
   */
  it("puts nothing between the list and its items", () => {
    renderApp(
      <VirtualList
        items={ITEMS}
        estimateHeight={40}
        itemKey={(item) => item.id}
        renderItem={(item) => <span>{item.id}</span>}
        label="rows"
      />,
    );

    const list = document.querySelector<HTMLElement>("[role='list']");
    if (list === null) throw new Error("the list has no role");
    for (const generic of list.querySelectorAll<HTMLElement>(
      ".virtual__runway, .virtual__window",
    )) {
      expect(generic.getAttribute("role")).toBe("presentation");
    }

    const items = [...list.querySelectorAll<HTMLElement>("[role='listitem']")];
    expect(items.length).toBeGreaterThan(0);
    // Every item's path back to the list crosses only presentational nodes.
    for (const item of items) {
      let node = item.parentElement;
      while (node !== null && node !== list) {
        expect(node.getAttribute("role")).toBe("presentation");
        node = node.parentElement;
      }
      expect(node).toBe(list);
    }
  });

  it("states the size of the collection, not the size of the window", () => {
    renderApp(
      <VirtualList
        items={ITEMS}
        estimateHeight={40}
        itemKey={(item) => item.id}
        renderItem={(item) => <span>{item.id}</span>}
        label="rows"
      />,
    );

    const items = [...document.querySelectorAll<HTMLElement>("[role='listitem']")];
    expect(items.length).toBeLessThan(ITEMS.length);
    for (const item of items) {
      expect(item.getAttribute("aria-setsize")).toBe(String(ITEMS.length));
    }
    // And each row says where it sits in that collection.
    expect(items[0]?.getAttribute("aria-posinset")).toBe("1");
    const positions = items.map((item) => Number(item.getAttribute("aria-posinset")));
    expect(positions).toEqual(positions.map((_, index) => positions[0]! + index));
  });
});
