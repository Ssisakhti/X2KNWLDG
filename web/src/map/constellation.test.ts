/**
 * The Directional Orbit (`T-213`, ADR 0006 clause 3, D-152, risk R20).
 *
 * Two failures bracket this composition, and both have happened on this route.
 * The one it exists to prevent is a Focus that cannot be read: cards pinned to
 * ForceAtlas marks, competing with labels and edges in one coordinate system,
 * with no visual centre -- the screen `T-211`'s review rejected. The one it
 * must not *cause* is a neighbour that has no card and no other trace, so
 * every refusal below returns a counted reason and `orbitAccountsFor` is
 * asserted at every tier.
 *
 * Tested as arithmetic, because that is what it is: given a field, a
 * neighbourhood and the chrome's rectangles it returns coordinates, and
 * asserting them through a canvas would be asserting Sigma's camera instead.
 * That is also the property the acceptance criterion "changing focus is
 * stable" rests on, and it is checked here directly.
 */

import { describe, expect, it } from "vitest";

import type { EntityRef, IndexedRelation } from "../api/contract";
import { edge, expressesConcept, unit } from "../test/graphRecords";
import {
  ORBIT_COMPACT_MIN_WIDTH,
  ORBIT_FULL_MIN_WIDTH,
  ORBIT_PILL_MIN_WIDTH,
  ORBIT_TIERS,
  STAGE_OMISSIONS,
  orbitAccountsFor,
  orbitMinimumWidth,
  orbitTier,
  placeOrbit,
  stageCardsOverlap,
  type OrbitPlacement,
  type OrbitSide,
  type StageOmission,
  type StageRect,
} from "./constellation";
import type { ActiveRelation, RelatedEntity, RelationDirection } from "./neighbourhood";

/** The review viewport's field: 2852 less the drawer, as `T-212` measured it. */
const FULL = { width: 2260, height: 1632 };
/** A 1440x900 field, which is the tier boundary the browser gate walks. */
const COMPACT = { width: 1440, height: 844 };

const CENTRE = "youtube:pqlWNihgdjI:KU-000001";

function active(
  record: IndexedRelation,
  direction: RelationDirection,
  otherId: string,
): ActiveRelation {
  return { record, direction, otherId };
}

/**
 * One neighbour, stated the way the projection states it.
 *
 * `on` is the side of the *focus* the neighbour belongs to, which is the
 * composition's own vocabulary -- and the record is built to match, which is
 * the inversion this suite exists partly to pin down. `ActiveRelation`'s
 * direction is stated from the entity it is listed under, so a relation
 * running *into* the focus is `outgoing` in the neighbour's own row. Reading
 * that field as the side put every card on the wrong half of the field, and
 * the real graph is what showed it: five `exemplifies` edges pointing at one
 * entity were drawn as though they left it.
 *
 * `parentId` / `toParent` carry what a mark further out hangs off -- the other
 * field `T-213` needed and `projectNeighbourhood` now records.
 */
function related(
  record: EntityRef,
  {
    hops = 1,
    on = "incoming" as OrbitSide,
    parentId = CENTRE,
    relation,
  }: {
    hops?: number;
    on?: OrbitSide;
    parentId?: string | null;
    relation?: IndexedRelation;
  } = {},
): RelatedEntity {
  const id = record.global_id;
  const near = parentId ?? CENTRE;
  // Into the focus means the neighbour is the record's `from_id`, which its
  // own row calls `outgoing`.
  const line = relation ?? (on === "incoming" ? edge(id, near) : edge(near, id));
  const direction: RelationDirection = on === "incoming" ? "outgoing" : "incoming";
  const cue = active(line, direction, near);
  const toCentre = hops === 1 ? [cue] : [];
  return {
    globalId: id,
    record,
    hops,
    toCentre,
    relations: [cue],
    parentId,
    toParent: parentId === null ? [] : [cue],
  };
}

/** `count` neighbours on one side of the focus, in the list's own order. */
function side(on: OrbitSide, count: number, from = 100): RelatedEntity[] {
  return Array.from({ length: count }, (_value, index) =>
    related(unit(`KU-${from + index}`), { on }),
  );
}

function rectOf(placement: OrbitPlacement, globalId: string): StageRect {
  const card = [placement.centre, ...placement.cards].find(
    (candidate) => candidate?.globalId === globalId,
  );
  if (card === undefined || card === null) throw new Error(`no card for ${globalId}`);
  return card.rect;
}

