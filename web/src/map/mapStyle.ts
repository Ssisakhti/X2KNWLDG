/**
 * The Map's one style table, as reducers (`T-205`).
 *
 * D-124 is the reason this file exists at all. A projected node carries `x`,
 * `y` and the API's `EntityRef` verbatim; a projected edge carries its
 * `IndexedRelation`. No colour, size, shape or label is ever written onto the
 * graph, because the graph is the evidence the inspector reads back and a
 * stored display attribute would put a presentation decision inside it -- and
 * would break the field-by-field comparison D-125's refusal depends on. So the
 * appearance of every mark is computed here, at draw time, from the record and
 * from the current view state, and handed to Sigma as a reducer.
 *
 * §8.6 allows one style table in this phase. This is it: `MapLegend`,
 * `sigmaRenderer` and the tests all read the same exported tables, so "the
 * legend agrees with the marks" is structural rather than a thing to remember.
 *
 * ## What each channel carries, and why that assignment
 *
 * ADR 0005 invariant 9 forbids colour-only provenance, and `T-202` recorded
 * that a size difference alone is indistinguishable at real node density. So
 * the two variables are on independent channels and the safety-critical one
 * gets the channel that survives greyscale:
 *
 * | Variable | Channel | Non-colour? |
 * |---|---|---|
 * | node `provenance_class` | shape (circle / diamond / square / triangle) and base size | yes |
 * | node `kind` | hue, one per kind family | no -- it is a categorical hint |
 * | edge `relation_vocabulary` | head extremity shape and thickness | yes |
 * | edge `provenance_class` | hue, and a tail mark | yes |
 * | interaction state | size, opacity, depth, halo, label | yes |
 *
 * Provenance is the distinction a reader must never get wrong -- `source` is
 * grounded in the medium, `derived` is synthesis, `user` is neither (D-006) --
 * so it owns shape on both nodes and edges. Kind has 31 values and therefore
 * cannot have a non-colour channel of its own; it is a hint the legend, the
 * label and the DOM cards spell out in words, and no decision in the approved
 * journey rests on telling two kind hues apart.
 *
 * ## Every value the data can actually carry
 *
 * `KIND_FAMILY` is a `Record<KnowledgeKind, ...>`, so a kind added to the
 * frozen contract is a *compile error here* rather than a node that silently
 * renders as something else -- the same device `api/vocabulary.ts` uses. The
 * grouping mirrors `artifacts.SECTION_ORDER`, the report's existing twelve
 * sections, plus `canonical_concept`, which is a Map/index kind rather than a
 * report section.
 *
 * A value the contract does *not* declare is a fourth case in every table, and
 * it renders as itself: `UNRECOGNISED` marks (a triangle, a reserved hue, a
 * square tail) exist so that a `provenance_class` or `relation_vocabulary` this
 * build has never heard of is visibly *not* one of the known ones. Rounding it
 * to `source` or `canonical` would be the client making a claim about
 * provenance, which is the one thing this Map may not do. An absent `kind` is a
 * different case again and is not an error: only knowledge units and concepts
 * carry one, so a source, an artifact or a caption is `unstated`.
 *
 * ## Colours are literals here, not tokens
 *
 * The DOM reads `--provenance-source-fg` and friends from the stylesheet and
 * follows the user's light/dark preference. WebGL cannot: Sigma needs a parsed
 * colour, so the canvas palette is a single set of mid-tone values chosen to
 * stay legible on both the light (`#fbfaf8`) and dark (`#17161a`) stage. The
 * legend beside the canvas uses the CSS tokens, which is why its swatch is not
 * always pixel-identical to the mark -- and why the legend states the *shape*,
 * which is the part that carries the meaning.
 */

import type {
  EntityRef,
  IndexedRelation,
  KnowledgeKind,
  ProvenanceClass,
} from "../api/contract";
import {
  MAP_EDGE_LABEL_CHARS,
  MAP_LABEL_CHARS,
  edgeLabelVisibility,
  nodeLabelVisibility,
  truncateForDisplay,
  type MapLabelVisibility,
} from "./labelPolicy";
import type { MapEdgeAttributes, MapNodeAttributes } from "./graphProjection";

/** The relation vocabularies, as the contract spells them. */
export type RelationVocabulary = IndexedRelation["relation_vocabulary"];

/**
 * The node shapes this Map draws, which are exactly the shapes
 * `sigmaRenderer.ts` declares as primitives. A name not in this union would be
 * silently replaced by Sigma with its first declared shape, so the union and
 * the declaration are kept in step by the compiler.
 */
export type MapNodeShape = "circle" | "diamond" | "square" | "triangle";

