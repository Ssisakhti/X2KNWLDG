/**
 * One selected source's neighbourhood, and the two things it must not get wrong.
 *
 * **Direction**, because the Knowledge Map got it wrong once (D-193) and every
 * card landed on the wrong half of the field. The fix there was to read
 * direction from the focus's own end; the fix here is to not derive it at all,
 * because the response already separates the two — so the test that matters is
 * that a relation which *names the centre on both sides* still lands where the
 * response put it.
 *
 * **Accounting**, because a stage with a card budget and a response with a bound
 * are two different places a relationship can be lost, and neither may lose one
 * quietly.
 */

import { describe, expect, it } from "vitest";

import { briefStateOf, projectSourceNeighbourhood, stageBudget } from "./sourceNeighbourhood";
import {
  NO_BRIEF,
  PARTIAL,
  PASS,
  POST,
  brief,
  detail,
  neighbourhoodPayload,
  sourceNode,
  staleBrief,
} from "../test/sourceRecords";

const centre = sourceNode(PASS);

describe("direction", () => {
  it("keeps each side where the response put it", () => {
    const view = projectSourceNeighbourhood(
      neighbourhoodPayload(centre, {
        incoming: [detail(POST, PASS, { id: "SR-in" })],
        outgoing: [detail(PASS, PARTIAL, { id: "SR-out" })],
        neighbors: [sourceNode(POST), sourceNode(PARTIAL)],
      }),
    );
    expect(view.incoming.map((edge) => edge.relation.id)).toEqual(["SR-in"]);
    expect(view.outgoing.map((edge) => edge.relation.id)).toEqual(["SR-out"]);
    expect(view.incoming[0]?.direction).toBe("incoming");
    expect(view.outgoing[0]?.direction).toBe("outgoing");
  });

  it("names the other end from the side the response stated, not by comparing ids", () => {
    // A self-relation is the case that separates the two rules: comparing ids
    // cannot tell which end is "other" when both are the centre, and the
    // response's own arrays still can.
    const view = projectSourceNeighbourhood(
      neighbourhoodPayload(centre, {
        incoming: [detail(PASS, PASS, { id: "SR-self-in" })],
        outgoing: [detail(PASS, PASS, { id: "SR-self-out" })],
        neighbors: [],
      }),
    );
    expect(view.incoming[0]?.otherSourceId).toBe(PASS);
    expect(view.outgoing[0]?.otherSourceId).toBe(PASS);
  });

  it("lists incoming before outgoing, so the companion reads in one order", () => {
    const view = projectSourceNeighbourhood(
      neighbourhoodPayload(centre, {
        incoming: [detail(POST, PASS, { id: "SR-in" })],
        outgoing: [detail(PASS, PARTIAL, { id: "SR-out" })],
      }),
    );
    expect(view.all.map((edge) => edge.relation.id)).toEqual(["SR-in", "SR-out"]);
  });

  it("keeps a relationship whose endpoint record was not returned", () => {
    const view = projectSourceNeighbourhood(
      neighbourhoodPayload(centre, { incoming: [detail(POST, PASS)], neighbors: [] }),
    );
    expect(view.incoming).toHaveLength(1);
    expect(view.incoming[0]?.other).toBeNull();
    // The id survives even where the record does not, so the row can name it.
    expect(view.incoming[0]?.otherSourceId).toBe(POST);
  });
});

describe("the brief", () => {
  it("carries a stale brief with its state, rather than withholding it", () => {
    const view = projectSourceNeighbourhood(
      neighbourhoodPayload(centre, { knowledge: staleBrief() }),
    );
    expect(view.knowledge.state).toBe("stale");
    expect(view.knowledge.brief).not.toBeNull();
    expect(view.knowledge.reason).toContain("knowledge_units_sha256");
  });

  it("states one brief state and claims nothing about any other source", () => {
    const view = projectSourceNeighbourhood(
      neighbourhoodPayload(centre, {
        knowledge: brief("PARTIAL"),
        incoming: [detail(POST, PASS)],
        neighbors: [sourceNode(POST)],
      }),
    );
    const states = briefStateOf(view);
    expect(states.get(centre.global_id)).toBe("available");
    // The neighbour's `EntityRef` says nothing about a brief, so nothing is
    // claimed about it — not even that it has none.
    expect(states.has(`${POST}:source`)).toBe(false);
    expect(states.size).toBe(1);
  });

  it("reports no brief as a state rather than as an error", () => {
    const view = projectSourceNeighbourhood(
      neighbourhoodPayload(sourceNode("youtube:fixture-fail"), { knowledge: NO_BRIEF }),
    );
    expect(view.knowledge.state).toBe("unavailable");
    expect(view.knowledge.brief).toBeNull();
  });
});

describe("the stage budget", () => {
  const many = (count: number, side: "in" | "out") =>
    Array.from({ length: count }, (_value, index) =>
      side === "in"
        ? detail(POST, PASS, { id: `SR-in-${index}` })
        : detail(PASS, PARTIAL, { id: `SR-out-${index}` }),
    );

  it("places what fits and counts the rest, per side", () => {
    const view = projectSourceNeighbourhood(
      neighbourhoodPayload(centre, { incoming: many(5, "in"), outgoing: many(2, "out") }),
    );
    const budget = stageBudget(3, view);
    expect(budget.incoming).toHaveLength(3);
    expect(budget.outgoing).toHaveLength(2);
    expect(budget.omitted).toBe(2);
    // The accounting the gate asserts: nothing returned simply vanishes.
    expect(budget.incoming.length + budget.outgoing.length + budget.omitted).toBe(
      view.all.length,
    );
  });

  it("never spends one side's room on the other", () => {
    // Six incoming and none outgoing must not fill both bands: a card on the
    // outgoing side would state a relationship the response did not return.
    const view = projectSourceNeighbourhood(
      neighbourhoodPayload(centre, { incoming: many(6, "in") }),
    );
    const budget = stageBudget(3, view);
    expect(budget.outgoing).toHaveLength(0);
    expect(budget.omitted).toBe(3);
  });

  it("places nothing at a tier with no room, and counts everything", () => {
    const view = projectSourceNeighbourhood(
      neighbourhoodPayload(centre, { incoming: many(2, "in"), outgoing: many(1, "out") }),
    );
    const budget = stageBudget(0, view);
    expect(budget.incoming).toHaveLength(0);
    expect(budget.outgoing).toHaveLength(0);
    expect(budget.omitted).toBe(3);
  });
});