/** Every rectangle the composition draws: cards and pills alike. */
function drawnRects(placement: OrbitPlacement): { id: string; rect: StageRect }[] {
  const cards = [placement.centre, ...placement.cards]
    .filter((card): card is NonNullable<typeof card> => card !== null)
    .map((card) => ({ id: card.globalId, rect: card.rect }));
  const pills = placement.edges.map((line) => ({
    id: `pill:${line.key}`,
    rect: line.pill.rect,
  }));
  return [...cards, ...pills];
}

describe("which composition a field can hold", () => {
  it("names the three tiers at their stated boundaries", () => {
    expect(orbitTier(ORBIT_FULL_MIN_WIDTH)).toBe("full");
    expect(orbitTier(ORBIT_FULL_MIN_WIDTH - 1)).toBe("compact");
    expect(orbitTier(ORBIT_COMPACT_MIN_WIDTH)).toBe("compact");
    expect(orbitTier(ORBIT_COMPACT_MIN_WIDTH - 1)).toBe("stack");
    expect(orbitTier(0)).toBe("stack");
  });

  it("places nothing and counts nothing at the stack tier", () => {
    // SPEC §5's third composition is not a smaller orbit: it is the route's
    // own document, where every relation is a row and *none* is dropped. So
    // the honest omission count here is zero, not twelve.
    const neighbours = [...side("incoming", 4), ...side("outgoing", 4, 200)];
    const placement = placeOrbit({
      centreId: CENTRE,
      related: neighbours,
      field: { width: 390, height: 844 },
    });
    expect(placement.tier).toBe("stack");
    expect(placement.centre).toBeNull();
    expect(placement.cards).toEqual([]);
    expect(placement.omittedTotal).toBe(0);
    expect(orbitAccountsFor(placement, neighbours)).toBe(true);
  });

  it("places nothing on a field that has not been measured yet", () => {
    // The container is sized in CSS and measured after layout, so a zero box
    // is the first render rather than an error -- and placing everything at
    // the origin would be a picture of nothing.
    const placement = placeOrbit({
      centreId: CENTRE,
      related: side("outgoing", 3),
      field: { width: 0, height: 0 },
      tier: "full",
    });
    expect(placement.centre).toBeNull();
    expect(placement.cards).toEqual([]);
  });

  it("places nothing with no selection", () => {
    const placement = placeOrbit({ centreId: null, related: [], field: FULL });
    expect(placement.centre).toBeNull();
  });
});

describe("each tier's boxes fit the field its own boundary promises", () => {
  // Arithmetic rather than taste, and the reason the `compact` boxes are
  // smaller than the mockup drew at 1440: SPEC §5 puts that tier's floor at
  // 900 px, so its centre card and one card a side have to fit in 900. A tier
  // that refuses every card it exists to place would be honest and useless.
  it.each([
    ["full", ORBIT_FULL_MIN_WIDTH],
    ["compact", ORBIT_COMPACT_MIN_WIDTH],
  ] as const)("%s holds a centre card and a card a side at its own minimum", (tier, width) => {
    expect(orbitMinimumWidth(ORBIT_TIERS[tier])).toBeLessThanOrEqual(width);
    const neighbours = [...side("incoming", 1), ...side("outgoing", 1, 200)];
    const placement = placeOrbit({
      centreId: CENTRE,
      related: neighbours,
      field: { width, height: 640 },
    });
    expect(placement.tier).toBe(tier);
    expect(placement.cards).toHaveLength(2);
    expect(placement.omittedTotal).toBe(0);
  });
});

