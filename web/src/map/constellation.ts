/**
 * Where a card may go on the stage, and why the rest have none (`T-213`,
 * D-132, D-152, risk R20).
 *
 * This module used to answer that question by pinning cards to the marks
 * ForceAtlas had already placed. `T-209` measured that policy honestly and it
 * worked; `T-211`'s review rejected the *composition* it produced, and ADR
 * 0006 clause 3 replaced it with a **Directional Orbit**: the selected card at
 * the centre of the field, incoming relations to the inline start, outgoing to
 * the inline end, and actual hop count as radial distance. `placeOrbit` is
 * that layout, and it is the only answer this route has to "where may a card
 * go" -- there is no second one, and the mark-anchored placement it replaces
 * is gone rather than kept beside it.
 *
 * **What changed, and what deliberately did not.**
 *
 * The orbit is *derived presentation state* over the same records: the
 * transient neighbourhood (`neighbourhood.ts`) and the selection. It reads no
 * graph store, holds none, creates no identity, and flows back into neither
 * (§8.6). What it stops reading is the camera. The old policy asked
 * `MapSession.nodePosition` where each mark was, so the constellation changed
 * with every pan and two of its five refusal reasons were facts about a
 * camera. The orbit asks nothing: given a field, a neighbourhood and the
 * chrome's rectangles it returns the same picture on every run and on every
 * machine, which is the acceptance clause "changing focus is stable".
 *
 * What did not change is the accounting, and it is the part R20 rests on:
 * **placed plus counted equals the neighbours the API returned, at every
 * tier**. Every refusal below returns a *reason*, the reasons are counted, the
 * count is rendered on the field and beside the list, and the entity itself is
 * in the complete related list either way. No neighbour is ever silently
 * dropped, and `orbitAccountsFor` is the assertion, kept here beside the
 * policy rather than only in a test.
 *
 * **Three compositions, not one scaled three ways** (SPEC §5). The orbit needs
 * room for a centre card and a card on each side. Below that it cannot be
 * drawn honestly, and the answer is not to shrink text until it is unreadable
 * -- it is to place fewer cards and count what was left off, and below the
 * `compact` minimum to draw no orbit at all and let the route's document
 * composition carry the focus and every one of its relations as a row.
 */

import { MAP_EDGE_LABEL_CHARS } from "./labelPolicy";
import type { MapPoint } from "./mapSession";
import type { RelatedEntity, RelationDirection } from "./neighbourhood";

/* -- the field, and the three compositions it can hold ------------------- */

/**
 * Which composition a field of this width can hold (SPEC §5).
 *
 * The two boundaries are arithmetic rather than taste, and `T-212` measured
 * the upper one in a browser: 2000 px is where a 560 px drawer still leaves a
 * field wide enough to place a card beside a centred primary, and below it the
 * drawer floats over the field instead of taking a slice out of it. 900 px is
 * where the centre card plus one card on each side stops fitting at all.
 */
export type OrbitTier = "full" | "compact" | "stack";

/** At or above this, the field holds the whole orbit and the open drawer. */
export const ORBIT_FULL_MIN_WIDTH = 2000;

/** At or above this, the field holds a centre card and two cards a side. */
export const ORBIT_COMPACT_MIN_WIDTH = 900;

/** Which composition a field of this width can hold. Zero means unmeasured. */
export function orbitTier(width: number): OrbitTier {
  if (width >= ORBIT_FULL_MIN_WIDTH) return "full";
  if (width >= ORBIT_COMPACT_MIN_WIDTH) return "compact";
  return "stack";
}

/** A card's footprint, in pixels. */
export interface StageCardBox {
  width: number;
  height: number;
}

/** The field's own pixel box. Zero means "not measured yet", and places nothing. */
export interface StageBox {
  width: number;
  height: number;
}

/** A rectangle on the field, in the same pixels the cards are placed in. */
export interface StageRect {
  left: number;
  top: number;
  right: number;
  bottom: number;
}

/**
 * The boxes, arms and insets one tier lays out with (SPEC §4, §5, §6).
 *
 * Stated per tier rather than scaled from one set, because that is the whole
 * argument of SPEC §5: a `compact` field is not a `full` field at 70 %, it is
 * a different composition with fewer cards, and its card is smaller because it
 * carries the same two lines in less room -- not because everything shrank.
 *
 * The heights are **upper bounds over what the browser actually lays out**,
 * which is the discipline `T-209` established for `MAP_STAGE_CARD_BOX`: a
 * reserved rectangle smaller than the drawn card is a fit test that passes
 * while the card hangs over the edge. The widths are exact, because
 * `MapOrbit` writes them onto the element.
 *
 * They are larger than SPEC §6 proposes, and `scripts/measure_orbit.ts` is
 * why: at 320 px wide Chrome laid a neighbour's card out at 186 px against
 * the 148 the mockup drew, so the reservation was smaller than the card and
 * a relation pill was seated in space the policy believed was empty. The
 * mockup's own cards carried no `global_id` line and its measurement was of
 * itself. A number measured on the shipped card beats a number drawn beside
 * one.
 */
export interface OrbitTierGeometry {
  /** The selected card, at the field's centre. */
  primaryBox: StageCardBox;
  /** A hop-1 neighbour's card. */
  cardBox: StageCardBox;
  /** A further-out mark's chip: it carries less, by design (SPEC §4). */
  chipBox: StageCardBox;
  /** How many hop-1 cards a side may hold, before the rest are counted. */
  perSide: number;
  /** Whether marks beyond hop 1 are drawn at all at this tier. */
  showFar: boolean;
  /** The hop-1 arm at the band's extremes, before the field's own scale. */
  armNear: number;
  /** How much wider the arm is for a band level with the centre (SPEC §4). */
  armFar: number;
  /** How much further out each hop beyond the first sits. */
  armStep: number;
  /** Room kept at the field's block start for the floating chrome. */
  topInset: number;
  /** Room kept at the field's block end for the same reason. */
  bottomInset: number;
}