/** The edge extremities this Map draws, likewise declared in `sigmaRenderer.ts`. */
export type MapEdgeExtremity = "none" | "arrow" | "diamond" | "circle" | "bar" | "square";

/** Sigma's two default node depth layers; a focused mark draws above the rest. */
export type MapNodeDepth = "nodes" | "topNodes";

/** Sigma's two default edge depth layers. */
export type MapEdgeDepth = "edges" | "topEdges";

/**
 * The four interaction states D-130's journey needs.
 *
 * `neighbour` is a state rather than a decoration: Explore -> Peek -> Focus
 * only works if, once something is focused, the things it is connected to are
 * visibly the things it is connected to.
 */
export type MapInteraction = "normal" | "neighbour" | "hovered" | "selected";

/** The interaction states, in the order the legend and the tests walk them. */
export const MAP_INTERACTIONS: readonly MapInteraction[] = [
  "normal",
  "neighbour",
  "hovered",
  "selected",
];

/**
 * What the Map tells Sigma about one node.
 *
 * A structural subset of Sigma's `NodeDisplayData`, declared here rather than
 * imported, for the same reason `MapSession` declares `MapRenderer`: `sigma`
 * evaluates `WebGL2RenderingContext` while its module body runs, so a static
 * import of it anywhere in the application's module graph is a `ReferenceError`
 * in jsdom (D-127). `sigmaRenderer.ts` is where the two types meet, and `tsc`
 * proves them compatible there.
 *
 * `visibility` is typed `"visible"` and not a union on purpose. De-emphasis in
 * this Map is opacity; a node the filters returned is never hidden, because a
 * hidden node is a node the user cannot know exists.
 */
export interface MapNodeDisplay {
  shape: MapNodeShape;
  size: number;
  color: string;
  opacity: number;
  zIndex: number;
  depth: MapNodeDepth;
  visibility: "visible";
  label: string | null;
  labelVisibility: MapLabelVisibility;
  labelColor: string;
  labelSize: number;
  backdropVisibility: "visible" | "hidden";
  backdropColor: string;
  backdropBorderColor: string;
  backdropBorderWidth: number;
  backdropPadding: number;
  backdropArea: "node";
}

/** What the Map tells Sigma about one edge. Same contract as above. */
export interface MapEdgeDisplay {
  size: number;
  color: string;
  opacity: number;
  zIndex: number;
  depth: MapEdgeDepth;
  visibility: "visible";
  head: MapEdgeExtremity;
  tail: MapEdgeExtremity;
  parallelPath: "curved";
  label: string | null;
  labelVisibility: MapLabelVisibility;
  labelColor: string;
}

// ---------------------------------------------------------------------------
// Provenance: the channel that must survive greyscale
// ---------------------------------------------------------------------------

export interface NodeProvenanceMark {
  shape: MapNodeShape;
  /** Base radius before the interaction scale. */
  size: number;
}

/**
 * Node provenance, by shape.
 *
 * The sizes are not a ranking. A diamond and a triangle enclose visibly less
 * area than a circle of the same radius, so each shape is given the radius
 * that makes the four marks read as the same weight -- the opposite of a size
 * ramp, which would say something about importance that no field states
 * (ADR 0005 invariant 15).
 */
export const NODE_PROVENANCE_MARK: Record<ProvenanceClass, NodeProvenanceMark> = {
  source: { shape: "circle", size: 9 },
  derived: { shape: "diamond", size: 11 },
  user: { shape: "square", size: 9 },
};

/** A `provenance_class` this build does not know. Never rounded to a known one. */
export const UNRECOGNISED_PROVENANCE_MARK: NodeProvenanceMark = { shape: "triangle", size: 10 };

export function nodeProvenanceMark(value: string | null | undefined): NodeProvenanceMark {
  const known = (NODE_PROVENANCE_MARK as Record<string, NodeProvenanceMark | undefined>)[
    value ?? ""
  ];
  return known ?? UNRECOGNISED_PROVENANCE_MARK;
}

// ---------------------------------------------------------------------------
// Kind: the categorical hue channel
// ---------------------------------------------------------------------------

/**
 * The kind families, mirroring `artifacts.SECTION_ORDER`.
 *
 * `unstated` is not a family of kinds but the honest rendering of a node that
 * has none: `EntityRef.kind` is null for everything that is not a knowledge
 * unit or a concept, and a source, an artifact or a caption is a legitimate
 * graph node. `unrecognised` is the other case entirely -- a kind string this
 * build has never heard of.
 */
export type KindFamily =
  | "thesis"
  | "evidence"
  | "concept"
  | "framework"
  | "process"
  | "example"
  | "fact"
  | "recommendation"
  | "caveat"
  | "question"
  | "synthesis"
  | "reference"
  | "unstated"
  | "unrecognised";

