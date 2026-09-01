/**
 * Virtualization: a long transcript must not become a long DOM.
 *
 * jsdom performs no layout, so every measurement is zero and the estimate is
 * what the window is computed from. That is enough to assert the property that
 * matters -- the rendered row count is bounded by the viewport, not by the
 * item count -- without asserting pixel positions a layoutless environment
 * cannot produce.
 */

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