/**
 * The tiers, stated once.
 *
 * `stack` carries boxes of zero on purpose: it places nothing on the field, so
 * a box for it would be a number nothing reads. Its composition is the route's
 * own document -- the focused record, then every relation as a row -- and
 * *none* of them is dropped, which is why `stack` also has no omissions.
 */
export const ORBIT_TIERS: Readonly<Record<OrbitTier, OrbitTierGeometry>> = {
  full: {
    primaryBox: { width: 560, height: 232 },
    cardBox: { width: 320, height: 208 },
    chipBox: { width: 220, height: 108 },
    perSide: Number.POSITIVE_INFINITY,
    showFar: true,
    armNear: 520,
    armFar: 130,
    armStep: 300,
    topInset: 150,
    bottomInset: 130,
  },
  compact: {
    primaryBox: { width: 300, height: 200 },
    cardBox: { width: 270, height: 240 },
    chipBox: { width: 220, height: 108 },
    perSide: 2,
    showFar: false,
    armNear: 300,
    armFar: 60,
    armStep: 300,
    topInset: 140,
    bottomInset: 110,
  },
  stack: {
    primaryBox: { width: 0, height: 0 },
    cardBox: { width: 0, height: 0 },
    chipBox: { width: 0, height: 0 },
    perSide: 0,
    showFar: false,
    armNear: 0,
    armFar: 0,
    armStep: 0,
    topInset: 0,
    bottomInset: 0,
  },
};

/**
 * The width the arms are stated against (SPEC §4's geometry table).
 *
 * The table's numbers are the review viewport's, so a narrower field scales
 * them down rather than running its cards off the edge. Above it nothing
 * grows: an arm longer than the composition was drawn for pushes the cards
 * into the field's corners and empties the middle.
 */
export const ORBIT_REFERENCE_WIDTH = 2280;

/**
 * The narrowest field a tier's own boxes fit in, as arithmetic.
 *
 * Half the centre card, the gap, a neighbour's card and the field's inset, on
 * one side. A tier whose boundary is narrower than this is a tier that refuses
 * every card it was defined to place and counts them all -- honest, and
 * useless. The suite asserts it against `ORBIT_TIERS`, which is why the
 * `compact` boxes are smaller than the mockup drew at 1440: they have to hold
 * at 900, which is where SPEC §5 puts that tier's floor.
 */
export function orbitMinimumWidth(geometry: OrbitTierGeometry): number {
  return (
    geometry.primaryBox.width +
    2 * (ORBIT_CARD_GAP + geometry.cardBox.width + ORBIT_FIELD_INSET)
  );
}

/** The furthest a card's band centre may sit from the field's (SPEC §4). */
export const ORBIT_BAND_MAX = 560;

/** The closest two bands may sit before the composition stops reading as rows. */
export const ORBIT_BAND_MIN = 120;

/** The clear space a card keeps from its own port, and from another card. */
export const ORBIT_CARD_GAP = 12;

/** How far inside the field a card's rectangle must stay. */
export const ORBIT_FIELD_INSET = 16;

/**
 * How far out a refused card is pushed before it is counted, and how often.
 *
 * The one adjustment the orbit allows itself, and it is deliberately the only
 * one: pushing a card *outward along its own arm* keeps the two things the
 * composition means -- which side it is on, and which band it is in -- while
 * nudging it vertically would move it between bands and make the hop rings
 * lie. A card that still does not fit after these steps is refused and
 * counted, which is the same trade `T-209` settled for the old policy: a
 * counted refusal beats a card drawn over something.
 */
export const ORBIT_ARM_STEP = 48;
export const ORBIT_ARM_TRIES = 6;

/**
 * The narrower bands tried when the widest one runs a card under the chrome.
 *
 * SPEC §4 clamps the vertical band "so no card runs under floating chrome",
 * and this is that clamp: fractions of the band the field alone would allow,
 * tried in order, the first that seats every card winning. Stated as a list
 * rather than solved for, because the obstacles are measured rectangles in
 * arbitrary places and the answer has to be reproducible rather than optimal.
 */
export const ORBIT_BAND_STEPS: readonly number[] = [0.82, 0.64, 0.46, 0.28, 0.12, 0];

/**
 * How far the whole composition may slide to keep its centre card clear.
 *
 * The centre is the field's middle wherever the field allows it. Where a
 * floating control stands exactly there -- the counts surface reaches the
 * vertical middle at the `compact` tier -- the composition slides on the block
 * axis rather than letting the one card the reader asked for be painted over.
 */
export const ORBIT_CENTRE_STEP = 24;
export const ORBIT_CENTRE_TRIES = 12;

/**
 * How much of a statement each kind of card may show.
 *
 * Unchanged from `T-207` for the two that existed (SPEC §6 keeps them both),
 * and the chip's budget is `MAP_LABEL_CHARS.neighbour`'s number rather than a
 * sixth opinion about how long a preview is. The cut itself is the one cutter
 * (D-131, §8.6), so these are budgets and not a second policy.
 */
export const MAP_STAGE_PRIMARY_CHARS = 200;
export const MAP_STAGE_NEIGHBOUR_CHARS = 110;
export const MAP_STAGE_CHIP_CHARS = 64;