/** Every family, in the order the legend lists them. */
export const KIND_FAMILIES: readonly KindFamily[] = [
  "thesis",
  "evidence",
  "concept",
  "framework",
  "process",
  "example",
  "fact",
  "recommendation",
  "caveat",
  "question",
  "synthesis",
  "reference",
  "unstated",
  "unrecognised",
];

/**
 * Every knowledge kind the contract declares, placed in a family.
 *
 * `Record<KnowledgeKind, KindFamily>` and not a lookup with a fallback: a kind
 * added to `constants.py`, regenerated into the declarations, becomes a
 * compile error here. That is the point. A fallback would let a new kind
 * arrive as an unremarkable grey dot and nobody would find out.
 */
export const KIND_FAMILY: Record<KnowledgeKind, KindFamily> = {
  claim: "thesis",
  principle: "thesis",

  evidence: "evidence",

  concept: "concept",
  definition: "concept",
  // Not one of `SECTION_ORDER`'s report sections: a canonical concept is the
  // library's cross-source node, and it belongs with the concepts it unifies.
  canonical_concept: "concept",

  framework: "framework",
  mental_model: "framework",
  diagnostic_model: "framework",

  process: "process",
  instruction: "process",

  example: "example",
  case_study: "example",
  analogy: "example",

  fact: "fact",
  statistic: "fact",

  recommendation: "recommendation",
  actionable_experiment: "recommendation",

  caveat: "caveat",
  limitation: "caveat",
  assumption: "caveat",
  counterargument: "caveat",

  question: "question",
  open_problem: "question",
  hypothesis: "question",

  relationship: "synthesis",
  implication: "synthesis",
  generalized_rule: "synthesis",
  synthesis: "synthesis",

  reference: "reference",
  quote: "reference",
};

/**
 * One hue per family, mid-tone so that it reads on both stage backgrounds.
 *
 * `unrecognised` reserves a hue used by nothing else, because the failure to
 * avoid is a value the contract does not declare quietly looking like one it
 * does.
 */
export const KIND_FAMILY_COLOUR: Record<KindFamily, string> = {
  thesis: "#4477aa",
  evidence: "#228833",
  concept: "#aa3377",
  framework: "#ee7733",
  process: "#009988",
  example: "#999933",
  fact: "#1e9fd0",
  recommendation: "#ddaa33",
  caveat: "#cc3311",
  question: "#6644aa",
  synthesis: "#8b5a2b",
  reference: "#5f7a86",
  unstated: "#8b847b",
  unrecognised: "#e4007f",
};

/** The family of a `kind` field: absent is `unstated`, unknown is `unrecognised`. */
export function kindFamily(kind: string | null | undefined): KindFamily {
  if (kind === null || kind === undefined || kind === "") return "unstated";
  const family = (KIND_FAMILY as Record<string, KindFamily | undefined>)[kind];
  return family ?? "unrecognised";
}

/** The kinds a family holds, for the legend. Empty for the two non-kind families. */
export function kindsOfFamily(family: KindFamily): readonly string[] {
  return Object.keys(KIND_FAMILY)
    .filter((kind) => KIND_FAMILY[kind as KnowledgeKind] === family)
    .sort();
}

// ---------------------------------------------------------------------------
// Edges: vocabulary by shape, provenance by hue and tail
// ---------------------------------------------------------------------------

export interface EdgeVocabularyMark {
  /** The arrowhead at the target end. Direction is a stated field, not a guess. */
  head: MapEdgeExtremity;
  /** Base thickness before the interaction scale. */
  size: number;
}

/**
 * Edge vocabulary, by head shape and thickness.
 *
 * The two library-synthetic relations, `derived_from` and `expresses_concept`,
 * are 62 of the real graph's 118 edges and are deliberately outside
 * `RELATION_TYPES` (§10). They are drawn thinner than canonical evidence and
 * carry a diamond head rather than an arrow: the graph should not read as
 * though the library's own synthesis were extracted from the medium. Nothing
 * here inspects the relation *name* -- `relation_vocabulary` is the field that
 * states which vocabulary an edge belongs to, and the name is printed verbatim
 * on the active path instead.
 */
export const EDGE_VOCABULARY_MARK: Record<RelationVocabulary, EdgeVocabularyMark> = {
  canonical: { head: "arrow", size: 2.2 },
  library_synthetic: { head: "diamond", size: 1.4 },
  user: { head: "circle", size: 1.4 },
};

/** A `relation_vocabulary` this build does not know. */
export const UNRECOGNISED_VOCABULARY_MARK: EdgeVocabularyMark = { head: "bar", size: 1.4 };

