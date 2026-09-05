/**
 * The Source Map's style table (`T-256`, from `T-255`'s approved compositions).
 *
 * A second table rather than a widening of `mapStyle`, because the two Maps
 * draw different things and share only their mechanism. The Knowledge Map's
 * table answers "what kind of knowledge is this, and where did it come from";
 * this one answers "what medium is this source, and does it have a brief". A
 * single table with a mode flag would be one function with two bodies, and the
 * kind palette would sit in it unused — reachable, and therefore reachable by
 * mistake.
 *
 * What this table **gives up**, and why each refusal is the design rather than
 * an omission (D-247, D-274, D-277):
 *
 * - **One size for every mark, one weight for every edge.** A source relation
 *   carries no confidence, no score and no rank, and `basis_total` is a count.
 *   Sizing a mark or thickening an edge by it would draw a ranking the records
 *   do not contain — the single most load-bearing refusal in these pictures.
 * - **No freshness channel.** The v1 shapes carry no per-relation staleness, so
 *   nothing here can say whether a relationship is still current.
 * - **No kind hue.** A source node's `kind` is `null` in every body, so the
 *   Knowledge Map's twelve-family palette is absent rather than reused for
 *   something else.
 * - **Run status is not a mark.** `PASS`/`PARTIAL`/`FAIL` is a fact about a
 *   *run*; drawn on the field it reads as a quality ranking of the source. It
 *   is a badge on a card, in `SourceBriefCard`, and nowhere on the stage.
 *
 * What it **adds**, each in two channels so neither is colour alone (ADR 0001
 * invariant 10):
 *
 * - **Medium** — hue, plus a glyph the cards and the legend carry.
 * - **Brief state** — fill: a source with a brief is solid, one whose brief is
 *   stale is solid with a ring, one with no brief is hollow. An absent brief is
 *   a normal condition (D-257), so it is drawn as an absence of fill rather
 *   than as an alarm colour.
 * - **Scope** — a dash pattern on the edge, plus the word on every pill.
 *
 * The interaction states, the field scale, the halo and the dimming are
 * `mapStyle`'s and are imported rather than restated: they are facts about this
 * *renderer* rather than about either Map's records, and a second copy is how
 * two fields come to feel like two applications.
 */

import type { EntityRef, SourceRelationSummary } from "../api/contract";

import {
  EDGE_INTERACTION,
  MAP_DIMMED_EDGE_OPACITY,
  MAP_DIMMED_NODE_OPACITY,
  MAP_HALO,
  MAP_LABEL_SIZE,
  MAP_QUIET_EDGE_OPACITY,
  NODE_INTERACTION,
  edgeFieldScale,
  hasFocus,
  markFieldScale,
  type MapEdgeDisplay,
  type MapInteraction,
  type MapNodeDisplay,
  type MapViewState,
  EMPTY_VIEW_STATE,
  nodeInteraction,
} from "./mapStyle";
import { MAP_LABEL_CHARS, nodeLabelVisibility, truncateForDisplay } from "./labelPolicy";
import { mapStage, type MapStage } from "./stage";

/** How a medium is drawn, and how it is written. */
export interface SourceMediumMark {
  /** The mark's hue. Never the only channel. */
  colour: string;
  /** The glyph the cards, the legend and the outline carry beside the word. */
  glyph: string;
}

/**
 * The two implemented media, in the ink each stage is drawn in.
 *
 * The hues are the `thesis` and `process` families of `KIND_FAMILY_INK`,
 * reused in a mode that draws no kinds — the palette is one project's, and
 * inventing two more hues would have widened it for no reader's benefit. They
 * are per stage for the same reason the families are: a source node's label is
 * text on the canvas, and `stage.ts` shows no single ink clears 4.5:1 on both
 * grounds. `stageContrast.test.ts` holds every value below to its own ground.
 */
export const SOURCE_MEDIUM_INK: Record<MapStage, Record<string, SourceMediumMark>> = {
  light: {
    youtube: { colour: "#4477aa", glyph: "▶" },
    twitter: { colour: "#008274", glyph: "✦" },
  },
  dark: {
    youtube: { colour: "#4d83b8", glyph: "▶" },
    twitter: { colour: "#009988", glyph: "✦" },
  },
};