/**
 * The relation pill's reserved rectangle, from its own text (SPEC §4).
 *
 * The reservation has to *be* the drawn rectangle -- a pill seated against a
 * box it then outgrows is a label over a card, the clause the visual gate
 * checks -- so `MapOrbit` writes this exact width onto the element and the
 * text inside is centred in it. `ORBIT_PILL_CHAR` is a deliberate upper bound
 * over what the 12 px face actually measures, so the label always has more
 * room than it needs; the relation name is cut by `MAP_EDGE_LABEL_CHARS` with
 * the cut visible, so it can neither overflow nor shorten in silence.
 *
 * One fixed width for every pill was tried first and measured wrong. At the
 * `full` tier a hop-1 edge has `arm - primaryBox.width / 2` of clear run
 * between the two cards it joins; a 260 px pill is wider than that run, so
 * four of seven pills found no seat at all and were reported crowded. A pill
 * as wide as its own words fits the geometry SPEC §4 states.
 */
export const ORBIT_PILL_HEIGHT = 30;
export const ORBIT_PILL_MIN_WIDTH = 110;
export const ORBIT_PILL_MAX_WIDTH = 260;
/** An upper bound on one character of the pill's face, in pixels. */
export const ORBIT_PILL_CHAR = 8;
/** The arrow, the vocabulary glyph, the gaps and the padding around them. */
export const ORBIT_PILL_FURNITURE = 56;
/**
 * Characters allowed for the word naming the focus itself.
 *
 * The near end of a hop-1 pill is the focus, and the focus is a *word* in the
 * reader's language rather than an id -- so its length is the catalogue's, and
 * a pure layout cannot read a catalogue. Eight is above both shipped words
 * ("focus", "کانون") with room for a third locale.
 */
export const ORBIT_PILL_FOCUS_CHARS = 8;

/** The box one pill's own text needs, bounded at both ends. */
export function orbitPillBox(relation: string, nearId: string | null): StageCardBox {
  const chars =
    Math.min(Array.from(relation).length, MAP_EDGE_LABEL_CHARS) +
    (nearId === null ? ORBIT_PILL_FOCUS_CHARS : Array.from(nearId).length);
  return {
    width: Math.max(
      ORBIT_PILL_MIN_WIDTH,
      Math.min(ORBIT_PILL_MAX_WIDTH, chars * ORBIT_PILL_CHAR + ORBIT_PILL_FURNITURE),
    ),
    height: ORBIT_PILL_HEIGHT,
  };
}

/** The clear space a pill keeps from a card, from the field's edge, and from another pill. */
export const ORBIT_PILL_GAP = 6;

/**
 * Where along its own edge a pill is tried, and how far it is lifted off it.
 *
 * Two freedoms, walked in a stated order so the seat is reproducible: where
 * along the path, then how far off it. A short edge between two adjacent cards
 * has almost no clear run, so the lift is what seats it -- and a lifted pill
 * keeps a dashed leader back to its edge, so it still reads as belonging to
 * that relation rather than floating in the field.
 */
export const ORBIT_PILL_POSITIONS: readonly number[] = [
  0.58, 0.46, 0.68, 0.36, 0.76, 0.28, 0.84, 0.5,
];
export const ORBIT_PILL_LIFTS: readonly number[] = [
  0, -34, 34, -62, 62, -92, 92, -130, 130, -176, 176,
];

/* -- what the orbit produces --------------------------------------------- */

/**
 * Which side of the centre a mark is drawn on.
 *
 * The relation's own direction, and nothing else: `incoming` means the record
 * runs *into* the focus. Which side of the field that is depends on the script
 * -- incoming reads first, so it is the inline start -- and `placeOrbit` takes
 * `rtl` for exactly that reason. The records are untouched; only the side
 * mirrors.
 */
export type OrbitSide = "incoming" | "outgoing";

/** One card the orbit placed: which record, where, and where its edge lands. */
export interface OrbitCard {
  globalId: string;
  /** The neighbour this card is for; `null` for the centre. */
  related: RelatedEntity | null;
  /** Which side it is on; `null` for the centre, which is on neither. */
  side: OrbitSide | null;
  /** Hops from the centre, as the response counted them. `0` for the centre. */
  hops: number;
  /** The card's rectangle in the field's pixels. `MapOrbit` writes it verbatim. */
  rect: StageRect;
  /** The point on the card's edge that faces the centre: where its edge lands. */
  port: MapPoint;
  /** Whether this card is a further-out chip rather than a hop-1 card. */
  chip: boolean;
}

/** One relation drawn as a path from a card's port to another's (SPEC §4). */
export interface OrbitEdge {
  /** The relation record's own id: unique, so it is the React key as well. */
  key: string;
  /** The relation as the record spells it. Never glossed here. */
  relation: string;
  /** `canonical` or `library_synthetic`, for the head and the dashing. */
  vocabulary: string | null;
  /** How the relation runs, seen from the neighbour. */
  direction: RelationDirection;
  /** The neighbour this edge belongs to. */
  globalId: string;
  /**
   * The `local_id` of the endpoint nearer the centre, or `null` for the focus.
   *
   * The near end of a hop-2 relation is its **parent**, not the focus. Naming
   * the focus there would state a relation the records do not contain, so the
   * pill reads `KU-000026 -> is_part_of` and this is where that name comes
   * from.
   */
  nearId: string | null;
  from: MapPoint;
  to: MapPoint;
  hops: number;
  /** Where the relation's own pill is seated. */
  pill: OrbitPill;
}

