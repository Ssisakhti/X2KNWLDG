/**
 * D-122, stated: what a Map node is allowed to say, and when (`T-205`).
 *
 * The `T-202` gate turned Sigma's labels on over the real graph and recorded
 * what happened: a knowledge unit's `label` is its whole `normalized_statement`
 * -- `library.py` chooses it that way, and the Reader wants exactly that -- so
 * 86 nodes drew 86 full sentences into a pile that hid the graph they were
 * annotating, with the longest running past the container edge. `T-204` then
 * shipped `renderLabels: false` and left the policy open. This module is the
 * policy, and it has two halves that must not be confused with each other:
 *
 * 1. **Truncation is presentational.** Nothing here rewrites, summarises or
 *    stores anything. The canonical statement stays in the node's `record`
 *    verbatim (D-124), the inspector and Quick Read show it in full (D-131),
 *    and what is drawn on the canvas is a *view* of the first few words of it,
 *    visibly cut with an ellipsis. ADR 0005 invariant 12 is the line: a
 *    truncated preview is honest because it looks truncated; a client-written
 *    summary would not be.
 *
 * 2. **Density is a rule, not a hope.** A label is drawn when the policy names
 *    a reason to draw it, and the reasons are: it is the focus, it is the node
 *    under the pointer or the keyboard, it is one of a *bounded* number of
 *    neighbours of the focus, or -- with nothing focused -- the camera has
 *    zoomed in far enough that Sigma's own label grid can place it without
 *    collisions. The overview never attempts 86 sentences again.
 *
 * The mechanism for the second half is Sigma's, deliberately: `labelVisibility`
 * per item decides *whether the policy forces a label*, and the three settings
 * in `MAP_LABEL_SETTINGS` decide what happens to everything left on `"auto"`.
 * A forced label bypasses both the grid and the size threshold (Sigma treats
 * `labelVisibility: "visible"` as a forced label), which is why forcing is
 * rationed here rather than handed out per node.
 *
 * Edge labels follow the same shape and are stricter: an edge names its real
 * relation only while it is on an active path. An overview that labelled 118
 * edges would be the same mistake with smaller words.
 */

import type { MapInteraction, MapViewState } from "./mapStyle";

/** What Sigma may do with a label the policy has not forced. */
export type MapLabelVisibility = "auto" | "visible" | "hidden";

/**
 * The visible mark of a cut. One character, appended, never inserted.
 *
 * A reader who sees it knows there is more text; a reader who does not see it
 * is looking at the whole stored value.
 */
export const MAP_LABEL_ELLIPSIS = "…";

/**
 * How many characters of a statement each interaction state may show.
 *
 * Deliberately small at the overview end and generous at the focus end,
 * because the states differ in how many labels can be on screen at once: one
 * selected node can afford a line and a half, while a graph-wide `"auto"`
 * label has to survive being one of many. None of these is a limit on the
 * *stored* text, which is untouched.
 */
export const MAP_LABEL_CHARS: Record<MapInteraction, number> = {
  normal: 42,
  neighbour: 64,
  hovered: 120,
  selected: 160,
};

/**
 * How many characters of a relation name an active path may show.
 *
 * `relation` is a controlled token for canonical and library-synthetic edges
 * (`supports`, `derived_from`), so this budget almost never bites -- but the
 * contract types the field as an open `string`, and a user relation is
 * free-form, so an edge label is truncated on the same terms as a node's.
 */
export const MAP_EDGE_LABEL_CHARS = 32;

/**
 * How many neighbours of the focus may have their label *forced*.
 *
 * This is the density budget D-132 requires a number for. Nothing is hidden
 * by it, and `T-207`'s related list still names every one of them (ADR 0005
 * invariant 13).
 *
 * **Four, measured** (`T-209`, D-145). Twelve was the starting value, chosen
 * on the argument that the real graph's most connected nodes sit in that
 * order of degree and that twelve short labels fit around a focus. The walk
 * disagreed: forcing a label on all eight neighbours of the busiest entity
 * drew nine sentences into a cluster about 250 px across -- ForceAtlas2 pulls
 * a node's neighbours *towards* it, so a fan-out is the densest part of the
 * picture, which is the worst place to bypass Sigma's label grid. Sigma's own
 * budget for that area, at `labelGridCellSize: 180`, is one or two labels.
 *
 * Four is the largest fan-out that stayed readable. Above it the neighbours
 * keep their marks, their emphasis and their place in the semantic related
 * list, and their labels go back to `"auto"` so the grid decides which ones
 * fit. A budget that is exceeded therefore costs legibility, never data.
 *
 * It is deliberately the same number as `MAP_STAGE_CARD_BUDGET` and for the
 * same measured reason, but it stays a separate constant: they bound
 * different things, and one of them will move without the other.
 */
export const MAP_LABEL_NEIGHBOUR_BUDGET = 4;

