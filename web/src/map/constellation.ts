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
 * 3. **No room.** The mark is on the stage but the *card* would not be: every
 *    direction it could open in leaves it hanging over the edge. `T-209` saw
 *    this in the shipped UI -- two cards anchored near the top of the stage
 *    opened upwards, spilled out of it, and had their first line of text
 *    covered by the panel above, which is precisely the *silent* cut D-131
 *    forbids: nothing on screen said the statement had been shortened,
 *    because it had not been -- it was hidden.
 * 4. **Crowded.** A card that cannot be opened in any of the directions that
 *    fit without covering a card already placed is refused,
 *    and the second one is the one that goes: two cards in one place are less
 *    readable than one, and the lower one is unreadable *and* still claims to
 *    point at a mark. The test is the card's own footprint, measured in a
 *    browser (`T-209`, D-145) -- it used to be a cell of a fixed grid, the
 *    device Sigma's `labelDensity`/`labelGridCellSize` uses for labels, and
 *    on the real fan-out that grid did both halves of its job wrong: it
 *    refused seven of eight neighbours whose cards would have fitted, and
 *    placed two that overlapped by two thirds of a card, because two anchors
 *    either side of a cell boundary can be one pixel apart while two in one
 *    cell can be 300 apart. A grid answers "same cell?"; the question is
 *    "same pixels?".
 * 5. **Over budget.** A hard cap on cards, because the graph must stay visible
 *    through them: an HTML card per node is the failure mode R20 names.
 *
 * **A refused card is never a hidden entity.** Every clause above returns a
 * *reason*, the reasons are counted, and the count is rendered beside the
 * stage; the entity itself is in the semantic related list either way, which
 * is the completeness path D-132 requires and the acceptance criterion "no
 * neighbour silently disappears" is judged on.
 *
 * `T-209` measured every number here on the real route in Chrome. The budget,
 * the inset and the settle delay were kept; the grid cell was not, and what
 * replaced it is stated below. They are all stated here, once, so
 * re-measuring is an edit rather than an excavation.
 */

import type { MapPoint } from "./mapSession";
import type { RelatedEntity } from "./neighbourhood";

/**
 * How many neighbour cards the stage may carry at once.
 *
 * Four. A label is a line of text beside a mark; a card is a block with a
 * statement, a relation and a badge row, and five of those over a 900x600
 * stage is a page of cards with a graph somewhere underneath. The labels are
 * still doing their own job for the neighbours that have no card.
 *
 * D-187: this said "four, not twelve" and pointed at
 * `MAP_LABEL_NEIGHBOUR_BUDGET` for the twelve — which D-145 had already
 * lowered to four, in the same file, a hundred and thirty lines away. The two
 * budgets happen to be the same number today; they remain separate constants
 * because they bound different things, and neither is derived from the other.
 */
export const MAP_STAGE_CARD_BUDGET = 4;

/** A card's footprint on the stage, in pixels. */
export interface StageCardBox {
  width: number;
  height: number;
}

/**
 * How much room a card actually takes, measured in a browser (`T-209`).
 *
 * Not a preference: these are the boxes Chrome laid out on the real route at
 * a 1216x630 stage. The width is the CSS number -- `.map__card` is
 * `min(20rem, 60%)` and `.map__card--primary` is `min(26rem, 70%)`. The
 * height is an **upper bound over what the library actually produces**, and
 * that is the important word: the first walk declared 248 from one sample and
 * then found a card 295 px tall, because a neighbour's relation cue can list
 * several relations and wrap. A reserved rectangle smaller than the drawn
 * card is a fit test that passes while the card hangs over the edge, so the
 * number is the tallest card seen across eighteen focuses, rounded up.
 *
 * A stated consequence, since it is a trade rather than an oversight: a card
 * needs `height + gap + inset` of clear stage above or below its mark, so on
 * a short stage -- a phone's 360 px, say -- almost no mark has room and the
 * constellation collapses to the focused card alone. Every neighbour is then
 * counted as `no_room` and every one of them is still in the related list
 * (R20). The alternative, a second pair of boxes for the narrow breakpoint,
 * would put `base.css`'s 48rem in TypeScript as well, and refusing a card is
 * the safe direction: a 296 px card on a 360 px stage is the graph with a
 * card over it.
 */
