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
  MAP_STAGE_CARD_BOX,
  MAP_STAGE_CARD_BUDGET,
  MAP_STAGE_CARD_GAP,
  MAP_STAGE_CARD_INSET,
  MAP_STAGE_NEIGHBOUR_CHARS,
  MAP_STAGE_PRIMARY_BOX,
  MAP_STAGE_PRIMARY_CHARS,
  STAGE_OMISSIONS,
  placeConstellation,
  stageCardRect,
  stageCardsOverlap,
  type StageOmission,
  type StagePlacement,
} from "./constellation";
import type { MapPoint } from "./mapSession";
import type { RelatedEntity } from "./neighbourhood";

const STAGE = { width: 900, height: 600 };

/**
 * A roomier stage and a small card, for the tests about the *clauses*.
 *
 * The policy's clause order and its accounting are arithmetic over anchors and
 * a box; asserting them with the shipped 320x248 card would mean hand-placing
 * eight anchors that provably miss each other on one stage, and the test would
 * then be about that arrangement. The shipped boxes have tests of their own
 * below -- both of them regressions from what `T-209` measured in a browser.
 */
const STAGE_WIDE = { width: 1600, height: 1200 };
const TEST_BOX = { width: 120, height: 80 };

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

/**
 * Anchors whose `TEST_BOX` cards provably miss each other, on `STAGE_WIDE`.
 *
 * All of them sit in one quadrant, so every card opens the same way and the
 * spacing argument is one subtraction: 200 px apart, a 120x80 card and a
 * 12 px gap, so consecutive cards are 68 px clear horizontally and 108 px
 * clear vertically. Anchors either side of the stage's midpoint would flip
 * `align`/`above` and could then collide while being 200 px apart, which is
 * the kind of arrangement a test should not have to reason about.
 */
function spread(entities: readonly RelatedEntity[], from = 0): Record<string, MapPoint> {
  const points: Record<string, MapPoint> = {};
  entities.forEach((entity, index) => {
    points[entity.globalId] = {
      x: 100 + ((index + from) % 4) * 200,
      y: 100 + Math.floor((index + from) / 4) * 200,
    };
  });
  return points;
}

/** `placeConstellation` over `spread`'s anchors: the wide stage, the small card. */
function placeSpread(
  input: Omit<Parameters<typeof placeConstellation>[0], "stage" | "box" | "primaryBox">,
) {
  return placeConstellation({
    ...input,
    stage: STAGE_WIDE,
    box: TEST_BOX,
    primaryBox: TEST_BOX,
  });
}