export function edgeVocabularyMark(value: string | null | undefined): EdgeVocabularyMark {
  const known = (EDGE_VOCABULARY_MARK as Record<string, EdgeVocabularyMark | undefined>)[
    value ?? ""
  ];
  return known ?? UNRECOGNISED_VOCABULARY_MARK;
}

export interface EdgeProvenanceMark {
  /** The mark at the source end: the non-colour half of edge provenance. */
  tail: MapEdgeExtremity;
  colour: string;
}

/**
 * Edge provenance, by hue and by a mark at the tail.
 *
 * The hue matches what the Library and the Reader already teach -- green for
 * source-grounded, amber for derived, violet for user-authored -- and the tail
 * mark is what keeps invariant 9 true for edges as well as nodes. The tail is
 * used rather than the head because the head already carries vocabulary, and
 * two variables cannot share one end of a line.
 */
export const EDGE_PROVENANCE_MARK: Record<ProvenanceClass, EdgeProvenanceMark> = {
  source: { tail: "none", colour: "#2f8f5f" },
  derived: { tail: "bar", colour: "#a9801f" },
  user: { tail: "circle", colour: "#7a5ac9" },
};

/** A `provenance_class` this build does not know, on an edge. */
export const UNRECOGNISED_EDGE_PROVENANCE_MARK: EdgeProvenanceMark = {
  tail: "square",
  colour: KIND_FAMILY_COLOUR.unrecognised,
};

export function edgeProvenanceMark(value: string | null | undefined): EdgeProvenanceMark {
  const known = (EDGE_PROVENANCE_MARK as Record<string, EdgeProvenanceMark | undefined>)[
    value ?? ""
  ];
  return known ?? UNRECOGNISED_EDGE_PROVENANCE_MARK;
}

// ---------------------------------------------------------------------------
// The field: what a mark's size is a function of (`T-216`, D-197)
// ---------------------------------------------------------------------------

/**
 * The field width the mark sizes above are stated at.
 *
 * `SPEC.md` §3: "Mark size scales with the viewport; the ratios do not." The
 * approved Explore composition draws `NODE_PROVENANCE_MARK`'s 9 as a 12 px
 * circle on a 1280 px field and as a 27 px circle on a 2852 px one, and it is
 * the *same* nine either way -- what changes is the field, not the ratio
 * between a circle and a diamond.
 *
 * This is the width that factor is 1.35 at, and below it the factor stops
 * shrinking: a mark on a narrow field is already as small as it can be read
 * at, and a phone should not draw a graph in five-pixel dots.
 */
export const MAP_FIELD_REFERENCE_WIDTH = 1280;

/**
 * The mark scale at the reference width, as a multiplier on a **radius**.
 *
 * The mockup's own factor is `1.35` and it multiplies a *diameter*
 * (`r = mark.size * 0.5 * MARK`); Sigma's `size` is a radius, so the number
 * that reproduces the approved picture here is half of it. Stated as the
 * halved value rather than as `1.35 / 2` at the call site, because a reader
 * checking this against `docs/mockups/T-211/render.js` needs to be told once
 * which of the two conventions each number is in.
 */
export const MAP_MARK_FIELD_SCALE = 0.675;

/**
 * How much of a *thickness* an edge is drawn at, at the reference width.
 *
 * `0.62` is the mockup's, and it is a real correction rather than a rounding:
 * `EDGE_VOCABULARY_MARK`'s 2.2 and 1.4 were calibrated in `T-205` against a
 * camera-scaled renderer, where they were multiplied up by the framing before
 * they reached a pixel. Drawn as declared they are heavy, and the approved
 * composition draws them at 0.62 of that.
 */
export const MAP_EDGE_FIELD_SCALE = 0.62;

/**
 * The field width above which an edge starts getting thicker.
 *
 * The mockup thickens edges on `max(1, MARK * 0.55)` rather than on `MARK`, so
 * an edge grows more slowly than a mark and does not start growing at all
 * until the field is wide enough. With `MARK = max(1, W / 1280) * 1.35` that
 * expression is exactly `max(1, W / 1724)`, which is the form used here: one
 * threshold instead of two nested factors, and the same numbers -- 1.36 px for
 * a canonical edge at 1440, 2.26 px at 2852.
 */
export const MAP_EDGE_FIELD_THICKEN_WIDTH = 1724;

/**
 * The multiplier on every node radius, for a field this wide.
 *
 * A **camera-independent** function, and that is the whole of D-197: Sigma's
 * default `itemSizesReference: "positions"` reads a size as a distance in
 * graph units and multiplies it by the pixels-per-graph-unit of the current
 * framing, so the same graph drew marks several times larger on a 2852 px
 * field than on a 1440 px one and the approved quiet field was quiet only at
 * the narrow end (`SPEC.md` §16). `sigmaRenderer.ts` therefore asks for
 * `"screen"` sizes -- pixels, with no framing term -- and the viewport scale
 * SPEC §3 does specify is applied here, where it can be read and tested.
 *
 * Zero, or any width below the reference, draws the reference composition: a
 * route whose stage has not been measured yet is a route about to be measured,
 * not a route with no marks.
 */