/** A relation's horizontal text pill, seated clear of every card (SPEC §4). */
export interface OrbitPill {
  /** The pill's centre. `box` is what is drawn around this point. */
  at: MapPoint;
  /** The rectangle `MapOrbit` writes onto the element, exactly as reserved. */
  box: StageCardBox;
  rect: StageRect;
  /** The dashed leader back to the edge, when the pill was lifted off it. */
  leader: { from: MapPoint; to: MapPoint } | null;
  /**
   * Every seat was taken, and the pill was kept on its path anyway.
   *
   * Reported rather than hidden: dropping the relation would be a silent
   * omission of the one thing the composition exists to state, and drawing it
   * without saying so would let the gate pass a picture with a label over a
   * card.
   */
  crowded: boolean;
}

/** One dashed hop ring, labelled at its foot on the vertical axis (SPEC §4). */
export interface OrbitRing {
  hop: number;
  centre: MapPoint;
  rx: number;
  ry: number;
}

/** Which side is which, said in words rather than left to a bare arrow. */
export interface OrbitSideLabel {
  side: OrbitSide;
  at: MapPoint;
}

/**
 * Why a neighbour the API returned has no card on the field.
 *
 * Four, and every one of them is a fact about *this composition* rather than
 * about a camera. That is the change `T-213` made to the vocabulary: the old
 * policy's `not_loaded` and `off_stage` said "the accumulated graph has no
 * mark for it" and "the camera has panned its mark out of view", and the orbit
 * consults neither -- a neighbour is placed by its direction and its hop
 * count, so a mark the pages have not reached still gets a card. Keeping two
 * reasons no clause can produce would be worse than dropping them: a reason
 * that never fires is a sentence in the interface that can never be true.
 *
 * `unanchored` is the one this composition adds. A hop-2 mark's edge leaves
 * the hop-1 card it is actually joined to; if that parent has no card, the
 * edge has no honest starting point, and drawing it from the centre would put
 * a relation on screen that the records do not contain.
 */
export type StageOmission = "no_room" | "crowded" | "budget" | "unanchored";

/** Every omission reason, in the order the count is rendered. */
export const STAGE_OMISSIONS: readonly StageOmission[] = [
  "no_room",
  "crowded",
  "budget",
  "unanchored",
];

/** What the orbit placed, and what it counted instead. */
export interface OrbitPlacement {
  /** Which of the three compositions this field can hold. */
  tier: OrbitTier;
  /** The field it was laid out in, so a consumer measures the same box. */
  field: StageBox;
  /** The selected entity's card, at the centre. `null` with nothing to place. */
  centre: OrbitCard | null;
  /** The neighbour cards placed, in the related list's own order. */
  cards: readonly OrbitCard[];
  /** One path per placed neighbour, with its pill already seated. */
  edges: readonly OrbitEdge[];
  /** One ring per hop the placement actually drew. */
  rings: readonly OrbitRing[];
  /** The two side labels, or none when there is nothing on that side. */
  sides: readonly OrbitSideLabel[];
  /** How many neighbours were refused a card, by reason. Never a silent drop. */
  omitted: Readonly<Record<StageOmission, number>>;
  /** Neighbours refused a card in total: the sum of `omitted`. */
  omittedTotal: number;
}

export interface OrbitInput {
  /** The selected entity's `global_id`, or `null`. */
  centreId: string | null;
  /** Every neighbour the API returned, in the related list's order. */
  related: readonly RelatedEntity[];
  /** The field: the stage's own box, which is already the field less the drawer. */
  field: StageBox;
  /**
   * The floating chrome's own rectangles, in the field's pixels (`T-212`).
   *
   * Measured by the route from the surfaces marked `data-map-chrome`, never
   * stated as insets: the composition mirrors under `dir="rtl"` and an inset
   * per edge mirrors an already-mirrored coordinate (D-191). The orbit
   * consumes the same rectangles the old policy did rather than growing a
   * second answer to where a card may go.
   */
  obstacles?: readonly StageRect[];
  /**
   * Whether the interface is laid out right to left.
   *
   * Incoming left and outgoing right is a *reading* order, so it mirrors with
   * the script: in Persian the incoming side is the right, where reading
   * starts (D-012).
   */
  rtl?: boolean;
  /** Overridden only to re-measure the policy; defaults to the stated tier. */
  tier?: OrbitTier;
}

/* -- geometry ------------------------------------------------------------ */

/** Whether two rectangles share any pixel. Touching edges do not. */
export function stageCardsOverlap(a: StageRect, b: StageRect): boolean {
  return a.left < b.right && b.left < a.right && a.top < b.bottom && b.top < a.bottom;
}

/** Whether a rectangle is wholly inside the field, inset by the stated margin. */
export function fitsField(rect: StageRect, field: StageBox, inset: number): boolean {
  return (
    rect.left >= inset &&
    rect.top >= inset &&
    rect.right <= field.width - inset &&
    rect.bottom <= field.height - inset
  );
}

/** Whether a rectangle is clear of every floating control on the field. */
export function clearsChrome(rect: StageRect, obstacles: readonly StageRect[]): boolean {
  return !obstacles.some((chrome) => stageCardsOverlap(rect, chrome));
}

/** A box centred on a point. */
function boxAt(point: MapPoint, box: StageCardBox): StageRect {
  return {
    left: point.x - box.width / 2,
    top: point.y - box.height / 2,
    right: point.x + box.width / 2,
    bottom: point.y + box.height / 2,
  };
}

/**
 * A point on the cubic an edge is drawn along.
 *
 * The same curve `MapOrbit` writes into the path, and the same one a pill
 * walks to find its seat -- one definition, because a pill seated against a
 * different curve from the one drawn is a pill beside nothing.
 */
