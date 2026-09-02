/**
 * The projection's whole job is to change nothing, so these tests are mostly
 * about absence: no field the API did not send, no value filled in where it
 * sent `null`, and no identity the API did not choose.
 */

import { describe, expect, it } from "vitest";

import { VIDEO, concept, edge, expressesConcept, unit } from "../test/graphRecords";
import {
  GraphConflictError,
  createMapGraph,
  edgeAttributes,
  nodeAttributes,
  recordDifference,
  sameRecord,
} from "./graphProjection";
import { seedPosition } from "./seedPositions";

describe("nodeAttributes", () => {
  it("carries the API's record, not a copy of some of it", () => {
    const record = unit("KU-000001");
    const attributes = nodeAttributes(record);
    expect(attributes.record).toBe(record);
    expect(attributes.record.confidence).toBe(0.91);
    expect(attributes.record.canonical_path).toBe(`output/${record.external_id}/knowledge_units.json`);
  });

  it("adds a seeded position and nothing else", () => {
    // The style matrix is T-205's and D-122 forbids drawing the raw label, so
    // a `label`, `size` or `color` appearing here would be this module
    // deciding a question it does not own -- and an invented field either way.
    expect(Object.keys(nodeAttributes(unit("KU-000001"))).sort()).toEqual(["record", "x", "y"]);
  });

  it("seeds from the node's identity, so a second page cannot move it", () => {
    const record = concept("122c822b7bbf");
    const { x, y } = nodeAttributes(record);
    expect({ x, y }).toEqual(seedPosition(record.global_id));
    expect(x === 0 && y === 0).toBe(false);
  });

  it("keeps a null confidence null, because a concept has none to state", () => {
    const attributes = nodeAttributes(concept("1577d39282f7"));
    expect(attributes.record.confidence).toBeNull();
    expect(attributes.record.source_id).toBeNull();
  });
});

describe("edgeAttributes", () => {
  it("carries the relation record verbatim", () => {
    const record = expressesConcept("youtube:pqlWNihgdjI:KU-000034", "library:concepts:191e");
    const attributes = edgeAttributes(record);
    expect(attributes.record).toBe(record);
    expect(Object.keys(attributes)).toEqual(["record"]);
    expect(attributes.record.relation_vocabulary).toBe("library_synthetic");
    expect(attributes.record.confidence).toBeNull();
  });
});

describe("createMapGraph", () => {
  it("is multi and directed, because the real data is both", () => {
    const graph = createMapGraph();
    expect(graph.multi).toBe(true);
    expect(graph.type).toBe("directed");
  });
});

describe("recordDifference", () => {
  it("finds no difference between a record and itself", () => {
    expect(recordDifference(unit("KU-000001"), unit("KU-000001"))).toBeNull();
    expect(sameRecord(edge("a", "b"), edge("a", "b"))).toBe(true);
  });

  it("treats an absent field and a null one as the same statement", () => {
    // Every optional field in the contract is `field?: T | null`, so both
    // spellings mean "not stated". Refusing a graph over that difference would
    // be refusing it over punctuation.
    const stated = concept("122c", { locator: null });
    const absent = concept("122c");
    delete (absent as { locator?: unknown }).locator;
    expect(recordDifference(stated, absent)).toBeNull();
  });

  it("names the field two pages disagree about", () => {
    expect(recordDifference(unit("KU-000001"), unit("KU-000001", { confidence: 0.4 }))).toBe(
      "confidence",
    );
    expect(recordDifference(unit("KU-000001"), unit("KU-000001", { label: "something else" }))).toBe(
      "label",
    );
  });

  it("does not read a stated confidence and an unstated one as the same", () => {
    // The inverse of the null/absent rule, and the reason it is not simply
    // "ignore nulls": 0.88 against nothing is two claims, and one is wrong.
    expect(recordDifference(edge("a", "b"), edge("a", "b", "supports", { confidence: null }))).toBe(
      "confidence",
    );
  });

  it("descends into nested objects and arrays and names the path", () => {
    const withLocator = unit("KU-000001", {
      locator: { type: "time_range", artifact_id: `youtube:${VIDEO}:A-transcript`, start_sec: 0, end_sec: 30 },
    });
    const moved = unit("KU-000001", {
      locator: { type: "time_range", artifact_id: `youtube:${VIDEO}:A-transcript`, start_sec: 12, end_sec: 30 },
    });
    expect(recordDifference(withLocator, moved)).toBe("locator.start_sec");

    const one = unit("KU-D-0001", { derived_from: ["youtube:x:KU-000001"] });
    const other = unit("KU-D-0001", { derived_from: ["youtube:x:KU-000002"] });
    expect(recordDifference(one, other)).toBe("derived_from[0]");
  });

  it("names the same field whichever order the members were written in", () => {
    const left = { a: 1, b: 2, c: 3 };
    const right = { c: 4, b: 9, a: 1 };
    expect(recordDifference(left, right)).toBe("b");
    expect(recordDifference(right, left)).toBe("b");
  });
});

describe("GraphConflictError", () => {
  it("states what disagreed, so a refusal can be read without a debugger", () => {
    const failure = new GraphConflictError("edge", "a|supports|b", "confidence");
    expect(failure).toBeInstanceOf(Error);
    expect(failure.kind).toBe("edge");
    expect(failure.id).toBe("a|supports|b");
    expect(failure.field).toBe("confidence");
    expect(failure.message).toContain("a|supports|b");
    expect(failure.message).toContain("confidence");
  });
});
