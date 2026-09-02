/**
 * `T-208`: the drawn graph is reachable as a list, and the list is honest
 * about its own bound.
 *
 * Two claims, and the second is the one a bound can quietly break. The rows
 * are the graph's own nodes in the graph's own order -- never a ranking -- and
 * whatever the bound leaves out is counted rather than dropped, which is the
 * same discipline the stage's omission report keeps (D-132, R20).
 */

import { describe, expect, it } from "vitest";

import { GraphSnapshot } from "./graphSnapshot";
import { MAP_OUTLINE_PAGE, outlineOfGraph } from "./outline";
import { VIDEO, concept, edge, expressesConcept, page, payload, unit } from "../test/graphRecords";

const KU1 = `youtube:${VIDEO}:KU-000001`;
const KU2 = `youtube:${VIDEO}:KU-000002`;
const KU3 = `youtube:${VIDEO}:KU-000003`;
const C1 = "library:concepts:122c822b7bbf";

function loaded(): GraphSnapshot {
  const snapshot = new GraphSnapshot({});
  snapshot.applyPage(
    payload({
      nodes: [unit("KU-000001"), unit("KU-000002"), unit("KU-000003"), concept("122c822b7bbf")],
      edges: [edge(KU1, KU2), edge(KU2, KU3), expressesConcept(KU1, C1)],
    }),
    page(),
  );
  return snapshot;
}

describe("the Map's outline", () => {
  it("lists the loaded nodes in the order the API returned them", () => {
    const outline = outlineOfGraph(loaded().graph);
    expect(outline.rows.map((row) => row.globalId)).toEqual([KU1, KU2, KU3, C1]);
    // Not by how connected they are: KU2 has two edges and would be first if
    // this list ranked anything (invariant 15).
    expect(outline.rows[0]?.edgesDrawn).toBe(2);
    expect(outline.rows[1]?.edgesDrawn).toBe(2);
  });

  it("carries the record's own statement, through the one card formatter", () => {
    const outline = outlineOfGraph(loaded().graph);
    const first = outline.rows[0];
    expect(first?.preview.globalId).toBe(KU1);
    expect(first?.preview.text).toBe(
      "A statement the transcript actually makes, numbered KU-000001.",
    );
    // Loaded, because it was read out of the loaded graph. The related list's
    // rows say the opposite for a neighbour the Map has not drawn.
    expect(first?.preview.loaded).toBe(true);
    expect(first?.preview.origin).toBe("graph");
  });

  it("counts drawn edges, and counts a self-relation once", () => {
    const snapshot = new GraphSnapshot({});
    snapshot.applyPage(
      payload({ nodes: [unit("KU-000001")], edges: [edge(KU1, KU1, "refines")] }),
      page(),
    );
    // `degree` in a directed multigraph counts a loop twice -- in and out --
    // which would report one recorded self-relation as two.
    expect(outlineOfGraph(snapshot.graph).rows[0]?.edgesDrawn).toBe(1);
  });

  it("counts what its bound leaves out rather than dropping it", () => {
    const outline = outlineOfGraph(loaded().graph, 2);
    expect(outline.listed).toBe(2);
    expect(outline.loaded).toBe(4);
    expect(outline.unlisted).toBe(2);
    // Listed plus unlisted is loaded: the same identity the constellation's
    // placement report keeps.
    expect(outline.listed + outline.unlisted).toBe(outline.loaded);
  });

  it("states nothing at all about a graph it has not been given", () => {
    // `null` is not an empty library. The Map's own state says which of the
    // two this is (`describeGraph`), and this list does not guess.
    expect(outlineOfGraph(null)).toEqual({ rows: [], loaded: 0, listed: 0, unlisted: 0 });
  });

  it("lists a whole page by default", () => {
    expect(MAP_OUTLINE_PAGE).toBe(25);
    const outline = outlineOfGraph(loaded().graph);
    expect(outline.listed).toBe(4);
    expect(outline.unlisted).toBe(0);
  });
});
