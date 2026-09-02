/**
 * `T-208`: the whole journey exists without a pointer and without WebGL.
 *
 * This is the surface that makes that true. The counts beside the canvas say
 * how much the Map holds; these rows are *what* it holds, and each of them
 * carries the three things a mark on the canvas carries -- a preview, a
 * selection and a way into the Reader -- as real controls in the DOM.
 */

import { fireEvent, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { createMapGraph, nodeAttributes } from "../map/graphProjection";
import { MAP_OUTLINE_PAGE } from "../map/outline";
import type { MapPeekBinding } from "../map/useMapPeek";
import { concept, unit } from "../test/graphRecords";
import { renderApp } from "../test/render";
import { MapOutline } from "./MapOutline";

const KU1 = "youtube:pqlWNihgdjI:KU-000001";

function graphOf(count: number) {
  const graph = createMapGraph();
  for (let index = 1; index <= count; index += 1) {
    const record = unit(`KU-${String(index).padStart(6, "0")}`);
    graph.addNode(record.global_id, nodeAttributes(record));
  }
  return graph;
}

function peekSpy(): { binding: MapPeekBinding; opened: string[] } {
  const opened: string[] = [];
  const binding: MapPeekBinding = {
    peek: null,
    open: vi.fn(),
    close: vi.fn(),
    handlers: (globalId: string) => ({
      onMouseEnter: () => opened.push(`pointer:${globalId}`),
      onMouseLeave: () => undefined,
      onFocus: () => opened.push(`keyboard:${globalId}`),
      onBlur: () => undefined,
    }),
  };
  return { binding, opened };
}

function outline(): HTMLElement {
  const found = document.querySelector<HTMLElement>("[data-map-panel='outline']");
  if (found === null) throw new Error("the Map states nothing about what it holds");
  return found;
}

describe("the Map's outline", () => {
  it("lists what the Map has drawn, with each row's own drawn relations", () => {
    const graph = createMapGraph();
    const first = unit("KU-000001");
    const second = concept("C-000001");
    graph.addNode(first.global_id, nodeAttributes(first));
    graph.addNode(second.global_id, nodeAttributes(second));
    graph.addDirectedEdgeWithKey("e1", first.global_id, second.global_id, {
      record: {
        schema_version: "1.0",
        id: "e1",
        from_id: first.global_id,
        to_id: second.global_id,
        relation: "expresses_concept",
        relation_vocabulary: "library_synthetic",
        provenance_class: "derived",
        confidence: null,
        source_id: null,
        canonical_path: "output/library/graph.json",
      },
    });
    const { binding } = peekSpy();
    renderApp(
      <MapOutline graph={graph} revision={1} focus={null} onFocus={vi.fn()} peek={binding} preferOpen />,
    );

    expect(outline().dataset.mapOutline).toBe("2");
    expect(outline().dataset.mapOutlineLoaded).toBe("2");
    expect(document.querySelectorAll("[data-map-outline-edges]")).toHaveLength(2);
    expect(
      screen.getByText("A statement the transcript actually makes, numbered KU-000001."),
    ).toBeDefined();
    // Both rows: one edge is drawn, and it is drawn at each of its ends.
    expect(screen.getAllByText("1 relations drawn at this mark")).toHaveLength(2);
  });

  it("selects through the one selection identity, from a real button", () => {
    const focused: (string | null)[] = [];
    const { binding } = peekSpy();
    renderApp(
      <MapOutline
        graph={graphOf(1)}
        revision={1}
        focus={null}
        onFocus={(id) => focused.push(id)}
        peek={binding}
        preferOpen
      />,
    );
    const button = screen.getByRole("button", { name: "Focus" });
    fireEvent.click(button);
    expect(focused).toEqual([KU1]);
  });

  it("previews on keyboard focus, not on hover alone", () => {
    // The Peek is the information scent that makes a choice a choice (D-133).
    // A row that only previewed under a pointer would leave a keyboard reader
    // selecting nodes to find out whether selecting them was worth doing.
    const { binding, opened } = peekSpy();
    renderApp(
      <MapOutline graph={graphOf(1)} revision={1} focus={null} onFocus={vi.fn()} peek={binding} preferOpen />,
    );
    fireEvent.focus(screen.getByRole("button", { name: "Focus" }));
    expect(opened).toEqual([`keyboard:${KU1}`]);
  });

  it("marks the focused row rather than repeating the selection", () => {
    const { binding } = peekSpy();
    renderApp(
      <MapOutline graph={graphOf(1)} revision={1} focus={KU1} onFocus={vi.fn()} peek={binding} preferOpen />,
    );
    expect(screen.getByRole("button", { name: "Focused" }).getAttribute("aria-pressed")).toBe(
      "true",
    );
  });

  it("counts what its page does not list, and offers a control that lists it", () => {
    const { binding } = peekSpy();
    renderApp(
      <MapOutline
        graph={graphOf(MAP_OUTLINE_PAGE + 3)}
        revision={1}
        focus={null}
        onFocus={vi.fn()}
        peek={binding}
        preferOpen
      />,
    );
    expect(outline().dataset.mapOutline).toBe(String(MAP_OUTLINE_PAGE));
    expect(outline().dataset.mapOutlineUnlisted).toBe("3");
    fireEvent.click(screen.getByRole("button", { name: "List more nodes" }));
    expect(outline().dataset.mapOutline).toBe(String(MAP_OUTLINE_PAGE + 3));
    expect(outline().dataset.mapOutlineUnlisted).toBe("0");
    expect(document.querySelector("[data-map-outline-more]")).toBeNull();
  });

  it("says nothing is loaded rather than that nothing exists", () => {
    const { binding } = peekSpy();
    renderApp(
      <MapOutline graph={null} revision={0} focus={null} onFocus={vi.fn()} peek={binding} preferOpen />,
    );
    expect(
      screen.getByText("No node is loaded, so there is nothing to list.", { exact: false }),
    ).toBeDefined();
    expect(outline().dataset.mapOutlineLoaded).toBe("0");
  });

  it("opens itself when it is the only view of the graph", () => {
    const { binding } = peekSpy();
    const { rerender } = renderApp(
      <MapOutline graph={graphOf(2)} revision={1} focus={null} onFocus={vi.fn()} peek={binding} preferOpen={false} />,
    );
    expect(outline().dataset.mapPanelOpen).toBe("false");
    rerender(
      <MapOutline graph={graphOf(2)} revision={1} focus={null} onFocus={vi.fn()} peek={binding} preferOpen />,
    );
    expect(outline().dataset.mapPanelOpen).toBe("true");
  });
});