export const MAP_STAGE_CARD_BOX: StageCardBox = { width: 320, height: 296 };
export const MAP_STAGE_PRIMARY_BOX: StageCardBox = { width: 416, height: 176 };

/**
 * The gap a card leaves between itself and the mark it points at.
 *
 * `MapConstellation` writes it into the transform; the policy needs the same
 * number to know where the card's box actually lands, and one constant is
 * what keeps the drawn card and the reserved box the same rectangle.
 */
export const MAP_STAGE_CARD_GAP = 12;

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

/**
 * Why an entity that the API returned has no card on the stage.
 *
 * Five, and the fifth is `T-209`'s: `off_stage` means the *mark* is not on the
 * stage, `no_room` means the mark is but its card would not be. Collapsing
 * them would tell a reader to pan the camera when panning is not the problem,
 * and "a reason that is not the real reason is worse than no reason".
 */
export type StageOmission = "not_loaded" | "off_stage" | "no_room" | "crowded" | "budget";

/** Every omission reason, in the order the count is rendered. */
export const STAGE_OMISSIONS: readonly StageOmission[] = [
  "not_loaded",
  "off_stage",
  "no_room",
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
  /** The neighbour card's footprint. Defaults to what `T-209` measured. */
  box?: StageCardBox;
  /** The primary card's footprint, which is the wider one. */
  primaryBox?: StageCardBox;
  inset?: number;
}

function noOmissions(): Record<StageOmission, number> {
  return { not_loaded: 0, off_stage: 0, no_room: 0, crowded: 0, budget: 0 };
}

/** A card's rectangle on the stage, in the same pixels its anchor is in. */
export interface StageRect {
  left: number;
  top: number;
  right: number;
  bottom: number;
}

/**
 * What a card occupies: its own box, the gap back to its mark, **and the mark**.
 *
 * The box half has to agree with `MapConstellation`'s transform exactly --
 * the card grows away from its mark, by `MAP_STAGE_CARD_GAP`, in whichever
 * direction `align` and `above` name -- because a reserved rectangle
 * somewhere other than the drawn card is a policy about nothing.
 *
 * The mark is included because a card and the pointer back to it are one
 * object, and `T-209` walked into both halves of leaving it out. Two marks
 * four pixels apart, one card opening upwards and the other downwards,
 * overlap nothing at all: both are drawn, both point into the same four
 * pixels, and a reader cannot tell which card belongs to which mark -- the
 * confusion the crowding clause exists to prevent, arriving by a different
 * route. So the rectangle spans from the mark's own little square, a gap
 * wide, to the far edge of the card.
 */
export function stageCardRect(
  card: StageCard,
  box: StageCardBox = MAP_STAGE_CARD_BOX,
): StageRect {
  const gap = MAP_STAGE_CARD_GAP;
  const { x, y } = card.point;
  const left = card.align === "end" ? x - gap - box.width : x - gap;
  const right = card.align === "end" ? x + gap : x + gap + box.width;
  const top = card.above ? y - gap - box.height : y - gap;
  const bottom = card.above ? y + gap : y + gap + box.height;
  return { left, top, right, bottom };
}

/**
 * Whether a card's rectangle is wholly on the stage (`T-209`).
 *
 * The same inset the anchor clause uses, applied to the *card* rather than to
 * the mark: an anchor a hundred pixels inside the top edge is comfortably on
 * the stage while its 248 px card, opening upwards, is not. The overlay is a
 * sibling of the container rather than a child of it (D-137), so a card that
 * leaves the stage is not clipped -- it is drawn over whatever the route puts
 * above the canvas, which is how the walk found it: the first line of two
 * statements sat behind the search rail.
 */
function fitsStage(rect: StageRect, box: StageBox, inset: number): boolean {
  return (
    rect.left >= inset &&
    rect.top >= inset &&
    rect.right <= box.width - inset &&
    rect.bottom <= box.height - inset
  );
}