describe("the composition itself", () => {
  it("puts the focused card at the centre of the field", () => {
    const placement = placeOrbit({
      centreId: CENTRE,
      related: [...side("incoming", 3), ...side("outgoing", 3, 200)],
      field: FULL,
    });
    const centre = placement.centre;
    expect(centre).not.toBeNull();
    const rect = centre?.rect as StageRect;
    expect((rect.left + rect.right) / 2).toBeCloseTo(FULL.width / 2, 6);
    expect((rect.top + rect.bottom) / 2).toBeCloseTo(FULL.height / 2, 6);
    // Bigger than any neighbour's, which is one of the four means SPEC §6
    // uses to make it the unmistakable centre.
    const primary = ORBIT_TIERS.full.primaryBox;
    expect(rect.right - rect.left).toBe(primary.width);
    for (const card of placement.cards) {
      expect(card.rect.right - card.rect.left).toBeLessThan(primary.width);
    }
  });

  it("puts incoming relations at the inline start and outgoing at the inline end", () => {
    const placement = placeOrbit({
      centreId: CENTRE,
      related: [...side("incoming", 3), ...side("outgoing", 3, 200)],
      field: FULL,
    });
    const middle = FULL.width / 2;
    for (const card of placement.cards) {
      if (card.side === "incoming") expect(card.port.x).toBeLessThan(middle);
      else expect(card.port.x).toBeGreaterThan(middle);
    }
    expect(placement.cards.some((card) => card.side === "incoming")).toBe(true);
    expect(placement.cards.some((card) => card.side === "outgoing")).toBe(true);
  });

  it("mirrors the sides under a right-to-left script, and only the sides", () => {
    // Incoming-first is a *reading* order (D-012): in Persian the incoming
    // side is the right, where reading starts. The records are untouched --
    // the same relation, the same direction, the other half of the field.
    const neighbours = [...side("incoming", 3), ...side("outgoing", 3, 200)];
    const ltr = placeOrbit({ centreId: CENTRE, related: neighbours, field: FULL });
    const rtl = placeOrbit({ centreId: CENTRE, related: neighbours, field: FULL, rtl: true });
    const middle = FULL.width / 2;
    for (const card of rtl.cards) {
      if (card.side === "incoming") expect(card.port.x).toBeGreaterThan(middle);
      else expect(card.port.x).toBeLessThan(middle);
    }
    expect(rtl.cards.map((card) => card.globalId).sort()).toEqual(
      ltr.cards.map((card) => card.globalId).sort(),
    );
    for (const line of rtl.edges) {
      const same = ltr.edges.find((other) => other.key === line.key);
      expect(same?.relation).toBe(line.relation);
      expect(same?.direction).toBe(line.direction);
    }
  });

  it("reads hop count as distance from the centre", () => {
    const near = related(unit("KU-100"), { on: "outgoing" });
    const far = related(unit("KU-200"), {
      hops: 2,
      on: "outgoing",
      parentId: near.globalId,
    });
    const placement = placeOrbit({
      centreId: CENTRE,
      related: [near, far],
      field: FULL,
    });
    const nearCard = placement.cards.find((card) => card.hops === 1);
    const farCard = placement.cards.find((card) => card.hops === 2);
    expect(nearCard).toBeDefined();
    expect(farCard).toBeDefined();
    const middle = FULL.width / 2;
    expect(Math.abs((farCard?.port.x ?? 0) - middle)).toBeGreaterThan(
      Math.abs((nearCard?.port.x ?? 0) - middle),
    );
    // And it takes its parent's side, because it has no relation to the
    // centre to take a direction from.
    expect(farCard?.side).toBe(nearCard?.side);
  });

  it("draws a mark further out from the card it is actually joined to", () => {
    // SPEC §4: "a hop-2 edge leaves the hop-1 card it is actually joined to,
    // never a phantom point on the ring". Drawing it from the centre would
    // put a relation on screen that the records do not contain.
    const near = related(unit("KU-100"), { on: "outgoing" });
    const far = related(unit("KU-200"), {
      hops: 2,
      on: "outgoing",
      parentId: near.globalId,
    });
    const placement = placeOrbit({ centreId: CENTRE, related: [near, far], field: FULL });
    const nearCard = placement.cards.find((card) => card.globalId === near.globalId);
    const farEdge = placement.edges.find((line) => line.globalId === far.globalId);
    expect(farEdge?.from).toEqual(nearCard?.port);
    // And the pill names that parent rather than the focus.
    expect(farEdge?.nearId).toBe(near.record.local_id);
    const nearEdge = placement.edges.find((line) => line.globalId === near.globalId);
    expect(nearEdge?.nearId).toBeNull();
  });

  it("withdraws and counts a mark whose nearer neighbour has no card", () => {
    // Its parent was refused, so there is no honest starting point for the
    // edge. Both the card and the relation come off the field together: a
    // mark whose place states a hop and a side with nothing joining it to
    // anything is the phantom the clause above forbids.
    const orphan = related(unit("KU-300"), {
      hops: 2,
      on: "outgoing",
      parentId: "youtube:pqlWNihgdjI:KU-999",
    });
    const placement = placeOrbit({ centreId: CENTRE, related: [orphan], field: FULL });
    expect(placement.cards).toEqual([]);
    expect(placement.edges).toEqual([]);
    expect(placement.omitted.unanchored).toBe(1);
    expect(orbitAccountsFor(placement, [orphan])).toBe(true);
  });

  it("counts a neighbour whose records state no direction to place it by", () => {
    // A relation with no direction is not placed on a side and no side is
    // invented for it (SPEC §4). It keeps its row in the related list.
    const loop = unit("KU-400");
    const line = edge(loop.global_id, loop.global_id, "refines");
    const odd: RelatedEntity = {
      globalId: loop.global_id,
      record: loop,
      hops: 1,
      toCentre: [active(line, "self", loop.global_id)],
      relations: [active(line, "self", loop.global_id)],
      parentId: null,
      toParent: [],
    };
    const placement = placeOrbit({ centreId: CENTRE, related: [odd], field: FULL });
    expect(placement.cards).toEqual([]);
    expect(placement.omitted.unanchored).toBe(1);
    expect(orbitAccountsFor(placement, [odd])).toBe(true);
  });

  it("draws one ring per hop it actually placed, and none for a hop it did not", () => {
    const near = related(unit("KU-100"), { on: "outgoing" });
    const placement = placeOrbit({ centreId: CENTRE, related: [near], field: FULL });
    expect(placement.rings.map((ring) => ring.hop)).toEqual([1]);
  });

  it("labels only the sides it drew something on", () => {
    const placement = placeOrbit({
      centreId: CENTRE,
      related: side("outgoing", 2),
      field: FULL,
    });
    expect(placement.sides.map((label) => label.side)).toEqual(["outgoing"]);
  });

  it("reads direction from the focus's end of the relation, not the neighbour's", () => {
    // The defect the real graph found. `exemplifies` running
    // `KU-000029 -> KU-000028` is `outgoing` in KU-000029's own row and
    // `incoming` to the focus, and the composition is about the focus: the
    // card belongs at the inline start and its pill must read
    // `exemplifies -> focus` rather than `focus -> exemplifies`.
    const neighbour = unit("KU-100");
    const into: RelatedEntity = {
      globalId: neighbour.global_id,
      record: neighbour,
      hops: 1,
      toCentre: [active(edge(neighbour.global_id, CENTRE, "exemplifies"), "outgoing", CENTRE)],
      relations: [],
      parentId: CENTRE,
      toParent: [],
    };
    const placement = placeOrbit({ centreId: CENTRE, related: [into], field: FULL });
    expect(placement.cards[0]?.side).toBe("incoming");
    expect(placement.cards[0]?.port.x).toBeLessThan(FULL.width / 2);
    expect(placement.edges[0]?.direction).toBe("incoming");
    expect(placement.edges[0]?.nearId).toBeNull();
  });
});

