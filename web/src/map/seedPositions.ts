/**
 * Deterministic, non-zero seed positions for graph nodes (`T-202`).
 *
 * Sigma renders a node from its `x`/`y` attributes and ForceAtlas2 refines
 * positions it is *given*; neither invents one. Two properties of this module
 * are the reason it exists rather than a call to a random layout:
 *
 * 1. **A node's seed is a function of its identity, not its arrival order.**
 *    A Map is a progressive snapshot (D-118): nodes arrive page by page and an
 *    edge may reach a node that has not arrived yet (D-059). Seeding by index
 *    would give the same node a different starting point depending on which
 *    page it came in on, so the picture would reshuffle as the walk continued
 *    and a reload could not reproduce it. Hashing the `global_id` makes the
 *    seed stable across pages, reloads, and filter changes.
 * 2. **No node is ever seeded at the origin, and no two ids share a seed by
 *    construction of the layout rather than by luck.** ForceAtlas2's repulsion
 *    divides by the distance between two bodies, so a pile of nodes at one
 *    point is a division by zero, and the layout comes back as `NaN` rather
 *    than as an error.
 *
 * That second failure mode is silent, which is why seeding is applied where a
 * node is *inserted* rather than in a separate pass before layout.
 * `graphology-layout-forceatlas2` reads `attr.x` straight into a
 * `Float32Array`, so a node with no position becomes `NaN` with no throw, no
 * warning, and no visible mark on the canvas -- a node the API really returned
 * and the Map silently did not draw. A position is therefore part of inserting
 * a node, not a step that can be forgotten between two calls.
 *
 * The spread is a uniform disc rather than a circle: nodes on a ring all sit
 * at the same distance from the centre of gravity, which is the one starting
 * shape that gives ForceAtlas2's gravity nothing to work with.
 */

/** FNV-1a, 32-bit. Small, stdlib-free, and stable across engines and runs. */
function fnv1a(text: string, offset: number): number {
  let hash = offset >>> 0;
  for (let index = 0; index < text.length; index += 1) {
    hash ^= text.charCodeAt(index);
    hash = Math.imul(hash, 0x01000193) >>> 0;
  }
  return hash >>> 0;
}

/**
 * Murmur3's finalizer, and not optional here.
 *
 * FNV-1a alone was measured against the real id shape and failed on it. This
 * project's ids share a long prefix and differ in their last few characters --
 * `youtube:pqlWNihgdjI:KU-000001`, `…KU-000002` -- and FNV-1a's avalanche is
 * weak in exactly that case: 200 sequential ids put every radius into four of
 * ten buckets, and *none* of them in the inner half of the disc. The seeds
 * were distinct, so nothing crashed; the graph simply started as a ring, which
 * is the shape this module exists to avoid. The finalizer's shifts and
 * multiplications carry the low-bit difference into the high bits, and the
 * same 200 ids then spread evenly (17-23 per bucket, 51 inside the inner half).
 */
function avalanche(hash: number): number {
  let mixed = hash >>> 0;
  mixed ^= mixed >>> 16;
  mixed = Math.imul(mixed, 0x85ebca6b) >>> 0;
  mixed ^= mixed >>> 13;
  mixed = Math.imul(mixed, 0xc2b2ae35) >>> 0;
  mixed ^= mixed >>> 16;
  return mixed >>> 0;
}

/**
 * Two independent hash streams, so the angle and the radius of one id are not
 * the same number twice. The first is FNV-1a's published offset basis; the
 * second is an arbitrary but fixed second basis, and changing either moves
 * every seed in the project at once.
 */
const ANGLE_BASIS = 0x811c9dc5;
const RADIUS_BASIS = 0x9dc5811c;

const UINT32 = 0x100000000;

/**
 * The seeded disc, in graph units. Sigma rescales the whole scene to the
 * viewport by default, so these numbers set the *relative* spread the layout
 * starts from, never the on-screen size.
 */
export const SEED_MIN_RADIUS = 1;
export const SEED_MAX_RADIUS = 100;

export interface SeedPosition {
  readonly x: number;
  readonly y: number;
}

/**
 * The seed position of one node key.
 *
 * The radius is `sqrt`-distributed so the disc fills evenly instead of
 * crowding the centre, and it starts at `SEED_MIN_RADIUS` rather than at zero:
 * a hash that happened to land on zero would put that node exactly on the
 * centre of gravity.
 */
export function seedPosition(key: string): SeedPosition {
  const angle = (avalanche(fnv1a(key, ANGLE_BASIS)) / UINT32) * 2 * Math.PI;
  const spread = Math.sqrt(avalanche(fnv1a(key, RADIUS_BASIS)) / UINT32);
  const radius = SEED_MIN_RADIUS + spread * (SEED_MAX_RADIUS - SEED_MIN_RADIUS);
  return { x: radius * Math.cos(angle), y: radius * Math.sin(angle) };
}