export function markFieldScale(fieldWidth: number): number {
  return Math.max(1, fieldWidth / MAP_FIELD_REFERENCE_WIDTH) * MAP_MARK_FIELD_SCALE;
}

/** The same, for an edge's thickness. Flatter, and it starts later. */
export function edgeFieldScale(fieldWidth: number): number {
  return Math.max(1, fieldWidth / MAP_EDGE_FIELD_THICKEN_WIDTH) * MAP_EDGE_FIELD_SCALE;
}

/**
 * The renderer settings that make the two scales above the only ones there are
 * (D-197). `sigmaRenderer.ts` spreads them in.
 *
 * - `itemSizesReference: "screen"` is the decision. Sigma's default is
 *   `"positions"`, which reads every `size` this table returns as a distance
 *   in graph units and multiplies it by `cameraRatio * graphToViewportRatio`
 *   at draw time -- the framing. Two consequences, and both are `T-215`'s
 *   finding: a wider window frames the same graph into more pixels per unit
 *   and therefore draws bigger marks, and the marks then cross
 *   `labelRenderedSizeThreshold` and the label grid fills. `"screen"` drops
 *   the `graphToViewportRatio` term entirely, so a size is a pixel size and
 *   the only thing that scales it is the field width, in `markFieldScale`.
 *
 *   It does **not** freeze size under zoom, which is what D-196 assumed when
 *   it opened this question. Sigma divides by `zoomToSizeRatioFunction(ratio)`
 *   in both modes -- the default is `Math.sqrt` -- so a mark still grows as
 *   the camera comes in, at `1 / sqrt(ratio)`. D-122's zoom rule is therefore
 *   not retired by this change, and `labelPolicy.ts` re-expresses rather than
 *   deletes it.
 *
 * - `minEdgeThickness` is lowered from Sigma's 1.7 because 1.7 is above the
 *   thinnest thickness this table declares. `EDGE_VOCABULARY_MARK` draws a
 *   canonical edge at 2.2 and a library-synthetic one at 1.4, and after
 *   `edgeFieldScale` at the reference width those are 1.36 px and 0.87 px --
 *   so Sigma's floor would have clamped the thin one up to the thick one's
 *   neighbourhood and quietly deleted the vocabulary distinction that
 *   `mapStyle.test.ts` asserts the *constants* preserve. The floor is kept,
 *   at a value below the table's own smallest, because it still has a job:
 *   an edge on a camera zoomed far out must not vanish.
 */
export const MAP_SIZE_SETTINGS = {
  itemSizesReference: "screen",
  minEdgeThickness: 0.75,
} as const;

// ---------------------------------------------------------------------------
// Interaction
// ---------------------------------------------------------------------------

export interface InteractionMark {
  /** Multiplier on the base size. */
  scale: number;
  /** Opacity when this item is *not* being de-emphasised. Never zero. */
  opacity: number;
  zIndex: number;
  /** Whether the mark is lifted onto Sigma's top depth layer. */
  top: boolean;
}

/**
 * The four states, for nodes.
 *
 * `T-202` recorded that its size-only selection was indistinguishable at real
 * node density, so `selected` is four signals at once: it is the largest, it
 * is the only mark with a halo ring, it is lifted onto the top depth layer,
 * and it is the one label the policy always forces. `hovered` is the same
 * signals at a lower amplitude, because Peek is a preview and not a selection
 * (D-133).
 */
export const NODE_INTERACTION: Record<MapInteraction, InteractionMark> = {
  normal: { scale: 1, opacity: 1, zIndex: 0, top: false },
  neighbour: { scale: 1.15, opacity: 1, zIndex: 1, top: false },
  hovered: { scale: 1.35, opacity: 1, zIndex: 2, top: true },
  selected: { scale: 1.7, opacity: 1, zIndex: 3, top: true },
};

/** The same four states, for edges. */
export const EDGE_INTERACTION: Record<MapInteraction, InteractionMark> = {
  normal: { scale: 1, opacity: 0.85, zIndex: 0, top: false },
  neighbour: { scale: 1.1, opacity: 0.95, zIndex: 1, top: false },
  hovered: { scale: 1.4, opacity: 1, zIndex: 2, top: true },
  selected: { scale: 1.6, opacity: 1, zIndex: 3, top: true },
};