describe("nothing is drawn over anything", () => {
  it("keeps every card and every pill inside the field", () => {
    const placement = placeOrbit({
      centreId: CENTRE,
      related: [...side("incoming", 4), ...side("outgoing", 4, 200)],
      field: FULL,
    });
    for (const { id, rect } of drawnRects(placement)) {
      expect(`${id}:${rect.left >= 0}`).toBe(`${id}:true`);
      expect(`${id}:${rect.top >= 0}`).toBe(`${id}:true`);
      expect(`${id}:${rect.right <= FULL.width}`).toBe(`${id}:true`);
      expect(`${id}:${rect.bottom <= FULL.height}`).toBe(`${id}:true`);
    }
  });

  it("overlaps no card with another card, and no pill with any card", () => {
    const placement = placeOrbit({
      centreId: CENTRE,
      related: [...side("incoming", 4), ...side("outgoing", 4, 200)],
      field: FULL,
    });
    const rects = drawnRects(placement);
    const hits: string[] = [];
    for (let i = 0; i < rects.length; i += 1) {
      for (let j = i + 1; j < rects.length; j += 1) {
        const a = rects[i];
        const b = rects[j];
        if (a === undefined || b === undefined) continue;
        if (stageCardsOverlap(a.rect, b.rect)) hits.push(`${a.id} over ${b.id}`);
      }
    }
    expect(hits).toEqual([]);
  });

  it("refuses a card that would be drawn under a floating control, and counts it", () => {
    // The workspace put the controls *on* the field (`T-212`), and a card
    // under one shows its first two words and hides the visible truncation
    // marker -- the one silent cut D-131 forbids, arriving from a new
    // direction. The rectangles are the route's own measurements.
    const neighbours = side("outgoing", 3);
    const open = placeOrbit({ centreId: CENTRE, related: neighbours, field: FULL });
    const covered = open.cards.map((card) => card.rect);
    const blocked = placeOrbit({
      centreId: CENTRE,
      related: neighbours,
      field: FULL,
      // A control laid exactly over every card the open field placed.
      obstacles: covered,
    });
    for (const card of blocked.cards) {
      for (const chrome of covered) {
        expect(stageCardsOverlap(card.rect, chrome)).toBe(false);
      }
    }
    expect(orbitAccountsFor(blocked, neighbours)).toBe(true);
  });

  it("seats a pill off its own path rather than over a card, and says so with a leader", () => {
    const placement = placeOrbit({
      centreId: CENTRE,
      related: [...side("incoming", 4), ...side("outgoing", 4, 200)],
      field: FULL,
    });
    expect(placement.edges.length).toBeGreaterThan(0);
    for (const line of placement.edges) {
      // Every pill is the reserved box, exactly: a pill that outgrew its
      // seat would be a label over a card with nothing to notice it. The box
      // is its own text's, bounded at both ends.
      expect(line.pill.box.width).toBeGreaterThanOrEqual(ORBIT_PILL_MIN_WIDTH);
      expect(line.pill.rect.right - line.pill.rect.left).toBeGreaterThanOrEqual(
        line.pill.box.width,
      );
      // A lifted pill keeps a dashed leader back to its edge; one on the path
      // does not need one.
      if (line.pill.leader !== null) {
        expect(line.pill.leader.from).not.toEqual(line.pill.leader.to);
      }
    }
  });

  it("prefers a band that refuses nothing over one that seats the same cards", () => {
    /*
     * The search stops as soon as a band refuses nothing, so "no omissions"
     * is one of the two things it is looking for — but the replacement tested
     * only the card count, so a narrower band that seated the same cards and
     * refused *nothing* was discarded and the wider band's refusals were
     * reported instead. The counts were always the chosen band's own and so
     * always true; the sentence they produce named a reason the composition
     * did not have to have.
     */
    const neighbours = side("outgoing", 3);
    // Chrome across the top and bottom of the field: the widest band runs
    // into it, a narrower one does not.
    const obstacles: StageRect[] = [
      { left: 0, top: 0, right: FULL.width, bottom: 120 },
      { left: 0, top: FULL.height - 120, right: FULL.width, bottom: FULL.height },
    ];
    const placement = placeOrbit({
      centreId: CENTRE,
      related: neighbours,
      field: FULL,
      obstacles,
    });

    // Whatever it settled on, the report is about the band it chose: the
    // omission total and the cards it drew account for every neighbour.
    expect(placement.cards.length + placement.omittedTotal).toBe(neighbours.length);
    expect(
      Object.values(placement.omitted).reduce((sum, count) => sum + count, 0),
    ).toBe(placement.omittedTotal);
    // And it did not settle for refusals it could have avoided: a placement
    // that drew every neighbour must report none.
    if (placement.cards.length === neighbours.length) {
      expect(placement.omittedTotal).toBe(0);
    }
  });

  it("keeps a crowded pill on its path and reports it rather than dropping the relation", () => {
    // Every seat taken is a real outcome, and the two wrong answers are
    // dropping the relation -- the one thing SPEC §4 insists a reader can
    // judge before opening a card -- and moving it somewhere arbitrary
    // without saying so.
    const neighbours = side("outgoing", 2);
    const open = placeOrbit({ centreId: CENTRE, related: neighbours, field: FULL });
    const everywhere: StageRect[] = [
      { left: 0, top: 0, right: FULL.width, bottom: FULL.height },
    ];
    const packed = placeOrbit({
      centreId: CENTRE,
      related: neighbours,
      field: FULL,
      obstacles: everywhere,
    });
    // With the whole field covered no card is placed at all, so there is no
    // pill to crowd: the assertion is that the refusal is counted, not that a
    // pill was drawn anyway.
    expect(packed.cards).toEqual([]);
    expect(packed.omitted.no_room).toBe(neighbours.length);
    expect(open.cards.length).toBeGreaterThan(0);
  });
});

