/**
 * The complete related list (`T-207`, D-132, risk R20).
 *
 * The claim this file exists for is one sentence from `T-207`'s acceptance
 * criteria: **no neighbour silently disappears.** So the tests below stack the
 * odds against that -- more neighbours than the stage can carry, neighbours the
 * Map has not drawn, a neighbour two hops out with no relation to the focus at
 * all, and a server that says it cut the walk short -- and count the rows every
 * time.
 *
 * The second claim is the one that makes the list *useful* rather than merely
 * complete (D-130's acceptance question): before opening a neighbour, the row
 * says what it states and by which real relation it is connected.
 */

import { fireEvent, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { EntityRef } from "../api/contract";
import { ApiFailure } from "../api/errors";
import { concept, edge, expressesConcept, unit } from "../test/graphRecords";
import { renderApp } from "../test/render";
import { createMapGraph, nodeAttributes } from "../map/graphProjection";
import { MAP_STAGE_CARD_BUDGET, placeConstellation } from "../map/constellation";
import { projectNeighbourhood, type Neighbourhood } from "../map/neighbourhood";
import type { MapPeekBinding } from "../map/useMapPeek";
import { MapRelatedList } from "./MapRelatedList";

const KU1 = "youtube:pqlWNihgdjI:KU-000001";
const KU2 = "youtube:pqlWNihgdjI:KU-000002";
const KU3 = "youtube:pqlWNihgdjI:KU-000003";
const C1 = "library:concepts:C-000001";

/** A Peek binding that records what it was asked, and holds nothing. */
function stubPeek(): MapPeekBinding {
  return {
    peek: null,
    open: vi.fn(),
    close: vi.fn(),
    handlers: () => ({
      onMouseEnter: () => undefined,
      onMouseLeave: () => undefined,
      onFocus: () => undefined,
      onBlur: () => undefined,
    }),
  };
}

function graphOf(records: readonly EntityRef[]) {
  const graph = createMapGraph();
  for (const record of records) graph.addNode(record.global_id, nodeAttributes(record));
  return graph;
}

/** Two neighbours of `KU-000001`, joined by two different vocabularies. */
function twoNeighbours(): Neighbourhood {
  return projectNeighbourhood({
    center_id: KU1,
    depth: 1,
    nodes: [unit("KU-000001"), unit("KU-000002"), concept("C-000001")],
    edges: [edge(KU1, KU2, "supports"), expressesConcept(KU1, C1)],
    truncated: false,
  });
}

function list(props: Partial<Parameters<typeof MapRelatedList>[0]> = {}) {
  return renderApp(
    <MapRelatedList
      focus={KU1}
      neighbourhood={twoNeighbours()}
      status="ready"
      error={null}
      onRetry={() => undefined}
      depth={1}
      onDepthChange={() => undefined}
      graph={graphOf([unit("KU-000001"), unit("KU-000002"), concept("C-000001")])}
      onFocus={() => undefined}
      peek={stubPeek()}
      placement={null}
      {...props}
    />,
  );
}

/** Every row's `global_id`, in the order the DOM has them. */
function rows(): string[] {
  return [...document.querySelectorAll("[data-map-related-entity]")].map(
    (node) => node.getAttribute("data-map-related-entity") ?? "",
  );
}

describe("the related list", () => {
  it("lists every returned neighbour, with its statement and its relation", () => {
    list();
    // The order is the sort key `neighbourhood.ts` fixes: same hops, then the
    // relation as stated, so `expresses_concept` precedes `supports`. It says
    // nothing about importance and it is the same on every run.
    expect(rows()).toEqual([C1, KU2]);
    // What it says: the record's own statement, on the card.
    expect(
      screen.getByText("A statement the transcript actually makes, numbered KU-000002."),
    ).toBeDefined();
    // Why it is worth opening: the real relation, and its direction.
    expect(screen.getByText("supports")).toBeDefined();
    expect(screen.getByText("expresses_concept")).toBeDefined();
    expect(document.querySelector("[data-map-related]")?.getAttribute("data-map-related")).toBe(
      "2",
    );
  });

  it("lists a neighbour whose card the stage could not place, and says why", () => {
    // The whole of R20's mitigation in one assertion: more neighbours than the
    // budget allows, every one of them still a row.
    const many = Array.from({ length: MAP_STAGE_CARD_BUDGET + 3 }, (_value, index) =>
      unit(`KU-20000${index}`),
    );
    const neighbourhood = projectNeighbourhood({
      center_id: KU1,
      depth: 1,
      nodes: [unit("KU-000001"), ...many],
      edges: many.map((record) => edge(KU1, record.global_id, "supports")),
      truncated: false,
    });
    const placement = placeConstellation({
      centreId: KU1,
      related: neighbourhood.related,
      // Every mark on one point, so the policy has to refuse all but the
      // first. The `y` is one with room for a card below it: the fit clause
      // needs `height + gap + inset` of clear stage on one side (D-145).
      position: () => ({ x: 400, y: 150 }),
      stage: { width: 900, height: 600 },
    });

    list({ neighbourhood, graph: graphOf([unit("KU-000001"), ...many]), placement });

    expect(rows()).toHaveLength(many.length);
    expect(placement.omittedTotal).toBeGreaterThan(0);
    expect(
      document.querySelector("[data-map-stage-omitted]")?.getAttribute("data-map-stage-omitted"),
    ).toBe(String(placement.omittedTotal));
    expect(document.querySelector("[data-map-stage-omission='crowded']")).not.toBeNull();
  });

  it("marks the rows whose cards *are* on the stage", () => {
    const neighbourhood = twoNeighbours();
    const placement = placeConstellation({
      centreId: KU1,
      related: neighbourhood.related,
      position: (globalId) => (globalId === KU2 ? { x: 400, y: 150 } : null),
      stage: { width: 900, height: 600 },
    });
    list({ neighbourhood, placement });
    const marked = [...document.querySelectorAll("[data-map-related-on-stage]")];
    expect(marked).toHaveLength(1);
    expect(marked[0]?.closest("[data-map-related-entity]")?.getAttribute(
      "data-map-related-entity",
    )).toBe(KU2);
  });

  it("distinguishes a neighbour the Map has drawn from one it has not loaded", () => {
    // Two different facts. The list reads the second from the accumulated
    // graph rather than assuming it from the response.
    list({ graph: graphOf([unit("KU-000001"), unit("KU-000002")]) });
    expect(screen.getByText("Loaded on the Map")).toBeDefined();
    expect(screen.getByText("Not loaded on the Map yet.")).toBeDefined();
  });

  it("says a two-hop neighbour states no relation to the focus, rather than borrowing one", () => {
    const neighbourhood = projectNeighbourhood({
      center_id: KU1,
      depth: 2,
      nodes: [unit("KU-000001"), unit("KU-000002"), unit("KU-000003")],
      edges: [edge(KU1, KU2), edge(KU2, KU3)],
      truncated: false,
    });
    list({
      neighbourhood,
      depth: 2,
      graph: graphOf([unit("KU-000001"), unit("KU-000002"), unit("KU-000003")]),
    });
    expect(rows()).toEqual([KU2, KU3]);
    expect(
      screen.getByText(
        "Reached through another entity 2 hops out; it states no relation to the focus itself.",
      ),
    ).toBeDefined();
  });

  it("states that the server cut the walk short", () => {
    const neighbourhood = projectNeighbourhood({
      center_id: KU1,
      depth: 1,
      nodes: [unit("KU-000001"), unit("KU-000002")],
      edges: [edge(KU1, KU2)],
      truncated: true,
    });
    list({ neighbourhood });
    expect(document.querySelector("[data-map-related-truncated]")).not.toBeNull();
    expect(
      screen.getByText(
        "The server cut the walk short at its own limit, so more neighbours exist than were returned.",
      ),
    ).toBeDefined();
  });

  it("states an entity with no relations as empty rather than as absent", () => {
    const neighbourhood = projectNeighbourhood({
      center_id: KU1,
      depth: 1,
      nodes: [unit("KU-000001")],
      edges: [],
      truncated: false,
    });
    list({ neighbourhood });
    expect(rows()).toEqual([]);
    expect(
      screen.getByText("The index records no relation for this entity at this depth."),
    ).toBeDefined();
  });

  it("offers the contract's three depths and reports the one chosen", () => {
    const chosen: number[] = [];
    list({ onDepthChange: (depth) => chosen.push(depth) });
    const control = screen.getByLabelText("Depth") as HTMLSelectElement;
    expect([...control.options].map((option) => option.value)).toEqual(["1", "2", "3"]);
    fireEvent.change(control, { target: { value: "3" } });
    expect(chosen).toEqual([3]);
  });

  it("focuses a neighbour by its own `global_id`", () => {
    // Every row's control carries the id it will focus, so a click cannot
    // resolve to a different identity than the row it is in.
    const focused: (string | null)[] = [];
    list({ onFocus: (globalId) => focused.push(globalId) });
    const button = document.querySelector<HTMLButtonElement>(
      `[data-map-focus-action="${KU2}"]`,
    );
    expect(button).not.toBeNull();
    fireEvent.click(button as HTMLButtonElement);
    expect(focused).toEqual([KU2]);
  });

  it("states a refused neighbourhood instead of an empty list", () => {
    list({
      neighbourhood: null,
      error: new ApiFailure("index_unavailable", "The index is rebuilding."),
    });
    expect(document.querySelector("[data-error-code='index_unavailable']")).not.toBeNull();
    expect(rows()).toEqual([]);
  });

  it("says nothing is focused rather than listing an empty neighbourhood", () => {
    list({ focus: null, neighbourhood: null });
    expect(
      screen.getByText("Nothing is focused, so there is no neighbourhood to list."),
    ).toBeDefined();
  });
});