/**
 * What an unrelated mark fades to while something is focused.
 *
 * Dimming, never hiding, and never below `MAP_MIN_VISIBLE_OPACITY`: §5 asks
 * for unrelated structure to be de-emphasised *without being represented as
 * absent*, and an opacity of zero is a claim that the filters returned fewer
 * nodes than they did.
 */
export const MAP_DIMMED_NODE_OPACITY = 0.35;
export const MAP_DIMMED_EDGE_OPACITY = 0.25;

/**
 * What an edge is drawn at on the overview, where *nothing* is focused
 * (`T-216`, D-198).
 *
 * `--edge-faint` is §6's proposed token for "the quiet Explore field", and
 * `T-214` recorded it as its one unimplemented clause: Explore's edges are
 * WebGL and a canvas cannot read a custom property (`SPEC.md` §15, D-194).
 * This is that clause, implemented where a renderer can reach it. The approved
 * capture draws its edges at 20 % white on the dark ground and 18 % black on
 * the light one; a provenance hue at this opacity carries about that weight
 * and, unlike a grey line, still says which of the three provenances the
 * relation has.
 *
 * It applies to the `normal` state and only while nothing is selected, so
 * hovering a mark still lights its own edges: with a focus on stage the
 * unrelated edges go further down, to `MAP_DIMMED_EDGE_OPACITY`, and the
 * active path comes up to 1. Three levels, in the order a reader meets them.
 *
 * Nodes are deliberately not quieted with them. The approved overview draws
 * its marks at full strength on a faint web of edges -- marks and structure
 * dominate, and text arrives on demand (ADR 0006 clause 3) -- so quieting both
 * would produce a grey picture rather than a quiet one.
 */
export const MAP_QUIET_EDGE_OPACITY = 0.32;

/** The floor every opacity in this module stays above. Asserted in the tests. */
export const MAP_MIN_VISIBLE_OPACITY = 0.15;

/** Halo geometry for the two focused states. The ring is the non-colour signal. */
export const MAP_HALO = {
  selected: { width: 2.5, padding: 6 },
  hovered: { width: 1.5, padding: 4 },
} as const;

/** Label sizes per state. Bigger for the focus, because there is only one. */
export const MAP_LABEL_SIZE: Record<MapInteraction, number> = {
  normal: 11,
  neighbour: 12,
  hovered: 13,
  selected: 14,
};

// ---------------------------------------------------------------------------
// View state
// ---------------------------------------------------------------------------

/**
 * What the Map is currently doing, as far as appearance is concerned.
 *
 * Identity only, and always an existing `global_id` or relation `id` (ADR 0005
 * invariant 2). This module never decides *what* is selected -- `T-206` owns
 * selection and its URL grammar, `T-207` owns the neighbourhood -- it only
 * decides what a selection looks like.
 */
export interface MapViewState {
  /** The focused entity's `global_id`, or `null`. Focus is history (D-133). */
  selectedNode: string | null;
  /** The `global_id` under the pointer or the keyboard. Peek writes no history. */
  hoveredNode: string | null;
  /** The focus's neighbours, by `global_id`. */
  neighbourNodes: ReadonlySet<string>;
  /**
   * The nodes the Directional Orbit has drawn a card for (`T-214`).
   *
   * A label on the canvas and a card over it are the *same statement* twice,
   * and the card is underneath nothing while the label is underneath the
   * card: ADR 0006 clause 5 says graph labels may not render under cards, and
   * `T-210`'s acceptance criterion says a label never sits under a Focus card.
   * So a node with a card has no label, and a node without one keeps exactly
   * the rule it had. Every neighbour is therefore still named -- by its card
   * if it has one, by its label if it does not -- which is a stronger
   * statement than either "hide them all in Focus" or the pile that was
   * there before.
   *
   * A *set of ids* rather than a flag, because the orbit places some
   * neighbours and counts others, and the ones it counted are exactly the
   * ones whose label still has a job to do.
   */
  cardedNodes: ReadonlySet<string>;
}

export const EMPTY_VIEW_STATE: MapViewState = {
  selectedNode: null,
  hoveredNode: null,
  neighbourNodes: new Set<string>(),
  cardedNodes: new Set<string>(),
};

/** Whether anything is focused. With no focus, nothing is de-emphasised. */
export function hasFocus(view: MapViewState): boolean {
  return view.selectedNode !== null;
}

/**
 * Which of the four states a node is in.
 *
 * `sigmaHovered` is Sigma's own hover flag, which arrives free with the
 * renderer; `view.hoveredNode` is the same state reached from the keyboard, so
 * that Peek is not pointer-only (D-120). Either one counts, which is what makes
 * the keyboard path a peer of the pointer path rather than a simulation of it.
 */