/**
 * The settings half of the policy: what Sigma does with every `"auto"` label.
 *
 * - `renderLabels: true` replaces `T-204`'s blanket `false`. The blanket was
 *   holding the door until this module existed.
 * - `renderEdgeLabels: true` is what lets an active path name its real
 *   relation. Edge labels are `"hidden"` unless the path is active, so this
 *   setting draws nothing on its own.
 * - `edgeLabelAnchors: "nodeLabels"` keeps an edge label tied to a node that
 *   already has one, which is Sigma's own way of saying the same thing the
 *   edge policy says.
 * - `labelDensity: 1` with `labelGridCellSize: 180` is the overview budget: at
 *   most one automatic label per 180x180 px cell of the viewport. On a stage
 *   around 900x600 that is roughly fifteen labels rather than eighty-six.
 * - `labelRenderedSizeThreshold: 14` is the zoom rule. A node must be drawn at
 *   least 14 px across before it may claim an automatic label, and node size
 *   grows with the camera, so the overview is quiet and zooming in is what
 *   makes it speak. Raised from Sigma's 6 because 6 is a threshold for dots
 *   with words beside them, not for sentences.
 * - `hideLabelsOnMove: true` drops labels while the camera is panning or
 *   zooming. Text that reflows every frame is unreadable anyway, and the
 *   labels return the moment the camera stops.
 *
 * `T-209` measured these four on the real graph in Chrome and kept all four:
 * the framed overview draws **8 labels over 86 marks**, and two zoom presses
 * make about twelve speak in the visible area, which is exactly the "quiet
 * until you look closer" D-122 asked for. They are stated here, once, so that
 * re-measuring means editing a value rather than finding where the behaviour
 * came from.
 */
export const MAP_LABEL_SETTINGS = {
  renderLabels: true,
  renderEdgeLabels: true,
  edgeLabelAnchors: "nodeLabels",
  labelDensity: 1,
  labelGridCellSize: 180,
  labelRenderedSizeThreshold: 14,
  hideLabelsOnMove: true,
} as const;

/**
 * One line of display text from a stored value, cut where a reader can see it.
 *
 * Three properties, each of which is a bug somewhere if it is missing:
 *
 * - **Whitespace is collapsed.** A `normalized_statement` can carry newlines,
 *   and a WebGL label is a single line: an uncollapsed newline is a gap in the
 *   middle of a sentence rather than a paragraph.
 * - **The cut is by code point, not by UTF-16 unit.** The extracted knowledge
 *   is Persian as often as English, and `String.prototype.slice` will happily
 *   halve a surrogate pair and draw a replacement character.
 * - **The cut prefers a word boundary**, but only when one is close enough to
 *   the budget to be worth it; otherwise a long unbroken token would collapse
 *   the label to almost nothing.
 *
 * Returns `null` for a value the record does not state, because a node with no
 * label must draw none rather than an empty ghost or an invented one.
 */
export function truncateForDisplay(value: string | null | undefined, budget: number): string | null {
  const { shown, truncated } = cutToBudget(value, budget);
  if (shown === null) return null;
  return truncated ? `${shown}${MAP_LABEL_ELLIPSIS}` : shown;
}

/** What a cut produced, and whether it cut. */
export interface CutText {
  /** A **prefix** of the stored text, or `null` when the record states none. */
  shown: string | null;
  /** Whether anything was removed. The surface must say so where it is true. */
  truncated: boolean;
}

/**
 * The cut itself, without deciding how the cut is *shown*.
 *
 * Extracted because the Map shortens text on two surfaces with two different
 * ways of admitting it: a WebGL label bakes in an ellipsis, because a canvas
 * has nowhere else to put the admission, while a DOM card states it in words
 * next to the text. §8.6 allows one card-content formatter, so the two share
 * this and differ only in how they say "there is more" -- and, more usefully,
 * neither can be given the code-point bug without the other.
 *
 * The returned text is always a prefix of the stored text with its whitespace
 * collapsed. Nothing is paraphrased and nothing is completed (D-131).
 */
export function cutToBudget(value: string | null | undefined, budget: number): CutText {
  if (typeof value !== "string") return { shown: null, truncated: false };
  const flat = value.replace(/\s+/gu, " ").trim();
  if (flat === "") return { shown: null, truncated: false };

  const points = Array.from(flat);
  if (points.length <= budget) return { shown: flat, truncated: false };

  const kept = points.slice(0, budget).join("");
  const lastSpace = kept.lastIndexOf(" ");
  // Only honour a word boundary in the last 40% of the budget: a 160-character
  // budget cut at character 3 because that is where the first space fell is
  // worse than a mid-word cut with an ellipsis.
  const body = lastSpace >= Math.floor(budget * 0.6) ? kept.slice(0, lastSpace) : kept;
  return { shown: body.trimEnd(), truncated: true };
}

/** Whether a label that survived truncation is visibly a truncation. */
export function isTruncated(displayed: string | null): boolean {
  return displayed !== null && displayed.endsWith(MAP_LABEL_ELLIPSIS);
}

/**
 * Whether the policy forces this node's label, leaves it to Sigma, or refuses
 * it.
 *
 * `"hidden"` appears in exactly one case, and it is not a way of removing a
 * node: with a focus on stage, an unrelated node keeps its mark and its
 * position and loses only its *label*, because a screen carrying a focused
 * statement plus eighty ambient sentences is the pile D-122 exists to prevent.
 * The mark stays drawn and dimmed -- de-emphasised, never represented as
 * absent (§5 `T-205`).
 */
export function nodeLabelVisibility(
  interaction: MapInteraction,
  view: MapViewState,
): MapLabelVisibility {
  if (interaction === "selected" || interaction === "hovered") return "visible";
  if (interaction === "neighbour") {
    return view.neighbourNodes.size <= MAP_LABEL_NEIGHBOUR_BUDGET ? "visible" : "auto";
  }
  return view.selectedNode === null ? "auto" : "hidden";
}

/**
 * Whether this edge names its relation.
 *
 * Only an active path does: the edge touching the focus, or the edge touching
 * whatever is under the pointer or the keyboard. Everything else is `"hidden"`,
 * which is why turning `renderEdgeLabels` on does not put 118 words on the
 * overview.
 */
export function edgeLabelVisibility(interaction: MapInteraction): MapLabelVisibility {
  return interaction === "selected" || interaction === "hovered" ? "visible" : "hidden";
}
