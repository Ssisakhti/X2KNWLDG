/**
 * Three filters, and no fourth (`T-205`).
 *
 * ADR 0005 invariant 7 is what these tests exist for: a control the Map
 * presents as server-backed must exist in the frozen operation's query type.
 * The interesting assertion is therefore a *negative* one -- that there is no
 * `kind` control -- because `kind` is the filter a knowledge graph most
 * obviously wants and the one `GET /api/graph` does not accept. A browser-side
 * `kind` filter would show a page the server never produced as though it had.
 *
 * The rest is about the value this component emits, since that value is what
 * `useGraphWalk`'s `deps` turn into a new question: an unset control must
 * contribute no key at all, or "filtered by nothing" and "filtered by
 * undefined" become two different snapshots of the same graph.
 */

import { fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Source } from "../api/contract";
import type { GraphFilters } from "../map/graphSnapshot";
import { jsonFetch, renderApp } from "../test/render";
import { MapFilters, graphFilters } from "./MapFilters";

const VIDEO = "youtube:pqlWNihgdjI";

function source(id: string, title: string | null): Source {
  return {
    schema_version: "1.0",
    id,
    source_type: "youtube",
    external_id: id.split(":")[1],
    title,
    canonical_dir: `output/${id}`,
    adapter: { name: "youtube", version: "1.0" },
    status: { validation: "PASS", coverage: "PASS", overall: "PASS" },
    counts: { knowledge_units: 69, relationships: 56 },
  } as Source;
}

function sourceList(sources: Source[], nextCursor: string | null = null) {
  return {
    api_version: "v1",
    schema_version: "1.0",
    data: sources,
    page: { limit: 200, next_cursor: nextCursor, total: sources.length },
  };
}

function refusal(code: string) {
  return { error: { code, message: "The index has not been built." } };
}

afterEach(() => vi.unstubAllGlobals());

function filterNames(): string[] {
  return Array.from(document.querySelectorAll<HTMLElement>("[data-map-filter]")).map(
    (element) => element.dataset.mapFilter ?? "",
  );
}

describe("the Map's filters", () => {
  it("offers exactly the three the graph endpoint accepts", async () => {
    vi.stubGlobal("fetch", jsonFetch(() => ({ body: sourceList([source(VIDEO, "A video")]) })));
    renderApp(<MapFilters value={{}} onChange={() => {}} />);

    await waitFor(() => expect(screen.getByRole("option", { name: "A video" })).toBeDefined());
    expect(filterNames()).toEqual(["source_id", "provenance_class", "relation_vocabulary"]);
    // The one that is deliberately absent. `GET /api/graph` has no `kind`
    // parameter, so offering one would be fiction either way it was built.
    expect(filterNames()).not.toContain("kind");
  });

  it("emits only the filters that are set", () => {
    // "Filtered by nothing" is an empty object, not an object of undefineds:
    // `Object.keys` is how a view states what a snapshot is filtered by.
    expect(graphFilters("", "", "")).toEqual({});
    expect(Object.keys(graphFilters("", "derived", ""))).toEqual(["provenance_class"]);
    expect(graphFilters(VIDEO, "source", "canonical")).toEqual({
      source_id: VIDEO,
      provenance_class: "source",
      relation_vocabulary: "canonical",
    });
  });

  it("hands a filter change up as a whole new filter value", () => {
    vi.stubGlobal("fetch", jsonFetch(() => ({ body: sourceList([]) })));
    const changes: GraphFilters[] = [];
    renderApp(<MapFilters value={{}} onChange={(next) => changes.push(next)} />);

    fireEvent.change(document.querySelector('[data-map-filter="provenance_class"]') as HTMLElement, {
      target: { value: "derived" },
    });
    expect(changes.at(-1)).toEqual({ provenance_class: "derived" });

    fireEvent.change(
      document.querySelector('[data-map-filter="relation_vocabulary"]') as HTMLElement,
      { target: { value: "library_synthetic" } },
    );
    // The value prop is still `{}` -- the parent owns the state -- so what
    // arrives is the new control's value and nothing invented around it.
    expect(changes.at(-1)).toEqual({ relation_vocabulary: "library_synthetic" });
  });

  it("keeps the filters that were already set when one of them changes", () => {
    vi.stubGlobal("fetch", jsonFetch(() => ({ body: sourceList([]) })));
    const changes: GraphFilters[] = [];
    renderApp(
      <MapFilters
        value={{ provenance_class: "derived" }}
        onChange={(next) => changes.push(next)}
      />,
    );

    fireEvent.change(
      document.querySelector('[data-map-filter="relation_vocabulary"]') as HTMLElement,
      { target: { value: "canonical" } },
    );
    expect(changes.at(-1)).toEqual({
      provenance_class: "derived",
      relation_vocabulary: "canonical",
    });
  });

  it("offers a source by the title the index holds, and clears back to any", async () => {
    vi.stubGlobal(
      "fetch",
      jsonFetch(() => ({ body: sourceList([source(VIDEO, "A video with a title")]) })),
    );
    const changes: GraphFilters[] = [];
    renderApp(<MapFilters value={{}} onChange={(next) => changes.push(next)} />);

    await waitFor(() =>
      expect(screen.getByRole("option", { name: "A video with a title" })).toBeDefined(),
    );
    const select = document.querySelector('[data-map-filter="source_id"]') as HTMLSelectElement;
    fireEvent.change(select, { target: { value: VIDEO } });
    expect(changes.at(-1)).toEqual({ source_id: VIDEO });

    fireEvent.change(select, { target: { value: "" } });
    expect(changes.at(-1)).toEqual({});
  });

  it("says so when it is listing only a page of the sources", async () => {
    vi.stubGlobal(
      "fetch",
      jsonFetch(() => ({ body: sourceList([source(VIDEO, "A video")], "opaque-cursor") })),
    );
    renderApp(<MapFilters value={{}} onChange={() => {}} />);
    await waitFor(() =>
      expect(screen.getByText(/More sources exist than are listed here/)).toBeDefined(),
    );
  });

  it("keeps the other two filters working when the source list is refused", async () => {
    // An unbuilt index refuses `/api/sources` with 503. The graph is still
    // filterable by provenance and vocabulary, so the refusal disables one
    // control and states itself rather than removing the whole filter bar.
    vi.stubGlobal(
      "fetch",
      jsonFetch(() => ({ status: 503, body: refusal("index_unavailable") })),
    );
    const changes: GraphFilters[] = [];
    renderApp(<MapFilters value={{}} onChange={(next) => changes.push(next)} />);

    await waitFor(() =>
      expect(
        document.querySelector("[data-map-filter-sources-failed]")?.getAttribute(
          "data-map-filter-sources-failed",
        ),
      ).toBe("index_unavailable"),
    );
    expect(
      (document.querySelector('[data-map-filter="source_id"]') as HTMLSelectElement).disabled,
    ).toBe(true);

    fireEvent.change(document.querySelector('[data-map-filter="provenance_class"]') as HTMLElement, {
      target: { value: "user" },
    });
    expect(changes.at(-1)).toEqual({ provenance_class: "user" });
  });

  it("asks the server for nothing when the sources are handed to it", () => {
    // The view that already holds the list should not make the same request
    // twice; the component takes the list as a prop when there is one.
    const fetched = vi.fn();
    vi.stubGlobal("fetch", fetched);
    renderApp(
      <MapFilters value={{}} onChange={() => {}} sources={[source(VIDEO, "A video")]} />,
    );
    expect(fetched).not.toHaveBeenCalled();
    expect(screen.getByRole("option", { name: "A video" })).toBeDefined();
  });
});
