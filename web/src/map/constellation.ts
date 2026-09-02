/**
 * The stated density policy for on-stage cards (`T-207`, D-132, risk R20).
 *
 * D-132 permits "one primary selected Knowledge Card, at most one transient
 * Peek card, active relation labels, and compact neighbour previews **under a
 * stated density policy**". This module is that policy, written as a function
 * so that "which cards are on the stage" has one answer, is reproducible, and
 * can be tested without a renderer.
 *
 * The rule has four clauses, applied in this order to the related list in its
 * own deterministic order (`neighbourhood.ts`), and each of them is *counted*:
 *
 * 1. **Not loaded.** A card is anchored to a mark, and only the accumulated
 *    graph has marks with positions. A neighbour the pages have not reached
 *    has nowhere on the stage to be, so it gets no card. (It keeps its row in
 *    the related list, and that row says so.)
 * 2. **Off the stage.** The camera can be panned or zoomed so a mark is
 *    outside the container. A card pinned to the edge would point at a node
 *    that is not there.
 * 3. **Crowded.** At most one card per cell of a fixed grid over the stage --
 *    the same device Sigma's own `labelDensity`/`labelGridCellSize` uses for
 *    labels, for the same reason: two cards in one place are less readable
 *    than one, and the second one is the one that goes.
 * 4. **Over budget.** A hard cap on cards, because the graph must stay visible
 *    through them: an HTML card per node is the failure mode R20 names.
 *
 * **A refused card is never a hidden entity.** Every clause above returns a
 * *reason*, the reasons are counted, and the count is rendered beside the
 * stage; the entity itself is in the semantic related list either way, which
 * is the completeness path D-132 requires and the acceptance criterion "no
 * neighbour silently disappears" is judged on.
 *
 * The numbers are starting values chosen to keep the topology visible, in the
 * same spirit as `PREVIEW_LIMIT` and `MAP_LABEL_NEIGHBOUR_BUDGET`, and
 * `T-209` measures them on the real route in a real browser. They are stated
 * here, once, so re-measuring is an edit rather than an excavation.
 */

import type { MapPoint } from "./mapSession";
import type { RelatedEntity } from "./neighbourhood";

/**
 * How many neighbour cards the stage may carry at once.
 *
 * Four, not twelve. A label is a line of text beside a mark and
 * `MAP_LABEL_NEIGHBOUR_BUDGET` can afford twelve of them; a card is a block
 * with a statement, a relation and a badge row, and five of those over a
 * 900x600 stage is a page of cards with a graph somewhere underneath. The two
 * budgets are deliberately different numbers for deliberately different
 * things, and the labels are still doing their own job for the neighbours that
 * have no card.
 */
export const MAP_STAGE_CARD_BUDGET = 4;

/**
 * One card per cell of this grid, in stage pixels.
 *
 * Larger than Sigma's 180 px label cell because a card is larger than a label.
 * It is the card's own footprint plus a gutter: two anchors closer together
 * than this produce two overlapping cards, and the second is refused as
 * `crowded` rather than drawn on top of the first.
 */
export const MAP_STAGE_CARD_CELL = 240;

/**
 * How far inside the stage an anchor must be for its card to be placed.
 *
 * A mark exactly on the edge has a card that is half outside the container,
 * and the container clips. This is not a layout nicety: a clipped card shows
 * the first two words of a statement and hides the visible truncation marker,
 * which would be the one kind of silent cut D-131 forbids.
 */
export const MAP_STAGE_CARD_INSET = 24;

/**
 * How much of a statement a card on the stage may show.
 *
 * Two numbers, both smaller than the rail's `PREVIEW_LIMIT`, because a card on
 * the stage is competing with the graph for the same pixels: the primary card
 * gets enough to read the claim, a neighbour preview gets enough to decide
 * whether to open it. The cut itself is `previewText` -- the one cutter, with
 * the cut marked (D-131, §8.6) -- so these are budgets, not a second policy.
 */
export const MAP_STAGE_PRIMARY_CHARS = 200;
export const MAP_STAGE_NEIGHBOUR_CHARS = 110;

/**
 * How long after the last frame the stage is considered settled, in
 * milliseconds.
 *
 * Cards are anchored to marks, so they have to be re-placed when the camera
 * moves -- and re-placing them *per frame* would re-render the related list
 * and the search rail sixty times a second for a pan. The Map already has a
 * precedent for the alternative: `hideLabelsOnMove: true` drops labels while
 * the camera is moving and brings them back when it stops, because text that
 * reflows every frame is unreadable anyway. Cards are the same argument, one
 * size larger, so they follow the same rule.
 *
 * A trailing delay rather than a periodic one: the last frame of a gesture is
 * the one whose positions are worth placing against.
 */
export const MAP_STAGE_SETTLE_MS = 150;

/** Why an entity that the API returned has no card on the stage. */
export type StageOmission = "not_loaded" | "off_stage" | "crowded" | "budget";

/** Every omission reason, in the order the count is rendered. */
export const STAGE_OMISSIONS: readonly StageOmission[] = [
  "not_loaded",
  "off_stage",
  "crowded",
  "budget",
];

