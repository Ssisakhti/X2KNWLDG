/**
 * Seeding is the layout's only input the Map controls, so these tests are
 * about the two properties ForceAtlas2 cannot recover from being wrong:
 * a node at the origin, and a node whose start moves between pages.
 */

import { describe, expect, it } from "vitest";

import { SEED_MAX_RADIUS, SEED_MIN_RADIUS, seedPosition } from "./seedPositions";

/** The real graph's identity shape: `source_type:external_id:local_id`. */
const IDS = [
  "youtube:pqlWNihgdjI:KU-000001",
  "youtube:pqlWNihgdjI:KU-000002",
  "youtube:pqlWNihgdjI:KU-D-0001",
  "concept:library:attention",
  "concept:library:transformer",
];

function radiusOf(key: string): number {
  const { x, y } = seedPosition(key);
  return Math.hypot(x, y);
}

describe("seedPosition", () => {
  it("is a pure function of the key, so a page boundary cannot move a node", () => {
    // The same id seeded twice -- as it is when it arrives on page 2 having
    // already been drawn from page 1 -- must be the same point, not a new one.
    for (const id of IDS) {
      expect(seedPosition(id)).toEqual(seedPosition(id));
    }
  });

  it("does not depend on insertion order or on how many nodes there are", () => {
    const forwards = IDS.map(seedPosition);
    const backwards = [...IDS].reverse().map(seedPosition).reverse();
    expect(backwards).toEqual(forwards);
    // And a single id seeded alone matches its place in the full set.
    expect(seedPosition(IDS[2]!)).toEqual(forwards[2]);
  });

  it("never places a node at the origin", () => {
    // ForceAtlas2 divides by the distance between two bodies. A node at the
    // centre of gravity comes back as NaN, and NaN renders as nothing at all.
    for (const id of IDS) {
      const { x, y } = seedPosition(id);
      expect(Number.isFinite(x)).toBe(true);
      expect(Number.isFinite(y)).toBe(true);
      expect(radiusOf(id)).toBeGreaterThanOrEqual(SEED_MIN_RADIUS - 1e-9);
    }
  });

  it("stays inside the seeded disc", () => {
    for (const id of IDS) {
      expect(radiusOf(id)).toBeLessThanOrEqual(SEED_MAX_RADIUS + 1e-9);
    }
  });

  it("separates ids that differ only in their last character", () => {
    // Knowledge unit ids are sequential, so neighbouring ids are the realistic
    // collision risk: KU-000001 and KU-000002 must not start on top of each
    // other, or the layout begins with a division by zero.
    const first = seedPosition("youtube:pqlWNihgdjI:KU-000001");
    const second = seedPosition("youtube:pqlWNihgdjI:KU-000002");
    expect(Math.hypot(first.x - second.x, first.y - second.y)).toBeGreaterThan(1);
  });

  it("gives 86 distinct points to the real sample's worth of sequential ids", () => {
    // The measured graph is 86 nodes. Distinctness is asserted rather than
    // assumed: a hash that collided would pile two real entities onto one point.
    const points = new Set<string>();
    for (let index = 1; index <= 86; index += 1) {
      const id = `youtube:pqlWNihgdjI:KU-${String(index).padStart(6, "0")}`;
      const { x, y } = seedPosition(id);
      points.add(`${x},${y}`);
    }
    expect(points.size).toBe(86);
  });

  it("spreads across the disc rather than around a ring", () => {
    // A ring puts every node the same distance from the centre of gravity,
    // which is the one starting shape gravity cannot improve on.
    const radii = Array.from({ length: 200 }, (_unused, index) =>
      radiusOf(`youtube:pqlWNihgdjI:KU-${String(index).padStart(6, "0")}`),
    );
    const inner = radii.filter((radius) => radius < SEED_MAX_RADIUS / 2).length;
    expect(inner).toBeGreaterThan(20);
    expect(inner).toBeLessThan(180);
  });
});
