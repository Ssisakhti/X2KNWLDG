/**
 * The on-stage density policy (`T-207`, D-132, risk R20).
 *
 * The failure this policy exists to prevent is an HTML card per node -- a
 * "graph" that is a pile of cards with no topology under it, which is exactly
 * what the `T-202` gate observed when it drew every label at once. The failure
 * it must not *cause* is a neighbour that has no card and no other trace, so
 * every clause here returns a counted reason and the counts are what the
 * related list states.
 *
 * Tested against a stub position lookup rather than a renderer: the policy is
 * arithmetic over anchors and a box, and asserting it through a canvas would
 * be asserting Sigma's camera instead.
 */

import { describe, expect, it } from "vitest";

import type { EntityRef } from "../api/contract";
import { concept, unit } from "../test/graphRecords";
import {
  MAP_STAGE_CARD_BUDGET,
  MAP_STAGE_CARD_CELL,
  MAP_STAGE_CARD_INSET,
  MAP_STAGE_NEIGHBOUR_CHARS,
  MAP_STAGE_PRIMARY_CHARS,
  STAGE_OMISSIONS,
  placeConstellation,
  type StageOmission,
} from "./constellation";
import type { MapPoint } from "./mapSession";
import type { RelatedEntity } from "./neighbourhood";

const STAGE = { width: 900, height: 600 };

/** A related entity, reduced to what the policy reads: its identity. */
function related(record: EntityRef, hops = 1): RelatedEntity {
  return { globalId: record.global_id, record, hops, toCentre: [], relations: [] };
}

function neighbours(count: number): RelatedEntity[] {
  return Array.from({ length: count }, (_value, index) =>
    related(unit(`KU-10000${index}`)),
  );
}

/** Anchors by id, and `null` for anything unlisted -- which is "not loaded". */
function positions(points: Record<string, MapPoint>) {
  return (globalId: string) => points[globalId] ?? null;
}

/** Well-separated anchors, one per grid cell, walking across the stage. */
function spread(entities: readonly RelatedEntity[], from = 0): Record<string, MapPoint> {
  const points: Record<string, MapPoint> = {};
  entities.forEach((entity, index) => {
    points[entity.globalId] = {
      x: MAP_STAGE_CARD_INSET + 10 + ((index + from) % 3) * MAP_STAGE_CARD_CELL,
      y: MAP_STAGE_CARD_INSET + 10 + Math.floor((index + from) / 3) * MAP_STAGE_CARD_CELL,
    };
  });
  return points;
}