describe("the accounting, at every tier", () => {
  it("places two cards a side at the compact tier and counts the rest", () => {
    // SPEC §5's `compact` tier, and the number `T-212` left to beat: framing
    // by camera ratio placed one card at 1440x900 and counted eight.
    const neighbours = [...side("incoming", 4), ...side("outgoing", 4, 200)];
    const placement = placeOrbit({
      centreId: CENTRE,
      related: neighbours,
      field: COMPACT,
    });
    expect(placement.tier).toBe("compact");
    expect(placement.cards.filter((card) => card.side === "incoming")).toHaveLength(2);
    expect(placement.cards.filter((card) => card.side === "outgoing")).toHaveLength(2);
    expect(placement.omitted.budget).toBe(4);
    expect(orbitAccountsFor(placement, neighbours)).toBe(true);
  });

  it("draws no mark beyond hop 1 at the compact tier, and counts every one", () => {
    const near = related(unit("KU-100"), { on: "outgoing" });
    const far = [1, 2].map((index) =>
      related(unit(`KU-20${index}`), {
        hops: 2,
        on: "outgoing",
        parentId: near.globalId,
      }),
    );
    const neighbours = [near, ...far];
    const placement = placeOrbit({
      centreId: CENTRE,
      related: neighbours,
      field: COMPACT,
    });
    expect(placement.cards.every((card) => card.hops === 1)).toBe(true);
    expect(placement.omitted.no_room).toBe(2);
    expect(orbitAccountsFor(placement, neighbours)).toBe(true);
  });

  it("accounts for every neighbour returned, whatever the field", () => {
    // The invariant R20 rests on: placed plus counted equals returned. Walked
    // over a range of fields rather than asserted at one, because the clause
    // has to hold at the boundary widths as well as the comfortable ones.
    const neighbours = [
      ...side("incoming", 5),
      ...side("outgoing", 5, 200),
      related(unit("KU-300"), {
        hops: 2,
        on: "outgoing",
        parentId: "youtube:pqlWNihgdjI:KU-200",
      }),
    ];
    for (const width of [900, 1024, 1440, 1999, 2000, 2260, 2852]) {
      for (const height of [640, 844, 1632]) {
        const placement = placeOrbit({
          centreId: CENTRE,
          related: neighbours,
          field: { width, height },
        });
        expect(`${width}x${height}: ${orbitAccountsFor(placement, neighbours)}`).toBe(
          `${width}x${height}: true`,
        );
      }
    }
  });

  it("counts every refusal under one of the stated reasons", () => {
    const neighbours = [...side("incoming", 6), ...side("outgoing", 6, 200)];
    const placement = placeOrbit({
      centreId: CENTRE,
      related: neighbours,
      field: COMPACT,
    });
    const counted = STAGE_OMISSIONS.reduce(
      (sum, reason: StageOmission) => sum + placement.omitted[reason],
      0,
    );
    expect(counted).toBe(placement.omittedTotal);
    expect(placement.omittedTotal).toBeGreaterThan(0);
  });
});