describe("the stage card policy", () => {
  it("states its own budgets rather than hiding them in a component", () => {
    expect(MAP_STAGE_CARD_BUDGET).toBeGreaterThan(0);
    // A card is a block of text, and how much room it takes is measured
    // rather than argued: `T-209` laid the real route out in Chrome and these
    // are the boxes it got back (D-145).
    expect(MAP_STAGE_CARD_BOX.width).toBeGreaterThan(0);
    expect(MAP_STAGE_CARD_BOX.height).toBeGreaterThan(0);
    expect(MAP_STAGE_PRIMARY_BOX.width).toBeGreaterThan(MAP_STAGE_CARD_BOX.width);
    expect(MAP_STAGE_CARD_GAP).toBeGreaterThan(0);
    expect(MAP_STAGE_PRIMARY_CHARS).toBeGreaterThan(MAP_STAGE_NEIGHBOUR_CHARS);
  });

  it("places the selected card and the neighbours that fit", () => {
    const centre = unit("KU-000001");
    const rows = neighbours(2);
    const placement = placeSpread({
      centreId: centre.global_id,
      related: rows,
      position: positions({
        // The far corner, so the primary card is nowhere near the grid.
        [centre.global_id]: { x: 1400, y: 1000 },
        ...spread(rows),
      }),
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
    const placement = placeSpread({
      centreId: null,
      related: rows,
      // Only the first has a mark. The other two are entities the pages have
      // not reached, so there is nothing to anchor to.
      position: positions(spread(rows.slice(0, 1))),
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
        // A `y` with room for a card below it: the fit clause needs
        // `height + gap + inset` of clear stage on one side of the mark.
        [rows[0]!.globalId]: { x: 400, y: 150 },
        // Beyond the inset, so its card would be clipped -- and a clipped card
        // hides the very truncation marker that makes a cut visible.
        [rows[1]!.globalId]: { x: STAGE.width - MAP_STAGE_CARD_INSET + 1, y: 150 },
      }),
      stage: STAGE,
    });
    expect(placement.cards.map((card) => card.globalId)).toEqual([rows[0]?.globalId]);
    expect(placement.omitted.off_stage).toBe(1);
  });

  it("refuses a card that would cover one already placed, instead of stacking it", () => {
    const rows = neighbours(2);
    const placement = placeConstellation({
      centreId: null,
      related: rows,
      position: positions({
        [rows[0]!.globalId]: { x: 400, y: 150 },
        [rows[1]!.globalId]: { x: 404, y: 152 },
      }),
      stage: STAGE,
    });
    expect(placement.cards).toHaveLength(1);
    expect(placement.omitted.crowded).toBe(1);
  });

  it("gives the selected card its own rectangle, so a neighbour never lands on top of it", () => {
    const centre = unit("KU-000001");
    const rows = neighbours(1);
    const placement = placeConstellation({
      centreId: centre.global_id,
      related: rows,
      position: positions({
        [centre.global_id]: { x: 400, y: 150 },
        [rows[0]!.globalId]: { x: 410, y: 155 },
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
    const placement = placeSpread({
      centreId: centre.global_id,
      related: rows,
      position: positions({
        [centre.global_id]: { x: 1500, y: 1100 },
        ...spread(rows),
      }),
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
    // The first neighbour lands on the second's anchor.
    points[rows[0]!.globalId] = { ...points[rows[1]!.globalId]! };
    const placement = placeSpread({
      centreId: null,
      related: rows,
      position: positions(points),
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
    const placement = placeSpread({
      centreId: null,
      related: rows,
      position: positions(points),
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
      box: TEST_BOX,
      primaryBox: TEST_BOX,
    });
    expect(placement.cards).toHaveLength(0);
    expect(placement.omitted.off_stage).toBe(2);
  });

  /*
   * The two halves of what `T-209` measured, as regressions.
   *
   * The policy used to ask "is another card in this 240 px cell?", and on the
   * real route that answered the wrong question twice. Both cases below are
   * the numbers the browser actually produced on the busiest entity of the
   * real 86/118 graph at a 1216x630 stage, with the shipped card boxes.
   */
  describe("the crowding clause, as measured in a browser (D-145)", () => {
    /*
     * Everything here comes from what `T-209` found on the real route, and
     * the fix has two halves because the grid got both halves wrong.
     *
     * A 240 px cell answered "is another card in this cell?", which is not
     * the question: two anchors either side of a cell boundary can be one
     * pixel apart, and two in one cell can be 300 apart. So a neighbour card
     * covered two thirds of the focused statement -- its identifier and the
     * marker that says its text was cut -- while seven neighbours whose cards
     * would have fitted were refused.
     *
     * And once overlap *was* the test, a second finding surfaced: a card
     * opens towards the middle of the stage so it is not clipped, so two
     * marks either side of the middle grow towards each other and meet. In a
     * twenty-focus sample of the real graph that placed the focused card and
     * not one neighbour's, at every degree. Hence the four orientations.
     */
    const REAL_STAGE = { width: 1216, height: 630 };

    /** Every placed card's drawn rectangle, primary included. */
    function rects(placement: StagePlacement) {
      const boxes = placement.cards.map((card) => stageCardRect(card, MAP_STAGE_CARD_BOX));
      return placement.primary === null
        ? boxes
        : [stageCardRect(placement.primary, MAP_STAGE_PRIMARY_BOX), ...boxes];
    }

    /** The invariant, stated once: no two drawn cards share a pixel. */
    function expectNoOverlap(placement: StagePlacement) {
      const boxes = rects(placement);
      for (let left = 0; left < boxes.length; left += 1) {
        for (let right = left + 1; right < boxes.length; right += 1) {
          expect(
            stageCardsOverlap(boxes[left] as never, boxes[right] as never),
            `cards ${left} and ${right} overlap`,
          ).toBe(false);
        }
      }
    }

    it("never draws two cards over the same pixels", () => {
      // The two anchors Chrome actually reported for the focus and its first
      // neighbour: 77 px apart horizontally, 12 apart vertically.
      const centre = unit("KU-000001");
      const rows = neighbours(1);
      const placement = placeConstellation({
        centreId: centre.global_id,
        related: rows,
        position: positions({
          [centre.global_id]: { x: 679.86, y: 70.17 },
          [rows[0]!.globalId]: { x: 756.83, y: 82.33 },
        }),
        stage: REAL_STAGE,
      });
      expect(placement.primary).not.toBeNull();
      expectNoOverlap(placement);
      // Whatever the policy did with the neighbour, it accounted for it.
      expect(placement.cards.length + placement.omittedTotal).toBe(rows.length);
    });

    it("opens a card the other way rather than covering one already placed", () => {
      // Two marks either side of the middle, far enough apart that a card
      // fits between them -- and the preferred orientations still collide,
      // because both prefer to open *inwards*. This is the shape of every
      // focus in the twenty-entity sample: the second card flips outwards
      // instead of being refused.
      const rows = neighbours(2);
      const placement = placeConstellation({
        centreId: null,
        related: rows,
        position: positions({
          [rows[0]!.globalId]: { x: 300, y: 200 },
          [rows[1]!.globalId]: { x: 700, y: 200 },
        }),
        stage: REAL_STAGE,
      });
      expect(placement.cards).toHaveLength(2);
      expect(placement.omittedTotal).toBe(0);
      // The second opens away from the middle: `end` was preferred and would
      // have covered the first.
      expect(placement.cards.map((card) => card.align)).toEqual(["start", "start"]);
      expectNoOverlap(placement);
    });

    it("refuses a neighbour whose card fits in none of its four directions", () => {
      // Four pixels from a card already placed: every orientation's rectangle
      // still contains an anchor inside the other card, because a card and
      // the pointer back to its mark are one object.
      const rows = neighbours(2);
      const placement = placeConstellation({
        centreId: null,
        related: rows,
        position: positions({
          [rows[0]!.globalId]: { x: 400, y: 200 },
          [rows[1]!.globalId]: { x: 404, y: 202 },
        }),
        stage: REAL_STAGE,
      });
      expect(placement.cards).toHaveLength(1);
      expect(placement.omitted.crowded).toBe(1);
    });

    it("refuses a card the stage has no room for, and says that rather than crowded", () => {
      // What the shipped UI actually did before this clause existed: two cards
      // anchored either side of the stage's middle opened *upwards*, spilled
      // out of the top of the stage — the overlay is a sibling of the
      // container, so nothing clips it — and had the first line of their
      // statements covered by the panel above. A statement whose first line is
      // hidden is the *silent* cut D-131 forbids, because nothing says it was
      // cut: it was not, it was hidden.
      //
      // A card needs `height + gap + inset` of clear stage on one side of its
      // mark, so on a 630 px stage a 296 px card leaves a band around the
      // middle where no direction works. A mark in it keeps its emphasis, its
      // label and its row; it gets no card, and the reason is its own.
      const rows = neighbours(1);
      const placement = placeConstellation({
        centreId: null,
        related: rows,
        position: positions({ [rows[0]!.globalId]: { x: 600, y: 315 } }),
        stage: REAL_STAGE,
      });
      expect(placement.cards).toHaveLength(0);
      expect(placement.omitted.no_room).toBe(1);
      // Not the reason for a mark the camera has moved away, and not the
      // reason for a neighbour already there. Both would send a reader to fix
      // the wrong thing.
      expect(placement.omitted.off_stage).toBe(0);
      expect(placement.omitted.crowded).toBe(0);
      expect(placement.omittedTotal).toBe(1);
    });

    it("keeps every card it does place wholly on the stage", () => {
      // The property, over the whole stage rather than one anchor: whatever
      // the policy places is inside the container, at every position a mark
      // could take.
      const rows = neighbours(1);
      for (let y = MAP_STAGE_CARD_INSET; y < REAL_STAGE.height; y += 17) {
        for (let x = MAP_STAGE_CARD_INSET; x < REAL_STAGE.width; x += 37) {
          const placement = placeConstellation({
            centreId: null,
            related: rows,
            position: positions({ [rows[0]!.globalId]: { x, y } }),
            stage: REAL_STAGE,
          });
          for (const card of placement.cards) {
            const rect = stageCardRect(card, MAP_STAGE_CARD_BOX);
            expect(rect.left, `card left of the stage at ${x},${y}`).toBeGreaterThanOrEqual(0);
            expect(rect.top, `card above the stage at ${x},${y}`).toBeGreaterThanOrEqual(0);
            expect(rect.right, `card right of the stage at ${x},${y}`).toBeLessThanOrEqual(
              REAL_STAGE.width,
            );
            expect(rect.bottom, `card below the stage at ${x},${y}`).toBeLessThanOrEqual(
              REAL_STAGE.height,
            );
          }
        }
      }
    });

    it("still guarantees the selected card, even where no direction fits", () => {
      // D-132 guarantees *one* primary card, so it is the one card that falls
      // back to its preferred direction rather than being dropped: a
      // selection with nothing on screen is worse than a card partly over the
      // edge, and the counts and Quick Read say the same thing in words
      // either way.
      const centre = unit("KU-000001");
      const placement = placeConstellation({
        centreId: centre.global_id,
        related: [],
        // On the stage — the inset clause is satisfied — but with no room for
        // a 176 px card on either side of it.
        position: positions({ [centre.global_id]: { x: 600, y: 150 } }),
        stage: { width: 1216, height: 300 },
      });
      expect(placement.primary).not.toBeNull();
      expect(placement.primary?.globalId).toBe(centre.global_id);
    });

    it("reserves the rectangle the card is actually drawn in, mark included", () => {
      // The reserved rectangle *is* the drawn one, and it includes the mark:
      // one computed anywhere else is a policy about nothing, and one that
      // stopped at the card's own edge let two cards point into the same
      // four pixels from opposite directions.
      const card = {
        globalId: "youtube:pqlWNihgdjI:KU-000001",
        related: null,
        point: { x: 500, y: 400 },
        align: "start" as const,
        above: false,
      };
      const box = { width: 200, height: 100 };
      const gap = MAP_STAGE_CARD_GAP;
      expect(stageCardRect(card, box)).toEqual({
        left: 500 - gap,
        top: 400 - gap,
        right: 500 + gap + box.width,
        bottom: 400 + gap + box.height,
      });
      // And the other way, which is the same rectangle mirrored about the mark.
      expect(stageCardRect({ ...card, align: "end", above: true }, box)).toEqual({
        left: 500 - gap - box.width,
        top: 400 - gap - box.height,
        right: 500 + gap,
        bottom: 400 + gap,
      });
    });

    it("places a second card once its mark is a card's width away", () => {
      // Same side of the stage, so both prefer the same direction and only
      // real clearance can place the second one.
      const rows = neighbours(2);
      const at = (gap: number) =>
        placeConstellation({
          centreId: null,
          related: rows,
          position: positions({
            [rows[0]!.globalId]: { x: 100, y: 100 },
            [rows[1]!.globalId]: { x: 100 + gap, y: 100 },
          }),
          stage: REAL_STAGE,
        });
      // A card reaches from its mark to the far edge of its box: the gap,
      // then the box, and the mark's own square on the other side.
      const clear = MAP_STAGE_CARD_BOX.width + MAP_STAGE_CARD_GAP * 2;
      expect(at(40).cards).toHaveLength(1);
      expect(at(clear).cards).toHaveLength(2);
      expectNoOverlap(at(clear));
    });
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

/**
 * `T-212`: the workspace put the controls on the field.
 *
 * Until the Map became a workspace, everything that competed with a card was
 * either the stage's own edge or another card, and both were already clauses
 * here. D-153 added a third competitor: a search surface, the counts, the
 * legend, the one primary drawer and the camera's controls all float *on* the
 * field now. A card is drawn over whatever the route puts there -- the overlay
 * is a sibling of the renderer's container, so nothing clips it (D-137) --
 * which means a card under a control shows its first two words and hides the
 * visible truncation marker. That is the one silent cut D-131 forbids,
 * arriving from a new direction, and the mockup's own geometry check found it
 * at 1440x900 before any of this was written.
 *
 * The reason such a card is refused is `no_room`, and that is the point of
 * asserting it: the mark *is* on the stage, so `off_stage` would send a reader
 * panning a camera that is not the problem, and `crowded` names another card.
 */
describe("the stage's floating chrome", () => {
  const FIELD = { width: 1200, height: 800 };

  /** A surface across the field's whole top edge, 200 px deep. */
  const TOP_CHROME = { left: 0, top: 0, right: FIELD.width, bottom: 200 };

  it("changes nothing when there is none, which is every stage before T-212", () => {
    // The default is an empty list, so the clause is additive: the policy's
    // own tests above pass an input with no `obstacles` at all.
    const rows = neighbours(3);
    const points = spread(rows);
    const input = {
      centreId: null,
      related: rows,
      position: positions(points),
      stage: STAGE_WIDE,
      box: TEST_BOX,
    };
    expect(placeConstellation({ ...input, obstacles: [] })).toEqual(placeConstellation(input));
  });

  it("refuses a card that would be drawn underneath a floating control", () => {
    // One neighbour, anchored where every orientation of its card lands
    // inside the surface across the top of the field.
    const [row] = neighbours(1);
    const at = (obstacles: readonly { left: number; top: number; right: number; bottom: number }[]) =>
      placeConstellation({
        centreId: null,
        related: [row!],
        position: positions({ [row!.globalId]: { x: 600, y: 100 } }),
        stage: FIELD,
        box: TEST_BOX,
        obstacles,
      });

    // Without the surface the card is placed: the mark is well inside the
    // stage and nothing else is on it.
    expect(at([]).cards).toHaveLength(1);

    // With it, no orientation is both on the stage and clear of the control.
    const refused = at([TOP_CHROME]);
    expect(refused.cards).toHaveLength(0);
    // The real reason, not a convenient one: the mark is on the stage.
    expect(refused.omitted.no_room).toBe(1);
    expect(refused.omitted.off_stage).toBe(0);
    expect(refused.omitted.crowded).toBe(0);
    // And it is counted, which is what keeps it in the related list (R20).
    expect(refused.omittedTotal).toBe(1);
  });

  it("opens a card the other way rather than refusing it", () => {
    // The same clause as the crowding one: a card tries all four orientations
    // before it is refused, so a control above a mark costs a direction and
    // not a card. `above: false` grows the card downwards, away from the
    // surface across the top.
    const [row] = neighbours(1);
    const placement = placeConstellation({
      centreId: null,
      related: [row!],
      position: positions({ [row!.globalId]: { x: 600, y: 260 } }),
      stage: FIELD,
      box: TEST_BOX,
      obstacles: [TOP_CHROME],
    });
    expect(placement.cards).toHaveLength(1);
    expect(placement.cards[0]!.above).toBe(false);
    expect(stageCardRect(placement.cards[0]!, TEST_BOX).top).toBeGreaterThanOrEqual(
      TOP_CHROME.bottom,
    );
  });

  it("keeps the selected card out from under the chrome as well", () => {
    // The card D-132 *guarantees* now chooses between three tiers rather than
    // two: on the stage and clear of the controls, then merely on the stage,
    // then the preferred direction whatever it covers. Being covered is worse
    // for this card than for any other, because it is the one the reader asked
    // for -- a WCAG 2.2 AA *Focus Not Obscured* failure and not a cosmetic
    // overlap (SPEC §8).
    const centre = unit("KU-000001");
    const placement = placeConstellation({
      centreId: centre.global_id,
      related: [],
      position: positions({ [centre.global_id]: { x: 600, y: 260 } }),
      stage: FIELD,
      obstacles: [TOP_CHROME],
    });
    expect(placement.primary).not.toBeNull();
    const rect = stageCardRect(placement.primary!, MAP_STAGE_PRIMARY_BOX);
    expect(stageCardsOverlap(rect, TOP_CHROME)).toBe(false);
  });

  it("still places the selected card when every direction is covered", () => {
    // The fallback stays a fallback. A selection with nothing on screen is not
    // an improvement on a card partly under a control, and this is the card
    // D-132 guarantees -- a neighbour in the same position is refused and
    // counted instead, which the clause above asserts.
    const centre = unit("KU-000001");
    const placement = placeConstellation({
      centreId: centre.global_id,
      related: [],
      position: positions({ [centre.global_id]: { x: 600, y: 100 } }),
      stage: FIELD,
      obstacles: [{ left: 0, top: 0, right: FIELD.width, bottom: FIELD.height }],
    });
    expect(placement.primary).not.toBeNull();
    expect(placement.primary?.globalId).toBe(centre.global_id);
  });

  it("counts placed cards plus omissions as the neighbours it was given", () => {
    // The accounting is total whatever the chrome does to it, which is the
    // claim R20 is judged on: every neighbour the API returned is either a
    // card on the stage or a counted reason there is none.
    const rows = neighbours(6);
    const points = spread(rows);
    const placement = placeConstellation({
      centreId: null,
      related: rows,
      position: positions(points),
      stage: STAGE_WIDE,
      box: TEST_BOX,
      obstacles: [{ left: 0, top: 0, right: STAGE_WIDE.width, bottom: 300 }],
    });
    expect(placement.cards.length + placement.omittedTotal).toBe(rows.length);
    expect(
      STAGE_OMISSIONS.reduce((sum, reason) => sum + placement.omitted[reason], 0),
    ).toBe(placement.omittedTotal);
  });
});