/** The medium marks for the stage this environment is on. */
export function sourceMediumMarks(
  stage: MapStage = mapStage(),
): Record<string, SourceMediumMark> {
  return SOURCE_MEDIUM_INK[stage];
}

/**
 * A `source_type` this build does not know.
 *
 * Never rounded to a known one, for `nodeProvenanceMark`'s reason: a medium
 * this build cannot name is a medium it must not name, and the roadmap has
 * four more of them. Magenta is `KIND_FAMILY_INK`'s `unrecognised`, which is
 * this project's existing "the vocabulary moved" colour.
 */
export const UNRECOGNISED_MEDIUM_INK: Record<MapStage, SourceMediumMark> = {
  light: { colour: "#e0007d", glyph: "?" },
  dark: { colour: "#f60089", glyph: "?" },
};

export function sourceMediumMark(
  value: string | null | undefined,
  stage: MapStage = mapStage(),
): SourceMediumMark {
  const known =
    value === null || value === undefined ? undefined : SOURCE_MEDIUM_INK[stage][value];
  return known ?? UNRECOGNISED_MEDIUM_INK[stage];
}

/** Which brief states a source node can be drawn in. */
export type BriefState = "available" | "stale" | "unavailable";

/** How a brief state is drawn: fill, and a ring for the one that needs it. */
export interface SourceBriefMark {
  /** `true` fills the mark; `false` draws it hollow. */
  filled: boolean;
  /** A ring around the mark, for the state that is neither current nor absent. */
  ring: boolean;
}

export const SOURCE_BRIEF_MARK: Record<BriefState, SourceBriefMark> = {
  available: { filled: true, ring: false },
  stale: { filled: true, ring: true },
  unavailable: { filled: false, ring: false },
};

export function sourceBriefMark(value: string | null | undefined): SourceBriefMark {
  const known = value === null || value === undefined ? undefined : SOURCE_BRIEF_MARK[value as BriefState];
  // A state this build does not know is drawn as no brief rather than as a
  // brief: the honest failure is to under-claim.
  return known ?? SOURCE_BRIEF_MARK.unavailable;
}

/** Scope, as a dash pattern. Two values, no third, no percentage. */
export const SOURCE_SCOPE_DASH: Record<SourceRelationSummary["scope"], boolean> = {
  partial: true,
  broad: false,
};

/**
 * The one size every source mark is drawn at, before the interaction scale and
 * the field scale. `NODE_PROVENANCE_MARK.source.size`, because every source
 * node *is* `provenance_class: "source"` and the two must not drift.
 */
export const SOURCE_MARK_SIZE = 9;

/** The one weight every relationship is drawn at. See the header. */
export const SOURCE_EDGE_SIZE = 1.8;

/**
 * What a source node's mark knows that its record does not.
 *
 * The brief state lives in the *neighbourhood* response rather than on the
 * node, so the view holds a map of it and hands it to the table — exactly as
 * it hands over the selection. A source the view has no brief state for is
 * drawn as `unavailable`, which is what a source with no `source_knowledge.json`
 * is, and is the honest under-claim rather than an invented "unknown" channel.
 */
export interface SourceViewState extends MapViewState {
  briefStates: ReadonlyMap<string, BriefState>;
}

export const EMPTY_SOURCE_VIEW_STATE: SourceViewState = {
  ...EMPTY_VIEW_STATE,
  briefStates: new Map(),
};