export function orbitPointOn(from: MapPoint, to: MapPoint, u: number): MapPoint {
  const bend = (to.y - from.y) * 0.12;
  const p1 = { x: from.x + (to.x - from.x) * 0.45, y: from.y + bend };
  const p2 = { x: from.x + (to.x - from.x) * 0.55, y: to.y - bend };
  const v = 1 - u;
  return {
    x: v * v * v * from.x + 3 * v * v * u * p1.x + 3 * v * u * u * p2.x + u * u * u * to.x,
    y: v * v * v * from.y + 3 * v * v * u * p1.y + 3 * v * u * u * p2.y + u * u * u * to.y,
  };
}

/** The cubic's own control points, so the path drawn is the path walked. */
export function orbitCurve(from: MapPoint, to: MapPoint): {
  p1: MapPoint;
  p2: MapPoint;
} {
  const bend = (to.y - from.y) * 0.12;
  return {
    p1: { x: from.x + (to.x - from.x) * 0.45, y: from.y + bend },
    p2: { x: from.x + (to.x - from.x) * 0.55, y: to.y - bend },
  };
}

/* -- the layout ---------------------------------------------------------- */

function noOmissions(): Record<StageOmission, number> {
  return { no_room: 0, crowded: 0, budget: 0, unanchored: 0 };
}

/**
 * The same relation, seen from the endpoint nearer the centre.
 *
 * `ActiveRelation.direction` is stated from the entity the relation is
 * *listed under*, which for a `RelatedEntity` is the neighbour: `exemplifies`
 * running `KU-000029 -> KU-000028` is `outgoing` in that neighbour's row. The
 * composition is about the **focus**, and from the focus that same edge is
 * `incoming`. Inverting once, here, is what makes "incoming relations to the
 * inline start" mean what ADR 0006 clause 3 says it means -- and what makes
 * the pill read `exemplifies -> focus` rather than the other way round.
 *
 * Read as often as it is written, so it is a function rather than a comment
 * at two call sites: the side and the pill must never disagree about which
 * way one edge runs.
 */
function fromNearEnd(direction: RelationDirection): RelationDirection {
  if (direction === "outgoing") return "incoming";
  if (direction === "incoming") return "outgoing";
  return "self";
}

/**
 * Which side a neighbour belongs on, from its own records.
 *
 * A hop-1 neighbour is placed by the direction of the relation joining it to
 * the centre, *seen from the centre*; a further-out one has no such relation,
 * so it takes its parent's side and its edge leaves its parent's card. `null`
 * when the records state neither -- a self-loop carries no direction to place,
 * and inventing one is exactly what SPEC §4 forbids.
 */
function sideOf(item: RelatedEntity, sides: Map<string, OrbitSide>): OrbitSide | null {
  const direct = item.toCentre[0]?.direction;
  if (direct !== undefined) {
    const seen = fromNearEnd(direct);
    if (seen === "incoming" || seen === "outgoing") return seen;
  }
  if (item.parentId !== null) return sides.get(item.parentId) ?? null;
  return null;
}

/** Evenly spaced within the band, so the reading order is the list's order. */
function bandPosition(index: number, count: number): number {
  if (count <= 1) return 0;
  return (index / (count - 1)) * 2 - 1;
}

/**
 * Lay the Directional Orbit out over one selection (`T-213`, D-152).
 *
 * Pure, and pure for the same reason the policy it replaces was: it takes a
 * field, a neighbourhood and the chrome's rectangles and returns a decision,
 * so the composition is asserted directly rather than inferred from what a
 * canvas happened to draw. Given the same three it returns the same picture,
 * which is what makes changing focus and coming back to it stable.
 */