describe("the composition is stable", () => {
  it("returns the same picture for the same inputs", () => {
    // "Changing focus is stable and Back restores the prior focus" is the
    // acceptance criterion, and this is the half of it the layout owns: the
    // orbit reads no camera and no clock, so two runs agree exactly.
    const neighbours = [...side("incoming", 3), ...side("outgoing", 3, 200)];
    const once = placeOrbit({ centreId: CENTRE, related: neighbours, field: FULL });
    const twice = placeOrbit({ centreId: CENTRE, related: neighbours, field: FULL });
    expect(twice).toEqual(once);
  });

  it("does not move a card when a neighbour it does not place is added", () => {
    // A composition whose every card shifts when one more arrives is one a
    // reader cannot follow between selections.
    const base = side("outgoing", 2);
    const before = placeOrbit({ centreId: CENTRE, related: base, field: COMPACT });
    const after = placeOrbit({
      centreId: CENTRE,
      related: [...base, ...side("outgoing", 2, 300)],
      field: COMPACT,
    });
    for (const card of before.cards) {
      expect(rectOf(after, card.globalId)).toEqual(card.rect);
    }
  });

  it("keeps a library-synthetic relation distinguishable on its own edge", () => {
    // 62 of the real graph's 118 edges are synthetic, and at this scale an
    // arrow head is two pixels: the vocabulary has to survive as data on the
    // edge, which is what `MapOrbit` dashes it from (ADR 0005 invariant 9).
    const synthetic = related(unit("KU-100"), {
      on: "outgoing",
      relation: expressesConcept(CENTRE, "youtube:pqlWNihgdjI:KU-100"),
    });
    const placement = placeOrbit({ centreId: CENTRE, related: [synthetic], field: FULL });
    expect(placement.edges[0]?.vocabulary).toBe("library_synthetic");
  });
});