/** One source node's appearance. */
export function sourceNodeStyle(
  record: EntityRef,
  interaction: MapInteraction,
  view: SourceViewState,
  fieldWidth: number,
  stage: MapStage = mapStage(),
): MapNodeDisplay {
  const medium = sourceMediumMark(record.source_type, stage);
  const brief = sourceBriefMark(view.briefStates.get(record.global_id) ?? "unavailable");
  const state = NODE_INTERACTION[interaction];
  const dimmed = interaction === "normal" && hasFocus(view);
  const halo =
    interaction === "selected"
      ? MAP_HALO.selected
      : interaction === "hovered"
        ? MAP_HALO.hovered
        : brief.ring
          ? MAP_HALO.hovered
          : null;
  const labelVisibility = nodeLabelVisibility(record.global_id, interaction, view);

  return {
    shape: "circle",
    // One size for every source. `state.scale` is the interaction — a selected
    // mark is larger than a quiet one — and that is a statement about what the
    // reader is doing, not about the source.
    size: SOURCE_MARK_SIZE * state.scale * markFieldScale(fieldWidth),
    // A hollow mark is drawn by giving the fill the stage's own ground and
    // letting the ring carry the hue: Sigma's node programs have no "no fill",
    // so the absence is drawn rather than declared.
    color: brief.filled ? medium.colour : "transparent",
    opacity: dimmed ? MAP_DIMMED_NODE_OPACITY : state.opacity,
    zIndex: state.zIndex,
    depth: state.top ? "topNodes" : "nodes",
    visibility: "visible",
    label:
      labelVisibility === "hidden"
        ? null
        : truncateForDisplay(record.label, MAP_LABEL_CHARS[interaction]),
    labelVisibility,
    labelColor: medium.colour,
    labelSize: MAP_LABEL_SIZE[interaction],
    // The ring does three jobs and they cannot collide: a selection ring, a
    // hover ring, and a stale-brief ring. The first two are the reader's own
    // state and win, because a reader looking at a mark needs to know it is the
    // one they chose before they need to know its brief has drifted — and the
    // card says the second in words either way.
    // A hollow mark is drawn BY its ring: with no fill and no ring there is
    // nothing on the field at all, which is what the first draft did to every
    // source with no brief — the most common state in a young library. So the
    // ring is hidden only when a fill is doing the drawing and nothing else
    // needs saying.
    backdropVisibility: halo === null && brief.filled ? "hidden" : "visible",
    backdropColor: "transparent",
    backdropBorderColor: medium.colour,
    backdropBorderWidth: halo?.width ?? (brief.filled ? 0 : 2),
    backdropPadding: halo?.padding ?? 0,
    backdropArea: "node",
  };
}

/**
 * One relationship's appearance.
 *
 * `edgeInteraction` is not reused: it reads `IndexedRelation.from_id`/`to_id`,
 * and a source relation names its ends `from_source_id`/`to_source_id` as
 * two-part ids rather than global ones. The rule is the same and the fields are
 * not, so the rule is applied here rather than the record bent to fit it.
 */
export function sourceEdgeStyle(
  record: SourceRelationSummary,
  interaction: MapInteraction,
  view: SourceViewState,
  fieldWidth: number,
  stage: MapStage = mapStage(),
): MapEdgeDisplay {
  const state = EDGE_INTERACTION[interaction];
  const dimmed = interaction === "normal" && hasFocus(view);
  const quiet = interaction === "normal" && !hasFocus(view);
  const relationInk = SOURCE_RELATION_INK[stage];

  return {
    // One weight for every relationship. `state.scale` is the interaction
    // again, and `basis_total` reaches this function and is not read.
    size: SOURCE_EDGE_SIZE * state.scale * edgeFieldScale(fieldWidth),
    color: relationInk,
    opacity: dimmed ? MAP_DIMMED_EDGE_OPACITY : quiet ? MAP_QUIET_EDGE_OPACITY : state.opacity,
    zIndex: state.zIndex,
    depth: state.top ? "topEdges" : "edges",
    visibility: "visible",
    // Direction, on every edge and at every interaction: the whole point of a
    // source relation is that it runs one way, and an edge that stated it only
    // on hover would leave the overview saying less than the records do.
    head: "arrow",
    // Scope, as a dash. Sigma has no dash on an edge program, so the tail
    // extremity carries the distinction the dash would: `partial` is marked,
    // `broad` is not. The word is on every pill regardless.
    tail: SOURCE_SCOPE_DASH[record.scope] ? "bar" : "none",
    parallelPath: "curved",
    // An edge label is the relation type, shown on the active path only —
    // `labelPolicy`'s rule for the Knowledge Map, and for the same reason: a
    // field of type names is a field nobody reads.
    label: interaction === "normal" ? null : record.relation_type,
    labelVisibility: interaction === "normal" ? "hidden" : "visible",
    labelColor: relationInk,
  };
}

/**
 * The one colour every relationship is drawn in.
 *
 * A source relation's `provenance_class` is always `derived` — the vocabulary
 * has no other value for it — so a provenance palette here would be a palette
 * with one entry, and a *type* palette would give eight relation types eight
 * hues and say, by drawing them apart, that they differ in kind rather than in
 * name. They differ in name; the pill says which.
 *
 * One colour per stage, because an edge carries a label too.
 */