/** One placed card: which entity, where, and which way it opens. */
export interface StageCard {
  globalId: string;
  /** The neighbour this card is for; `null` for the primary selected card. */
  related: RelatedEntity | null;
  /** The anchor, in pixels inside the stage. */
  point: MapPoint;
  /**
   * Which side of the anchor the card grows towards.
   *
   * Derived from which half of the stage the anchor is in, so a card near the
   * right edge opens leftwards instead of being clipped. Logical names rather
   * than left/right, because the Map is laid out in Persian as well (D-012).
   */
  align: "start" | "end";
  /** Whether the anchor is in the lower half, so the card opens upwards. */
  above: boolean;
}

export interface StagePlacement {
  /** The selected entity's card, when its mark is drawn and on the stage. */
  primary: StageCard | null;
  /** The neighbour cards the policy placed, in related-list order. */
  cards: readonly StageCard[];
  /** How many neighbours were refused a card, by reason. Never a silent drop. */
  omitted: Readonly<Record<StageOmission, number>>;
  /** Neighbours refused a card in total: the sum of `omitted`. */
  omittedTotal: number;
}

/** The stage's own pixel box. Zero means "not measured yet", and places nothing. */
export interface StageBox {
  width: number;
  height: number;
}

export interface ConstellationInput {
  /** The selected entity's `global_id`, or `null`. */
  centreId: string | null;
  /** Every neighbour the API returned, in the related list's order. */
  related: readonly RelatedEntity[];
  /** Where a node's mark is, in stage pixels, or `null`. `MapSession.nodePosition`. */
  position: (globalId: string) => MapPoint | null;
  stage: StageBox;
  /** Overridden only to re-measure the policy; defaults to the stated budget. */
  budget?: number;
  cell?: number;
  inset?: number;
}

function noOmissions(): Record<StageOmission, number> {
  return { not_loaded: 0, off_stage: 0, crowded: 0, budget: 0 };
}

/**
 * Apply the density policy to one selection.
 *
 * Pure, and pure on purpose: it takes a position lookup and a box and returns
 * a decision, so the policy is asserted directly rather than inferred from
 * what a canvas happened to draw.
 */
export function placeConstellation(input: ConstellationInput): StagePlacement {
  const budget = input.budget ?? MAP_STAGE_CARD_BUDGET;
  const cell = input.cell ?? MAP_STAGE_CARD_CELL;
  const inset = input.inset ?? MAP_STAGE_CARD_INSET;
  const { width, height } = input.stage;
  const omitted = noOmissions();

  const cards: StageCard[] = [];
  const taken = new Set<string>();
  const cellOf = (point: MapPoint) =>
    `${Math.floor(point.x / cell)}:${Math.floor(point.y / cell)}`;

  /**
   * Where a card for this entity would go, or why it cannot have one.
   *
   * Deliberately free of side effects: the two clauses that depend on the
   * cards already placed -- crowding and the budget -- are applied by the
   * caller, so an entity that has no mark at all is reported as
   * `not_loaded` rather than as whichever clause happened to be checked
   * first. A reason that is not the real reason is worse than no reason.
   */
  const anchor = (globalId: string): StageCard | StageOmission => {
    const point = input.position(globalId);
    if (point === null) return "not_loaded";
    // An unmeasured stage places nothing rather than placing everything in one
    // corner: the container is sized in CSS and measured after layout, so this
    // is the first render, not an error.
    if (width <= 0 || height <= 0) return "off_stage";
    if (
      point.x < inset ||
      point.y < inset ||
      point.x > width - inset ||
      point.y > height - inset
    ) {
      return "off_stage";
    }
    return {
      globalId,
      related: null,
      point,
      align: point.x > width / 2 ? "end" : "start",
      above: point.y > height / 2,
    };
  };

  // The primary card first, and it takes its cell: the selected statement is
  // the one card D-132 guarantees, so a neighbour gives way to it rather than
  // landing on top of it. It does not consume the neighbour budget, because it
  // is not a neighbour.
  const centre = input.centreId === null ? "not_loaded" : anchor(input.centreId);
  const primary = typeof centre === "string" ? null : centre;
  if (primary !== null) taken.add(cellOf(primary.point));

  for (const related of input.related) {
    const candidate = anchor(related.globalId);
    if (typeof candidate === "string") {
      omitted[candidate] += 1;
      continue;
    }
    // Crowding before the budget, so a card that would have overlapped one
    // already placed costs nothing: the budget is spent on cards a reader can
    // actually read.
    if (taken.has(cellOf(candidate.point))) {
      omitted.crowded += 1;
      continue;
    }
    if (cards.length >= budget) {
      omitted.budget += 1;
      continue;
    }
    taken.add(cellOf(candidate.point));
    cards.push({ ...candidate, related });
  }

  return {
    primary,
    cards,
    omitted,
    omittedTotal: STAGE_OMISSIONS.reduce((sum, reason) => sum + omitted[reason], 0),
  };
}