export function placeOrbit(input: OrbitInput): OrbitPlacement {
  const field = input.field;
  const tier = input.tier ?? orbitTier(field.width);
  const geometry = ORBIT_TIERS[tier];
  const obstacles = input.obstacles ?? [];
  const rtl = input.rtl ?? false;
  const omitted = noOmissions();
  const empty: OrbitPlacement = {
    tier,
    field,
    centre: null,
    cards: [],
    edges: [],
    rings: [],
    sides: [],
    omitted,
    omittedTotal: 0,
  };

  // An unmeasured field places nothing rather than placing everything at the
  // origin: the container is sized in CSS and measured after layout, so this
  // is the first render, not an error. The `stack` tier places nothing either,
  // and counts nothing: its composition is the route's own document, where
  // every neighbour is a row and none is dropped (SPEC §5).
  if (tier === "stack" || field.width <= 0 || field.height <= 0) return empty;
  if (input.centreId === null) return empty;

  const cx = field.width / 2;
  /** Incoming reads first, so it is the inline start: the left, mirrored. */
  const flip = rtl ? -1 : 1;
  const dirOf = (side: OrbitSide): number => (side === "incoming" ? -1 : 1) * flip;
  const scale = Math.min(1, field.width / ORBIT_REFERENCE_WIDTH);

  // The band is bounded by the room a card of this tier actually needs, at
  // both ends, and by the chrome the route keeps at each of them. A band
  // computed from the field's own height would put the outermost card's top
  // edge under the search surface.
  /*
   * The composition's own centre, which is the field's unless a control is
   * standing there (`T-213`).
   *
   * The centre card is the one card D-132 guarantees and the one thing a
   * reader asked for, so it may not be painted over -- that is the same WCAG
   * 2.2 AA *Focus Not Obscured* failure SPEC §8 cites and §13 records
   * `T-212` fixing one surface over. The field's exact middle is preferred
   * and tried first; if the chrome is there, the whole composition slides
   * along the block axis by stated steps until the card is clear, and
   * everything else -- bands, arms, rings, side labels -- is laid out around
   * wherever that lands. Sliding rather than shrinking, and on the block axis
   * only: moving it inline would put the centre nearer one side than the
   * other, and the two sides are the composition's meaning.
   *
   * If no offset clears, the middle stands. A selection with its card under a
   * control is bad; a selection with no card at all is worse, and the last
   * resort is the one the old policy chose for the same reason.
   */
  const middle = field.height / 2;
  const clearCentre = (): number => {
    for (let step = 0; step <= ORBIT_CENTRE_TRIES; step += 1) {
      for (const direction of step === 0 ? [0] : [1, -1]) {
        const candidate = middle + direction * step * ORBIT_CENTRE_STEP;
        const rect = boxAt({ x: cx, y: candidate }, geometry.primaryBox);
        if (fitsField(rect, field, ORBIT_FIELD_INSET) && clearsChrome(rect, obstacles)) {
          return candidate;
        }
      }
    }
    return middle;
  };
  const cy = clearCentre();

  const bandFor = (box: StageCardBox, limit: number): number =>
    Math.max(
      0,
      Math.min(
        limit,
        cy - geometry.topInset - box.height / 2,
        field.height - cy - geometry.bottomInset - box.height / 2,
      ),
    );
  const bandY = bandFor(geometry.cardBox, ORBIT_BAND_MAX);

  const taken: StageRect[] = [];

  // The centre first, and it takes its own rectangle: the selected statement
  // is the card D-132 guarantees, so a neighbour gives way to it rather than
  // landing on top of it. It is at the field's centre by definition -- that is
  // the whole composition -- so it has no orientation to choose and no way to
  // be refused.
  const centre: OrbitCard = {
    globalId: input.centreId,
    related: null,
    side: null,
    hops: 0,
    rect: boxAt({ x: cx, y: cy }, geometry.primaryBox),
    port: { x: cx, y: cy },
    chip: false,
  };
  taken.push(centre.rect);

  // Sides, from the records. Hop-1 by its own relation to the centre, further
  // out by its parent's side -- so the pass is in hop order, which the related
  // list's own order already guarantees (`neighbourhood.ts` sorts by hops
  // first).
  const sides = new Map<string, OrbitSide>();
  const placeable: RelatedEntity[] = [];
  for (const item of input.related) {
    const side = sideOf(item, sides);
    if (side === null) {
      // No direction to place it by, and none to invent. It keeps its row.
      omitted.unanchored += 1;
      continue;
    }
    sides.set(item.globalId, side);
    if (item.hops > 1 && !geometry.showFar) {
      omitted.no_room += 1;
      continue;
    }
    placeable.push(item);
  }

  // Per side and per hop, because the band is shared by everything at one
  // radius: two cards at the same hop on the same side are two rows of one
  // column, and a chip a ring further out belongs in the gaps between them.
  const groups = new Map<string, RelatedEntity[]>();
  for (const item of placeable) {
    const key = `${sides.get(item.globalId) ?? "incoming"}:${item.hops}`;
    const group = groups.get(key);
    if (group === undefined) groups.set(key, [item]);
    else group.push(item);
  }

  const cards: OrbitCard[] = [];
  const placed = new Map<string, OrbitCard>();
  const hopsDrawn = new Set<number>();

  for (const [key, group] of groups) {
    const side = key.startsWith("incoming") ? "incoming" : "outgoing";
    const hops = group[0]?.hops ?? 1;
    const chip = hops > 1;
    const box = chip ? geometry.chipBox : geometry.cardBox;
    const dir = dirOf(side);
    // Further-out rings sit in the gaps between the bands nearer in, so a chip
    // and a card can never share a row.
    const offset = chip ? 0.5 / Math.max(group.length, 1) : 0;
    // The band is this box's, not the card's: a chip is half a card's height,
    // so it reaches further up and down the field before its own top edge
    // meets the chrome. Computed from the box that is actually drawn, because
    // a band stated once for the tallest card either wastes the field or
    // refuses a chip that fitted.
    const widest = bandFor(box, chip ? ORBIT_BAND_MAX + 120 : ORBIT_BAND_MAX);
    /*
     * How many of this group the composition will place.
     *
     * Two limits, and they answer different questions. `perSide` is the
     * *tier's*: SPEC §5 gives `compact` two cards a side whatever the field
     * does. The band's capacity is the *field's*: at 1280x720 the compact band
     * is 144 px between its extremes and its card is 240 px tall, so asking
     * for two placed them 144 px apart, each overlapped the other, and both
     * were refused -- one card a side would have been drawn. A tier that ends
     * up with nothing because it asked for two is worse at its job than one
     * that asks for what fits.
     *
     * The band's *extent* is what holds them, and the extent is wider than the
     * band: the outermost card's centre is `span` from the middle and its own
     * box reaches half a card further, at both ends.
     */
    const allowed = hops === 1 ? geometry.perSide : Number.POSITIVE_INFINITY;
    /** How many cards of this box a band of this width holds, in rows. */
    const capacityOf = (span: number): number =>
      Math.max(
        1,
        Math.floor((2 * span + box.height + ORBIT_CARD_GAP) / (box.height + ORBIT_CARD_GAP)),
      );

    /**
     * Try to seat this side's cards within one band, without committing.
     *
     * Pure over `taken`, because the band itself is searched: a band is only
     * as wide as the field leaves it once the floating chrome is on it, and
     * finding that out means trying one and looking at the answer. Committing
     * as it went would leave the cards of a rejected band behind.
     */
    const attempt = (
      span: number,
    ): { cards: OrbitCard[]; crowded: number; noRoom: number; budget: number } => {
      // The band's own capacity, not the widest band's: a narrower band holds
      // fewer rows, and spacing the wider band's count into it puts every card
      // on top of the next. That was the last two refusals at 2852x1688.
      const shown = Math.min(group.length, allowed, capacityOf(span));
      const seatedCards: OrbitCard[] = [];
      const claimed: StageRect[] = [...taken];
      let crowded = 0;
      let noRoom = 0;
      for (let index = 0; index < shown; index += 1) {
        const item = group[index];
        if (item === undefined) continue;
        // Clamped, because the chips' half-row offset would otherwise push the
        // outermost one past the band it was measured for and straight into a
        // refusal the geometry could have avoided.
        const t = Math.max(-1, Math.min(1, bandPosition(index, shown) + offset));
        const y = cy + t * span;
        /*
         * The arm, floored at the centre card's own reach.
         *
         * The stated arms are the review viewport's and scale down with the
         * field, but the centre card does not scale with them -- it is the
         * tier's box -- so on a narrow field a scaled arm puts a neighbour's
         * port *inside* the card it is supposed to point away from. The floor
         * is arithmetic: half the centre card plus the gap every card keeps.
         * Without it the compact tier refused every card at its own minimum
         * width and counted them all, which is honest and useless.
         */
        const minArm = geometry.primaryBox.width / 2 + ORBIT_CARD_GAP;
        const baseArm =
          Math.max(
            minArm,
            (geometry.armNear + geometry.armFar * Math.max(0, 1 - Math.abs(t))) * scale,
          ) +
          (hops - 1) * geometry.armStep * scale;

        let seated: OrbitCard | null = null;
        let blockedByCard = false;
        for (let step = 0; step <= ORBIT_ARM_TRIES; step += 1) {
          const portX = cx + dir * (baseArm + step * ORBIT_ARM_STEP);
          // The card is laid out so its port touches the orbit and its body
          // extends away from the centre. That is geometry rather than
          // writing direction, so it is computed from `dir`.
          const left = dir === -1 ? portX - box.width : portX;
          const rect = {
            left,
            top: y - box.height / 2,
            right: left + box.width,
            bottom: y + box.height / 2,
          };
          if (!fitsField(rect, field, ORBIT_FIELD_INSET) || !clearsChrome(rect, obstacles)) {
            continue;
          }
          // Half the gap on each side, so *two* cards are a whole gap apart --
          // which is the number the band's own capacity was computed with. A
          // full gap each side separates them by two, and the browser priced
          // that: six cards spaced at the capacity's own pitch each overlapped
          // their neighbour by 8 px and were pushed off the field instead.
          const grown = {
            left: rect.left - ORBIT_CARD_GAP / 2,
            top: rect.top - ORBIT_CARD_GAP / 2,
            right: rect.right + ORBIT_CARD_GAP / 2,
            bottom: rect.bottom + ORBIT_CARD_GAP / 2,
          };
          if (claimed.some((other) => stageCardsOverlap(grown, other))) {
            blockedByCard = true;
            continue;
          }
          seated = {
            globalId: item.globalId,
            related: item,
            side,
            hops,
            rect,
            port: { x: portX, y },
            chip,
          };
          break;
        }

        if (seated === null) {
          // The two clauses in the order the old policy stated them, so the
          // reason reported is the real one: a card that never had room at
          // all is not the same answer as one another card was already in.
          if (blockedByCard) crowded += 1;
          else noRoom += 1;
          continue;
        }
        claimed.push(seated.rect);
        seatedCards.push(seated);
      }
      return { cards: seatedCards, crowded, noRoom, budget: group.length - shown };
    };

    /*
     * The band, clamped so no card runs under floating chrome (SPEC §4).
     *
     * The clamp is a *search* rather than an inset, and the browser is why.
     * `topInset` reserves room for the chrome in the abstract; the search rail
     * at the `full` tier is 424 px tall, nearly three times it, and the card
     * at the band's top edge landed under it. Pushing that card outward along
     * its arm -- the only adjustment the placement allows -- moves it towards
     * the field's own inline edge, which on the incoming side is *where the
     * rail is*, so it walked further under the surface it was escaping and
     * was finally refused for leaving the field. Three of six.
     *
     * A narrower band moves the whole side inwards instead, which is the
     * adjustment SPEC §4 actually names, and it keeps every card in its own
     * row and on its own side. The widest band that seats the most cards
     * wins; the steps are stated so the answer is reproducible.
     */
    let best = attempt(widest);
    if (best.crowded + best.noRoom > 0) {
      for (const factor of ORBIT_BAND_STEPS) {
        const candidate = attempt(widest * factor);
        if (candidate.cards.length > best.cards.length) best = candidate;
        if (best.crowded + best.noRoom === 0) break;
      }
    }

    omitted.crowded += best.crowded;
    omitted.no_room += best.noRoom;
    omitted.budget += best.budget;
    for (const card of best.cards) {
      taken.push(card.rect);
      cards.push(card);
      placed.set(card.globalId, card);
      hopsDrawn.add(card.hops);
    }
  }

  // Edges and their pills, after every card exists. Two passes on purpose: a
  // pill may only be seated where no card is, and a single pass puts a
  // relation label on top of a neighbour placed after it -- the exact "no
  // label over readable card content" clause the gate names.
  const edges: OrbitEdge[] = [];
  const pillRects: StageRect[] = [];
  const unanchored: OrbitCard[] = [];

  for (const card of cards) {
    const item = card.related;
    if (item === null) continue;
    const relation = (item.hops === 1 ? item.toCentre[0] : item.toParent[0]) ?? null;
    const parent = item.hops === 1 ? centre : (placed.get(item.parentId ?? "") ?? null);
    if (relation === null || parent === null) {
      // Its nearer endpoint has no card, so the edge has no honest starting
      // point. The card comes back off the field with it: a mark with no
      // relation drawn to it is a mark whose place in the orbit states a hop
      // and a side it cannot support.
      unanchored.push(card);
      continue;
    }

    const from =
      parent === centre
        ? { x: cx + dirOf(card.side ?? "outgoing") * (geometry.primaryBox.width / 2), y: cy }
        : parent.port;
    const to = card.port;

    const nearId = parent === centre ? null : (parent.related?.record.local_id ?? parent.globalId);
    const pill = seatPill({
      from,
      to,
      field,
      obstacles,
      cards: taken,
      pills: pillRects,
      box: orbitPillBox(relation.record.relation, nearId),
    });
    pillRects.push(pill.rect);

    edges.push({
      key: relation.record.id,
      relation: relation.record.relation,
      vocabulary: relation.record.relation_vocabulary ?? null,
      // Stated from the endpoint nearer the centre, so the pill reads
      // `exemplifies -> focus` and the side it is drawn on agrees with it.
      direction: fromNearEnd(relation.direction),
      globalId: card.globalId,
      nearId,
      from,
      to,
      hops: card.hops,
      pill,
    });
  }

  // A card whose edge could not be drawn is withdrawn and counted, so the
  // picture never shows a mark the composition cannot explain.
  //
  // Returned in the related list's own order rather than in the order the
  // sides happened to be laid out, so "the third card" means the same thing
  // on the field and in the list beside it.
  const order = new Map(input.related.map((item, index) => [item.globalId, index]));
  const drawn = cards
    .filter((card) => !unanchored.includes(card))
    .sort((left, right) => (order.get(left.globalId) ?? 0) - (order.get(right.globalId) ?? 0));
  omitted.unanchored += unanchored.length;

  const rings: OrbitRing[] = [...hopsDrawn]
    .filter((hop) => drawn.some((card) => card.hops === hop))
    .sort((left, right) => left - right)
    .map((hop) => {
      const reach = Math.max(
        ...drawn
          .filter((card) => card.hops === hop)
          .map((card) => Math.abs(card.port.x - cx)),
      );
      return {
        hop,
        centre: { x: cx, y: cy },
        rx: reach,
        ry: Math.min(bandY + (hop === 1 ? 90 : 190), cy - ORBIT_FIELD_INSET),
      };
    });

  const sideLabels: OrbitSideLabel[] = (["incoming", "outgoing"] as const)
    .filter((side) => drawn.some((card) => card.side === side))
    .map((side) => ({
      side,
      at: {
        x: cx + dirOf(side) * (geometry.armNear + geometry.armFar * 0.5) * scale,
        y: Math.max(ORBIT_FIELD_INSET, geometry.topInset / 2),
      },
    }));

  return {
    tier,
    field,
    centre,
    cards: drawn,
    edges,
    rings,
    sides: sideLabels,
    omitted,
    omittedTotal: STAGE_OMISSIONS.reduce((sum, reason) => sum + omitted[reason], 0),
  };
}