export const SOURCE_RELATION_INK: Record<MapStage, string> = {
  light: "#79736a",
  dark: "#8b847b",
};

/** A reducer as Sigma calls one, over the source graph's attributes. */
export type SourceNodeReducer = (
  key: string,
  data: unknown,
  attributes: { record: EntityRef },
  state: { isHovered: boolean },
) => MapNodeDisplay;

export type SourceEdgeReducer = (
  key: string,
  data: unknown,
  attributes: { record: SourceRelationSummary },
) => MapEdgeDisplay;

/**
 * The Source Map's style table, with the same surface `MapStyle` has.
 *
 * The two classes are deliberately not one with a flag: what they share is the
 * *shape* — a mutable view, a field width, two reducers — and `sigmaRendererFor`
 * takes that shape structurally, so the sharing is expressed where it is real
 * and nowhere else.
 */
export class SourceStyle {
  private state: SourceViewState = EMPTY_SOURCE_VIEW_STATE;
  private width = 0;

  get view(): SourceViewState {
    return this.state;
  }

  get fieldWidth(): number {
    return this.width;
  }

  setField(width: number): boolean {
    if (!Number.isFinite(width) || width === this.width) return false;
    this.width = width;
    return true;
  }

  setView(next: Partial<SourceViewState>): boolean {
    const merged: SourceViewState = {
      selectedNode: next.selectedNode !== undefined ? next.selectedNode : this.state.selectedNode,
      hoveredNode: next.hoveredNode !== undefined ? next.hoveredNode : this.state.hoveredNode,
      neighbourNodes:
        next.neighbourNodes !== undefined ? next.neighbourNodes : this.state.neighbourNodes,
      cardedNodes: next.cardedNodes !== undefined ? next.cardedNodes : this.state.cardedNodes,
      briefStates: next.briefStates !== undefined ? next.briefStates : this.state.briefStates,
    };
    if (
      merged.selectedNode === this.state.selectedNode &&
      merged.hoveredNode === this.state.hoveredNode &&
      sameMembers(merged.neighbourNodes, this.state.neighbourNodes) &&
      sameMembers(merged.cardedNodes, this.state.cardedNodes) &&
      sameStates(merged.briefStates, this.state.briefStates)
    ) {
      return false;
    }
    this.state = merged;
    return true;
  }

  clear(): boolean {
    return this.setView(EMPTY_SOURCE_VIEW_STATE);
  }

  readonly nodeReducer: SourceNodeReducer = (key, _data, attributes, state) =>
    sourceNodeStyle(
      attributes.record,
      nodeInteraction(key, this.state, state.isHovered),
      this.state,
      this.width,
    );

  readonly edgeReducer: SourceEdgeReducer = (_key, _data, attributes) =>
    sourceEdgeStyle(
      attributes.record,
      sourceEdgeInteraction(attributes.record, this.state),
      this.state,
      this.width,
    );
}

/**
 * An edge's interaction state, read from its own ends.
 *
 * `MapViewState` holds `global_id`s and a relation holds two-part source ids,
 * so the comparison is made on the two-part form of the selection rather than
 * by rebuilding a global id from an endpoint — which would have to guess the
 * reserved `:source` local id and would be a second place that id is spelled.
 */
export function sourceEdgeInteraction(
  record: SourceRelationSummary,
  view: SourceViewState,
): MapInteraction {
  if (view.selectedNode === null) return "normal";
  const selected = twoPartOf(view.selectedNode);
  if (selected === null) return "normal";
  return record.from_source_id === selected || record.to_source_id === selected
    ? "selected"
    : "normal";
}

function twoPartOf(globalId: string): string | null {
  const parts = globalId.split(":");
  return parts.length === 3 && parts[0] && parts[1] ? `${parts[0]}:${parts[1]}` : null;
}

function sameMembers(left: ReadonlySet<string>, right: ReadonlySet<string>): boolean {
  if (left === right) return true;
  if (left.size !== right.size) return false;
  for (const member of left) if (!right.has(member)) return false;
  return true;
}

function sameStates(
  left: ReadonlyMap<string, BriefState>,
  right: ReadonlyMap<string, BriefState>,
): boolean {
  if (left === right) return true;
  if (left.size !== right.size) return false;
  for (const [key, value] of left) if (right.get(key) !== value) return false;
  return true;
}

/** The application's one Source Map style table. */
export const sourceStyle = new SourceStyle();