export function nodeInteraction(
  key: string,
  view: MapViewState,
  sigmaHovered = false,
): MapInteraction {
  if (view.selectedNode === key) return "selected";
  if (sigmaHovered || view.hoveredNode === key) return "hovered";
  if (view.neighbourNodes.has(key)) return "neighbour";
  return "normal";
}

/**
 * Which of the four states an edge is in, derived from its own endpoints.
 *
 * An edge touching the focus is the *active path* -- it is the edge that gets
 * to name its real relation, which is the whole point of the "why is this
 * worth opening" question the approved journey asks before a click. An edge
 * between two neighbours is context, and everything else is structure.
 */
export function edgeInteraction(record: IndexedRelation, view: MapViewState): MapInteraction {
  const { from_id: from, to_id: to } = record;
  if (view.selectedNode !== null && (from === view.selectedNode || to === view.selectedNode)) {
    return "selected";
  }
  if (view.hoveredNode !== null && (from === view.hoveredNode || to === view.hoveredNode)) {
    return "hovered";
  }
  if (view.neighbourNodes.has(from) && view.neighbourNodes.has(to)) return "neighbour";
  return "normal";
}

// ---------------------------------------------------------------------------
// The reducers
// ---------------------------------------------------------------------------

/** One node's appearance: its record, its state, and nothing else. */
export function mapNodeStyle(
  record: EntityRef,
  interaction: MapInteraction,
  view: MapViewState,
  fieldWidth: number,
): MapNodeDisplay {
  const mark = nodeProvenanceMark(record.provenance_class);
  const family = kindFamily(record.kind);
  const colour = KIND_FAMILY_COLOUR[family];
  const state = NODE_INTERACTION[interaction];
  const dimmed = interaction === "normal" && hasFocus(view);
  const halo =
    interaction === "selected"
      ? MAP_HALO.selected
      : interaction === "hovered"
        ? MAP_HALO.hovered
        : null;

  return {
    shape: mark.shape,
    // Screen pixels, scaled by the field and by nothing else (D-197). The
    // renderer is configured with `itemSizesReference: "screen"`, so this
    // number reaches the shader as a radius in pixels rather than as a
    // distance in graph units the framing then multiplies.
    size: mark.size * state.scale * markFieldScale(fieldWidth),
    color: colour,
    opacity: dimmed ? MAP_DIMMED_NODE_OPACITY : state.opacity,
    zIndex: state.zIndex,
    depth: state.top ? "topNodes" : "nodes",
    visibility: "visible",
    label: truncateForDisplay(record.label, MAP_LABEL_CHARS[interaction]),
    labelVisibility: nodeLabelVisibility(record.global_id, interaction, view),
    // The label wears the mark's own hue rather than a fixed ink colour: the
    // stage follows the user's light/dark preference and WebGL cannot read a
    // CSS custom property, so a mid-tone that is legible on both is the only
    // honest choice available here.
    labelColor: colour,
    labelSize: MAP_LABEL_SIZE[interaction],
    backdropVisibility: halo === null ? "hidden" : "visible",
    // A ring, not a fill: the halo must not tint the mark it is describing.
    backdropColor: "transparent",
    backdropBorderColor: colour,
    backdropBorderWidth: halo?.width ?? 0,
    backdropPadding: halo?.padding ?? 0,
    backdropArea: "node",
  };
}

/** One edge's appearance. */
export function mapEdgeStyle(
  record: IndexedRelation,
  interaction: MapInteraction,
  view: MapViewState,
  fieldWidth: number,
): MapEdgeDisplay {
  const vocabulary = edgeVocabularyMark(record.relation_vocabulary);
  const provenance = edgeProvenanceMark(record.provenance_class);
  const state = EDGE_INTERACTION[interaction];
  const dimmed = interaction === "normal" && hasFocus(view);
  // The other half of `dimmed`: an edge in the `normal` state on a field with
  // nothing focused is the overview's own web, and the overview is quiet.
  const quiet = interaction === "normal" && !hasFocus(view);
  const visibility = edgeLabelVisibility(record, interaction, view);

  return {
    size: vocabulary.size * state.scale * edgeFieldScale(fieldWidth),
    color: provenance.colour,
    opacity: dimmed
      ? MAP_DIMMED_EDGE_OPACITY
      : quiet
        ? MAP_QUIET_EDGE_OPACITY
        : state.opacity,
    zIndex: state.zIndex,
    depth: state.top ? "topEdges" : "edges",
    visibility: "visible",
    head: vocabulary.head,
    tail: provenance.tail,
    // Parallel edges are common here -- one pair of entities carries a
    // canonical relation *and* a library-synthetic one -- and two straight
    // lines between the same two points are one drawn line and one edge the
    // Map counted but nobody can see.
    parallelPath: "curved",
    label:
      visibility === "hidden" ? null : truncateForDisplay(record.relation, MAP_EDGE_LABEL_CHARS),
    labelVisibility: visibility,
    labelColor: provenance.colour,
  };
}