/**
 * Where one relation's pill can sit without covering a card or another pill.
 *
 * Walked rather than computed: the seats are `ORBIT_PILL_POSITIONS` along the
 * edge's own curve and `ORBIT_PILL_LIFTS` off it, tried in that order, and the
 * first that lands clear of every card, every pill already seated, the
 * floating chrome and the field's own edge is the one taken.
 *
 * When every seat is taken the pill stays on its path and says so. Dropping it
 * would remove the relation -- the one thing SPEC §4 insists a reader can
 * judge before opening a card -- and moving it somewhere arbitrary would put a
 * label over readable text with nothing to notice it.
 */
function seatPill({
  from,
  to,
  field,
  obstacles,
  cards,
  pills,
  box,
}: {
  from: MapPoint;
  to: MapPoint;
  field: StageBox;
  obstacles: readonly StageRect[];
  cards: readonly StageRect[];
  pills: readonly StageRect[];
  box: StageCardBox;
}): OrbitPill {
  const half = {
    width: box.width / 2 + ORBIT_PILL_GAP,
    height: box.height / 2 + ORBIT_PILL_GAP,
  };
  for (const lift of ORBIT_PILL_LIFTS) {
    for (const u of ORBIT_PILL_POSITIONS) {
      const on = orbitPointOn(from, to, u);
      const at = { x: on.x, y: on.y + lift };
      const rect = boxAt(at, { width: half.width * 2, height: half.height * 2 });
      if (!fitsField(rect, field, ORBIT_PILL_GAP)) continue;
      if (!clearsChrome(rect, obstacles)) continue;
      if (cards.some((card) => stageCardsOverlap(rect, card))) continue;
      if (pills.some((other) => stageCardsOverlap(rect, other))) continue;
      return {
        at,
        box,
        rect,
        leader:
          lift === 0
            ? null
            : {
                from: on,
                to: { x: at.x, y: at.y - Math.sign(lift) * (box.height / 2) },
              },
        crowded: false,
      };
    }
  }
  const on = orbitPointOn(from, to, ORBIT_PILL_POSITIONS[0] ?? 0.5);
  return {
    at: on,
    box,
    rect: boxAt(on, { width: half.width * 2, height: half.height * 2 }),
    leader: null,
    crowded: true,
  };
}

/**
 * Placed plus counted equals the neighbours the API returned.
 *
 * The invariant R20 rests on, written beside the policy rather than only in
 * the suite that checks it, because it is the clause every tier has to keep
 * and the one a future change is most likely to break quietly.
 */
export function orbitAccountsFor(
  placement: OrbitPlacement,
  related: readonly RelatedEntity[],
): boolean {
  if (placement.tier === "stack") return placement.omittedTotal === 0;
  return placement.cards.length + placement.omittedTotal === related.length;
}
