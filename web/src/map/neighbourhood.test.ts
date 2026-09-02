/**
 * The bounded neighbourhood, projected (`T-207`, D-132).
 *
 * The claims under test are the ones an on-stage budget could otherwise hide:
 *
 * - **No neighbour disappears.** Every node the response carried is in
 *   `related`, whatever its distance, whatever its relation, whether the
 *   response reached it by an edge this Map can draw or not. This is R20's
 *   mitigation, and it is asserted by counting.
 * - **The order is reproducible.** Two projections of one response, and of the
 *   same response with its arrays shuffled, produce the same list in the same
 *   order -- because the order is a sort over stated fields rather than the
 *   order the server happened to serialise.
 * - **The direction is the record's.** `from_id -> to_id` decides `outgoing`
 *   and `incoming`, from the listed entity's point of view, and a self-loop is
 *   named rather than dropped.
 * - **A contradiction is refused, not merged** -- the same refusal
 *   `GraphSnapshot` makes, because it is the same projection (D-125).
 */

import { describe, expect, it } from "vitest";

import type { EntityRef, IndexedRelation, NeighborhoodPayload } from "../api/contract";
import { concept, edge, expressesConcept, unit } from "../test/graphRecords";
import { GraphConflictError } from "./graphProjection";
import {
  MAP_DEPTHS,
  MAP_DEPTH_MAX,
  MAP_DEPTH_MIN,
  noNeighbourhood,
  parseDepth,
  projectNeighbourhood,
} from "./neighbourhood";

const KU1 = "youtube:pqlWNihgdjI:KU-000001";
const KU2 = "youtube:pqlWNihgdjI:KU-000002";
const KU3 = "youtube:pqlWNihgdjI:KU-000003";
const KU4 = "youtube:pqlWNihgdjI:KU-000004";
const C1 = "library:concepts:C-000001";

function hood(
  nodes: EntityRef[],
  edges: IndexedRelation[],
  options: { centre?: string; depth?: number; truncated?: boolean } = {},
): NeighborhoodPayload {
  return {
    center_id: options.centre ?? KU1,
    depth: options.depth ?? 1,
    nodes,
    edges,
    truncated: options.truncated ?? false,
  };
}

/** The shape the real endpoint returns for one unit with two neighbours. */
function twoNeighbours(): NeighborhoodPayload {
  return hood(
    [unit("KU-000001"), unit("KU-000002"), concept("C-000001")],
    [edge(KU1, KU2), expressesConcept(KU1, C1)],
  );
}

describe("the depth bound", () => {
  it("is the contract's own 1..3", () => {
    expect(MAP_DEPTH_MIN).toBe(1);
    expect(MAP_DEPTH_MAX).toBe(3);
    expect(MAP_DEPTHS).toEqual([1, 2, 3]);
  });

  it("ignores a value outside it rather than clamping one into it", () => {
    // The server refuses `depth=4`; answering it with `depth=3` would tell the
    // client a bound it never set, and the response echoes `depth` back.
    expect(parseDepth(4)).toBeNull();
    expect(parseDepth(0)).toBeNull();
    expect(parseDepth("2")).toBeNull();
    expect(parseDepth(1.5)).toBeNull();
    expect(parseDepth(null)).toBeNull();
    expect(parseDepth(2)).toBe(2);
  });
});