/** Whether two card rectangles share any pixel. Touching edges do not. */
export function stageCardsOverlap(a: StageRect, b: StageRect): boolean {
  return a.left < b.right && b.left < a.right && a.top < b.bottom && b.top < a.bottom;
}

/**
 * The four ways one card can open, in the order the policy prefers them.
 *
 * The preferred orientation is the one `anchor` computed: towards the middle
 * of the stage, so a card near an edge is not clipped. What `T-209` measured
 * is that preferring it *only* is what made the constellation unreachable:
 * two marks either side of the stage's midpoint both open inwards, so their
 * cards grow towards each other and meet in the middle -- on the real graph,
 * every focus in a twenty-entity sample placed its own card and not one
 * neighbour's. Trying the other three orientations before giving up costs
 * three rectangle comparisons and turns a refusal into a card that opens the
 * other way.
 *
 * The order is stated so the placement is reproducible: preferred, then the
 * horizontal flip, then the vertical, then both.
 */
function orientations(card: StageCard): StageCard[] {
  const flipped = card.align === "end" ? "start" : "end";
  return [
    card,
    { ...card, align: flipped },
    { ...card, above: !card.above },
    { ...card, align: flipped, above: !card.above },
  ];
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
  const box = input.box ?? MAP_STAGE_CARD_BOX;
  const primaryBox = input.primaryBox ?? MAP_STAGE_PRIMARY_BOX;
  const inset = input.inset ?? MAP_STAGE_CARD_INSET;
  const { width, height } = input.stage;
  const omitted = noOmissions();

  const cards: StageCard[] = [];
  /** The rectangles already spoken for. A candidate may not touch one. */
  const taken: StageRect[] = [];

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

  // The primary card first, and it takes its own rectangle: the selected
  // statement is the one card D-132 guarantees, so a neighbour gives way to it
  // rather than landing on top of it -- which is exactly what the real route
  // did before `T-209` measured it, with a neighbour card covering two thirds
  // of the focused statement and its identifier. It does not consume the
  // neighbour budget, because it is not a neighbour.
  //
  // It prefers an orientation that keeps it on the stage, and falls back to
  // the preferred one when none does. The fallback is deliberate: this is the
  // card D-132 *guarantees*, so on a stage too small for it the honest
  // outcome is a card partly over the edge rather than a selection with
  // nothing on screen. A neighbour has no such guarantee, and is counted.
  const centre = input.centreId === null ? "not_loaded" : anchor(input.centreId);
  const preferred = typeof centre === "string" ? null : centre;
  const primary =
    preferred === null
      ? null
      : (orientations(preferred).find((option) =>
          fitsStage(stageCardRect(option, primaryBox), input.stage, inset),
        ) ?? preferred);
  if (primary !== null) taken.push(stageCardRect(primary, primaryBox));

  for (const related of input.related) {
    const candidate = anchor(related.globalId);
    if (typeof candidate === "string") {
      omitted[candidate] += 1;
      continue;
    }
    // Which of the four directions leave the card *on* the stage, and then
    // which of those leave it clear of the cards already placed. Two clauses
    // in that order, so the reason a card was refused is the real one: no
    // room at all is not the same answer as a neighbour already there.
    const fitting = orientations(candidate).filter((option) =>
      fitsStage(stageCardRect(option, box), input.stage, inset),
    );
    if (fitting.length === 0) {
      omitted.no_room += 1;
      continue;
    }
    // Crowding before the budget, so a card that cannot be placed at all
    // costs nothing: the budget is spent on cards a reader can actually read.
    const fitted = fitting.find(
      (option) =>
        !taken.some((placed) => stageCardsOverlap(stageCardRect(option, box), placed)),
    );
    if (fitted === undefined) {
      omitted.crowded += 1;
      continue;
    }
    if (cards.length >= budget) {
      omitted.budget += 1;
      continue;
    }
    taken.push(stageCardRect(fitted, box));
    cards.push({ ...fitted, related });
  }

  return {
    primary,
    cards,
    omitted,
    omittedTotal: STAGE_OMISSIONS.reduce((sum, reason) => sum + omitted[reason], 0),
  };
}