describe("the stage card policy", () => {
  it("states its own budgets rather than hiding them in a component", () => {
    expect(MAP_STAGE_CARD_BUDGET).toBeGreaterThan(0);
    // A card is a block of text, so its budget is smaller than the label
    // budget it sits beside -- and both are stated numbers `T-209` measures.
    expect(MAP_STAGE_CARD_CELL).toBeGreaterThan(0);
    expect(MAP_STAGE_PRIMARY_CHARS).toBeGreaterThan(MAP_STAGE_NEIGHBOUR_CHARS);
  });

  it("places the selected card and the neighbours that fit", () => {
    const centre = unit("KU-000001");
    const rows = neighbours(2);
    const placement = placeConstellation({
      centreId: centre.global_id,
      related: rows,
      position: positions({
        [centre.global_id]: { x: 700, y: 500 },
        ...spread(rows),
      }),
      stage: STAGE,
    });
    expect(placement.primary?.globalId).toBe(centre.global_id);
    expect(placement.cards.map((card) => card.globalId)).toEqual(
      rows.map((row) => row.globalId),
    );
    expect(placement.omittedTotal).toBe(0);
    // Every neighbour card carries the entity it is a card *for*, so the view
    // never has to look a record up by id and cannot look up the wrong one.
    expect(placement.cards[0]?.related?.globalId).toBe(rows[0]?.globalId);
  });

  it("opens a card away from the edge it is nearest", () => {
    // Logical alignment, computed from the anchor rather than from the
    // language: the card grows towards the middle of the stage in both.
    const centre = unit("KU-000001");
    const near = placeConstellation({
      centreId: centre.global_id,
      related: [],
      position: positions({ [centre.global_id]: { x: 100, y: 100 } }),
      stage: STAGE,
    });
    const far = placeConstellation({
      centreId: centre.global_id,
      related: [],
      position: positions({ [centre.global_id]: { x: 800, y: 500 } }),
      stage: STAGE,
    });
    expect(near.primary?.align).toBe("start");
    expect(near.primary?.above).toBe(false);
    expect(far.primary?.align).toBe("end");
    expect(far.primary?.above).toBe(true);
  });

  it("refuses a card for a neighbour the Map has not drawn, and says which clause", () => {
    const rows = neighbours(3);
    const placement = placeConstellation({
      centreId: null,
      related: rows,
      // Only the first has a mark. The other two are entities the pages have
      // not reached, so there is nothing to anchor to.
      position: positions(spread(rows.slice(0, 1))),
      stage: STAGE,
    });
    expect(placement.cards).toHaveLength(1);
    expect(placement.omitted.not_loaded).toBe(2);
    expect(placement.omittedTotal).toBe(2);
  });

  it("refuses a card for a mark the camera has moved off the stage", () => {
    const rows = neighbours(2);
    const placement = placeConstellation({
      centreId: null,
      related: rows,
      position: positions({
        [rows[0]!.globalId]: { x: 400, y: 300 },
        // Beyond the inset, so its card would be clipped -- and a clipped card
        // hides the very truncation marker that makes a cut visible.
        [rows[1]!.globalId]: { x: STAGE.width - MAP_STAGE_CARD_INSET + 1, y: 300 },
      }),
      stage: STAGE,
    });
    expect(placement.cards.map((card) => card.globalId)).toEqual([rows[0]?.globalId]);
    expect(placement.omitted.off_stage).toBe(1);
  });

  it("refuses a second card in the same cell instead of stacking it", () => {
    const rows = neighbours(2);
    const placement = placeConstellation({
      centreId: null,
      related: rows,
      position: positions({
        [rows[0]!.globalId]: { x: 400, y: 300 },
        [rows[1]!.globalId]: { x: 404, y: 302 },
      }),
      stage: STAGE,
    });
    expect(placement.cards).toHaveLength(1);
    expect(placement.omitted.crowded).toBe(1);
  });

  it("gives the selected card its cell, so a neighbour never lands on top of it", () => {
    const centre = unit("KU-000001");
    const rows = neighbours(1);
    const placement = placeConstellation({
      centreId: centre.global_id,
      related: rows,
      position: positions({
        [centre.global_id]: { x: 400, y: 300 },
        [rows[0]!.globalId]: { x: 410, y: 305 },
      }),
      stage: STAGE,
    });
    expect(placement.primary).not.toBeNull();
    expect(placement.cards).toHaveLength(0);
    expect(placement.omitted.crowded).toBe(1);
  });

  it("caps the neighbour cards at the stated budget, and the primary is not one of them", () => {
    const centre = unit("KU-000001");
    const rows = neighbours(MAP_STAGE_CARD_BUDGET + 3);
    const placement = placeConstellation({
      centreId: centre.global_id,
      related: rows,
      position: positions({
        [centre.global_id]: { x: 860, y: 560 },
        ...spread(rows),
      }),
      stage: STAGE,
    });
    expect(placement.cards).toHaveLength(MAP_STAGE_CARD_BUDGET);
    expect(placement.primary).not.toBeNull();
    expect(placement.omitted.budget).toBe(3);
    // The cards kept are the first of the list's own deterministic order, so
    // which cards appear is reproducible rather than a race with the layout.
    expect(placement.cards.map((card) => card.globalId)).toEqual(
      rows.slice(0, MAP_STAGE_CARD_BUDGET).map((row) => row.globalId),
    );
  });

  it("spends the budget on cards a reader can read, not on ones it refused", () => {
    // A crowded card costs nothing: crowding is checked before the budget, so
    // an overlapping anchor does not use up a slot a later neighbour could.
    const rows = neighbours(MAP_STAGE_CARD_BUDGET + 1);
    const points = spread(rows.slice(1));
    // The first neighbour lands on the second's cell.
    points[rows[0]!.globalId] = { ...points[rows[1]!.globalId]! };
    const placement = placeConstellation({
      centreId: null,
      related: rows,
      position: positions(points),
      stage: STAGE,
    });
    expect(placement.cards).toHaveLength(MAP_STAGE_CARD_BUDGET);
    expect(placement.omitted.crowded).toBe(1);
    expect(placement.omitted.budget).toBe(0);
  });

  it("every refused neighbour is counted exactly once, under one reason", () => {
    const rows = neighbours(MAP_STAGE_CARD_BUDGET + 4);
    const points = spread(rows.slice(0, MAP_STAGE_CARD_BUDGET + 1));
    // One off the stage, one crowded, one unplaced for want of a mark, and the
    // rest over budget.
    points[rows[0]!.globalId] = { x: -50, y: 300 };
    points[rows[1]!.globalId] = { ...points[rows[2]!.globalId]! };
    delete points[rows[3]!.globalId];
    const placement = placeConstellation({
      centreId: null,
      related: rows,
      position: positions(points),
      stage: STAGE,
    });
    const counted = STAGE_OMISSIONS.reduce(
      (sum: number, reason: StageOmission) => sum + placement.omitted[reason],
      0,
    );
    expect(placement.omittedTotal).toBe(counted);
    // The accounting is total: a returned neighbour is either on the stage or
    // counted as absent from it, and never neither.
    expect(placement.cards.length + placement.omittedTotal).toBe(rows.length);
  });

  it("places nothing at all before the stage has been measured", () => {
    // The container is sized in CSS and measured after layout, so the first
    // render has a zero box. Placing everything at the origin would put a pile
    // of cards in one corner and call it a constellation.
    const rows = neighbours(2);
    const placement = placeConstellation({
      centreId: null,
      related: rows,
      position: positions(spread(rows)),
      stage: { width: 0, height: 0 },
    });
    expect(placement.cards).toHaveLength(0);
    expect(placement.omitted.off_stage).toBe(2);
  });

  it("places no primary card for a selection with no mark", () => {
    // A focus the loaded pages do not hold is not drawn as one anywhere else
    // either, and a card pinned to a node that is not on screen would point at
    // nothing.
    const placement = placeConstellation({
      centreId: null,
      related: [related(concept("C-000001"))],
      position: positions({}),
      stage: STAGE,
    });
    expect(placement.primary).toBeNull();
    expect(placement.omitted.not_loaded).toBe(1);
  });
});