describe("projectNeighbourhood", () => {
  it("lists every neighbour the response returned", () => {
    const result = projectNeighbourhood(twoNeighbours());
    expect(result.centreId).toBe(KU1);
    expect(result.centre?.global_id).toBe(KU1);
    expect(result.related.map((entity) => entity.globalId).sort()).toEqual([C1, KU2].sort());
    expect(result.related).toHaveLength(result.nodesReturned - 1);
    expect(result.edgesReturned).toBe(2);
    expect(result.edgesUnjoinable).toBe(0);
    expect(result.unreachable).toBe(0);
    expect(result.truncated).toBe(false);
  });

  it("keeps the record verbatim, including a null the server wrote out", () => {
    const result = projectNeighbourhood(twoNeighbours());
    const conceptRow = result.related.find((entity) => entity.globalId === C1);
    expect(conceptRow?.record.confidence).toBeNull();
    expect(conceptRow?.record.source_id).toBeNull();
    expect(conceptRow?.record.label).toBe(concept("C-000001").label);
  });

  it("names each connection's real relation and its direction", () => {
    // Two edges, one out of the centre and one into it, so both directions are
    // exercised from the *neighbour's* point of view -- which is the point of
    // view the related list renders.
    const result = projectNeighbourhood(
      hood([unit("KU-000001"), unit("KU-000002"), unit("KU-000003")], [
        edge(KU1, KU2, "supports"),
        edge(KU3, KU1, "contradicts"),
      ]),
    );
    const two = result.related.find((entity) => entity.globalId === KU2);
    const three = result.related.find((entity) => entity.globalId === KU3);
    expect(two?.toCentre).toHaveLength(1);
    expect(two?.toCentre[0]?.record.relation).toBe("supports");
    expect(two?.toCentre[0]?.direction).toBe("incoming");
    expect(two?.toCentre[0]?.otherId).toBe(KU1);
    expect(three?.toCentre[0]?.record.relation).toBe("contradicts");
    expect(three?.toCentre[0]?.direction).toBe("outgoing");

    // And the centre's own view of the same two edges, which is what Quick
    // Read renders: one out, one in.
    expect(result.active.map((relation) => relation.direction).sort()).toEqual([
      "incoming",
      "outgoing",
    ]);
  });

  it("states more than one relation between the same pair rather than choosing one", () => {
    // The real graph joins a pair with a canonical relation *and* a
    // library-synthetic one often enough that `parallelPath: "curved"` exists
    // for it. Both are the index's claims; picking one would drop evidence.
    const result = projectNeighbourhood(
      hood([unit("KU-000001"), unit("KU-000002")], [
        edge(KU1, KU2, "supports"),
        expressesConcept(KU1, KU2),
      ]),
    );
    const two = result.related.find((entity) => entity.globalId === KU2);
    expect(two?.toCentre).toHaveLength(2);
    expect(two?.toCentre.map((relation) => relation.record.relation)).toEqual([
      "expresses_concept",
      "supports",
    ]);
    expect(two?.toCentre.map((relation) => relation.record.relation_vocabulary)).toEqual([
      "library_synthetic",
      "canonical",
    ]);
  });

  it("names a self-loop instead of dropping it", () => {
    // `intentional_self_loop` is a design the pipeline marks, not an error to
    // filter, so the centre's own relation to itself is stated.
    const result = projectNeighbourhood(
      hood([unit("KU-000001")], [edge(KU1, KU1, "refines")]),
    );
    expect(result.related).toHaveLength(0);
    expect(result.active).toHaveLength(1);
    expect(result.active[0]?.direction).toBe("self");
    expect(result.active[0]?.otherId).toBe(KU1);
  });

  it("counts hops, and says so instead of inventing a relation to the centre", () => {
    // Depth 2: `KU-000003` is reached through `KU-000002` and states no
    // relation to the centre at all. Borrowing the near neighbour's relation
    // would be an edge no request returned.
    const result = projectNeighbourhood(
      hood(
        [unit("KU-000001"), unit("KU-000002"), unit("KU-000003")],
        [edge(KU1, KU2), edge(KU2, KU3)],
        { depth: 2 },
      ),
    );
    const rows = new Map(result.related.map((entity) => [entity.globalId, entity]));
    expect(rows.get(KU2)?.hops).toBe(1);
    expect(rows.get(KU3)?.hops).toBe(2);
    expect(rows.get(KU3)?.toCentre).toEqual([]);
    // It still knows what it *is* connected to inside the neighbourhood.
    expect(rows.get(KU3)?.relations).toHaveLength(1);
    expect(rows.get(KU3)?.relations[0]?.otherId).toBe(KU2);
  });

  it("reaches a neighbour whichever way the index stored the edge", () => {
    // Reachability is undirected: a reader following `supports` backwards has
    // still reached the neighbour. Direction is stated per relation instead.
    const result = projectNeighbourhood(
      hood([unit("KU-000001"), unit("KU-000002")], [edge(KU2, KU1)]),
    );
    expect(result.related[0]?.hops).toBe(1);
    expect(result.unreachable).toBe(0);
  });

  it("orders by hops, then the stated relation, then identity", () => {
    const result = projectNeighbourhood(
      hood(
        [
          unit("KU-000004"),
          unit("KU-000002"),
          unit("KU-000001"),
          unit("KU-000003"),
        ],
        [edge(KU1, KU4, "supports"), edge(KU1, KU2, "contradicts"), edge(KU4, KU3, "supports")],
        { depth: 2 },
      ),
    );
    expect(result.related.map((entity) => entity.globalId)).toEqual([KU2, KU4, KU3]);
    expect(result.related.map((entity) => entity.hops)).toEqual([1, 1, 2]);
  });

  it("produces the same list whatever order the response serialised", () => {
    const forwards = projectNeighbourhood(
      hood(
        [unit("KU-000001"), unit("KU-000002"), unit("KU-000003"), unit("KU-000004")],
        [edge(KU1, KU2, "supports"), edge(KU1, KU3, "supports"), edge(KU1, KU4, "refines")],
      ),
    );
    const backwards = projectNeighbourhood(
      hood(
        [unit("KU-000004"), unit("KU-000003"), unit("KU-000002"), unit("KU-000001")],
        [edge(KU1, KU4, "refines"), edge(KU1, KU3, "supports"), edge(KU1, KU2, "supports")],
      ),
    );
    expect(backwards.related.map((entity) => entity.globalId)).toEqual(
      forwards.related.map((entity) => entity.globalId),
    );
  });

  it("honours the centre the response echoed, not the id the client asked with", () => {
    // The contract echoes `center_id` back precisely so a client that batches
    // requests cannot mis-attribute a response. Reading it is what makes the
    // guarantee worth having.
    const result = projectNeighbourhood(
      hood([unit("KU-000002"), unit("KU-000003")], [edge(KU2, KU3)], { centre: KU2 }),
    );
    expect(result.centreId).toBe(KU2);
    expect(result.related.map((entity) => entity.globalId)).toEqual([KU3]);
  });

  it("counts an edge whose endpoint the response did not return rather than drawing it", () => {
    const result = projectNeighbourhood(
      hood([unit("KU-000001"), unit("KU-000002")], [edge(KU1, KU2), edge(KU1, KU3)]),
    );
    expect(result.edgesReturned).toBe(1);
    expect(result.edgesUnjoinable).toBe(1);
    expect(result.related.map((entity) => entity.globalId)).toEqual([KU2]);
  });

  it("lists a returned node it cannot connect to the centre, and counts it", () => {
    const result = projectNeighbourhood(hood([unit("KU-000001"), unit("KU-000002")], []));
    expect(result.unreachable).toBe(1);
    expect(result.related.map((entity) => entity.globalId)).toEqual([KU2]);
    expect(result.related[0]?.toCentre).toEqual([]);
  });

  it("states an empty neighbourhood as empty rather than as absent", () => {
    const result = projectNeighbourhood(hood([unit("KU-000001")], []));
    expect(result.centre?.global_id).toBe(KU1);
    expect(result.related).toEqual([]);
    expect(result.active).toEqual([]);
    expect(result.nodesReturned).toBe(1);
  });

  it("carries the server's own `truncated` rather than guessing from a length", () => {
    const result = projectNeighbourhood(
      hood([unit("KU-000001"), unit("KU-000002")], [edge(KU1, KU2)], { truncated: true }),
    );
    expect(result.truncated).toBe(true);
  });

  it("accepts the same record twice and refuses two records claiming one id", () => {
    const twice = projectNeighbourhood(
      hood([unit("KU-000001"), unit("KU-000001")], []),
    );
    expect(twice.nodesReturned).toBe(1);

    expect(() =>
      projectNeighbourhood(
        hood([unit("KU-000001"), unit("KU-000001", { confidence: 0.2 })], []),
      ),
    ).toThrowError(GraphConflictError);
    try {
      projectNeighbourhood(hood([unit("KU-000001"), unit("KU-000001", { confidence: 0.2 })], []));
    } catch (cause) {
      expect((cause as GraphConflictError).field).toBe("confidence");
      expect((cause as GraphConflictError).kind).toBe("node");
    }
  });

  it("has an empty value that claims nothing", () => {
    const empty = noNeighbourhood(KU1, 1);
    expect(empty.centre).toBeNull();
    expect(empty.related).toEqual([]);
    expect(empty.truncated).toBe(false);
    expect(empty.nodesReturned).toBe(0);
  });
});