/**
 * A reducer as Sigma calls one, narrowed to what this Map uses.
 *
 * `data` is Sigma's already-computed display data and is deliberately typed
 * `unknown`: everything this table returns is computed from the record, so a
 * reducer that read the incoming data would be styling the style.
 */
export type MapNodeReducer = (
  key: string,
  data: unknown,
  attributes: MapNodeAttributes,
  state: { isHovered: boolean },
) => MapNodeDisplay;

export type MapEdgeReducer = (
  key: string,
  data: unknown,
  attributes: MapEdgeAttributes,
) => MapEdgeDisplay;

/**
 * The style table bound to a view state, with the two reducers over it.
 *
 * Mutable, and deliberately so: hovering a node must not relay out the graph
 * (D-128 relaxes the whole layout on every `update`, which would make the
 * picture jump on every pointer move). The renderer keeps one style object,
 * the view writes the new state into it, and `MapSession.refresh()` redraws
 * with the layout untouched.
 *
 * `setView` reports whether anything actually changed, so a caller can skip a
 * redraw for a pointer move that ended on the node it started on.
 *
 * The **field width** is kept beside the view state rather than in it, and the
 * separation is deliberate (`T-216`). `MapViewState` is identity: an existing
 * `global_id` per role, and nothing a renderer measured. A field width is the
 * opposite kind of fact -- one number about the surface, from `MapView`'s
 * `ResizeObserver` -- and putting it in the view state would make every reader
 * of that interface, `labelPolicy` included, able to reach a measurement it has
 * no business with. Two setters, two `changed` answers, one redraw either way.
 */
export class MapStyle {
  private state: MapViewState = EMPTY_VIEW_STATE;
  /**
   * The field the marks are drawn on, in CSS pixels. `0` until measured, which
   * `markFieldScale` reads as the reference composition (D-197).
   */
  private width = 0;

  get view(): MapViewState {
    return this.state;
  }

  get fieldWidth(): number {
    return this.width;
  }

  /**
   * The field's width changed, so every mark and every edge is a new size.
   *
   * Reports whether anything changed, on the same terms `setView` does: a
   * `ResizeObserver` fires on the height alone often enough that redrawing
   * every mark for it would be a redraw per scrollbar.
   */
  setField(width: number): boolean {
    if (!Number.isFinite(width) || width === this.width) return false;
    this.width = width;
    return true;
  }

  setView(next: Partial<MapViewState>): boolean {
    const merged: MapViewState = {
      selectedNode: next.selectedNode !== undefined ? next.selectedNode : this.state.selectedNode,
      hoveredNode: next.hoveredNode !== undefined ? next.hoveredNode : this.state.hoveredNode,
      neighbourNodes:
        next.neighbourNodes !== undefined ? next.neighbourNodes : this.state.neighbourNodes,
      cardedNodes: next.cardedNodes !== undefined ? next.cardedNodes : this.state.cardedNodes,
    };
    if (
      merged.selectedNode === this.state.selectedNode &&
      merged.hoveredNode === this.state.hoveredNode &&
      sameMembers(merged.neighbourNodes, this.state.neighbourNodes) &&
      sameMembers(merged.cardedNodes, this.state.cardedNodes)
    ) {
      return false;
    }
    this.state = merged;
    return true;
  }

  /** Back to an unfocused overview. A filter change is a new question (D-118). */
  clear(): boolean {
    return this.setView(EMPTY_VIEW_STATE);
  }

  readonly nodeReducer: MapNodeReducer = (key, _data, attributes, state) =>
    mapNodeStyle(
      attributes.record,
      nodeInteraction(key, this.state, state.isHovered),
      this.state,
      this.width,
    );

  readonly edgeReducer: MapEdgeReducer = (_key, _data, attributes) =>
    mapEdgeStyle(
      attributes.record,
      edgeInteraction(attributes.record, this.state),
      this.state,
      this.width,
    );
}

function sameMembers(left: ReadonlySet<string>, right: ReadonlySet<string>): boolean {
  if (left === right) return true;
  if (left.size !== right.size) return false;
  for (const member of left) if (!right.has(member)) return false;
  return true;
}

/**
 * The style the application's renderer draws through.
 *
 * One instance, because there is exactly one renderer (D-126) and therefore
 * exactly one thing that can be selected or hovered at a time. `MapStyle` is a
 * class rather than a module of globals so that a test -- and `T-207`'s
 * overlay, if it needs a second view -- can hold its own without disturbing
 * this one.
 */
export const mapStyle = new MapStyle();
