/**
 * The style table (`T-205`).
 *
 * These are pure tests over pure functions, which is the point: D-124 moved
 * every display decision out of the graph and into a reducer, so the whole
 * appearance of the Map is assertable without a canvas, a browser or a WebGL
 * context. What they are checking is not "does it look nice" but four rules
 * that have decisions behind them:
 *
 * 1. **No colour-only provenance** (ADR 0005 invariant 9). Every provenance
 *    class and every relation vocabulary is separated by something that
 *    survives greyscale -- shape at both ends of an edge, shape for a node --
 *    and the tests compare the marks pairwise rather than trusting that the
 *    table looks varied.
 * 2. **Every value the data can carry is covered**, including the two
 *    library-synthetic relations that are 62 of the real graph's 118 edges,
 *    and including values the contract does not declare, which must render as
 *    themselves rather than as the nearest known thing.
 * 3. **De-emphasis is not absence.** Unrelated structure fades and stays
 *    drawn; nothing this module produces is ever hidden.
 * 4. **The graph is not touched.** Running the reducers over the real snapshot
 *    leaves `x`, `y` and `record` and nothing else.
 */

import { describe, expect, it } from "vitest";

import type { EntityRef, IndexedRelation } from "../api/contract";
import { KNOWLEDGE_KINDS, PROVENANCE_CLASSES, RELATION_VOCABULARIES } from "../api/vocabulary";
import { concept, edge, expressesConcept, page, payload, unit } from "../test/graphRecords";
import { GraphSnapshot } from "./graphSnapshot";
import { edgeAttributes, nodeAttributes } from "./graphProjection";
import { MAP_LABEL_CHARS, MAP_LABEL_ELLIPSIS, isTruncated } from "./labelPolicy";
import {
  EDGE_INTERACTION,
  EDGE_PROVENANCE_MARK,
  EDGE_VOCABULARY_MARK,
  EMPTY_VIEW_STATE,
  KIND_FAMILIES,
  KIND_FAMILY,
  KIND_FAMILY_COLOUR,
  MAP_DIMMED_EDGE_OPACITY,
  MAP_DIMMED_NODE_OPACITY,
  MAP_EDGE_FIELD_SCALE,
  MAP_EDGE_FIELD_THICKEN_WIDTH,
  MAP_FIELD_REFERENCE_WIDTH,
  MAP_INTERACTIONS,
  MAP_MARK_FIELD_SCALE,
  MAP_MIN_VISIBLE_OPACITY,
  MAP_QUIET_EDGE_OPACITY,
  MAP_SIZE_SETTINGS,
  MapStyle,
  NODE_INTERACTION,
  NODE_PROVENANCE_MARK,
  UNRECOGNISED_EDGE_PROVENANCE_MARK,
  UNRECOGNISED_PROVENANCE_MARK,
  UNRECOGNISED_VOCABULARY_MARK,
  edgeInteraction,
  edgeProvenanceMark,
  edgeVocabularyMark,
  hasFocus,
  kindFamily,
  kindsOfFamily,
  edgeFieldScale,
  mapEdgeStyle as mapEdgeStyleOn,
  mapNodeStyle as mapNodeStyleOn,
  markFieldScale,
  nodeInteraction,
  nodeProvenanceMark,
  type MapInteraction,
  type MapViewState,
} from "./mapStyle";

const KU1 = "youtube:pqlWNihgdjI:KU-000001";
const KU2 = "youtube:pqlWNihgdjI:KU-000002";
const C1 = "library:concepts:C-000001";

function view(overrides: Partial<MapViewState> = {}): MapViewState {
  return { ...EMPTY_VIEW_STATE, ...overrides };
}

/**
 * The two reducers, over the field width the mark sizes are *stated* at
 * (`T-216`).
 *
 * Every assertion below except the sizing ones is about a shape, a hue, an
 * opacity or a label, and none of those moves with the field -- so the field
 * is defaulted here rather than repeated forty times, and the one number it
 * defaults to is `MAP_FIELD_REFERENCE_WIDTH`, where `markFieldScale` is
 * exactly `MAP_MARK_FIELD_SCALE`. A test that cares passes its own.
 */
function mapNodeStyle(
  record: EntityRef,
  interaction: MapInteraction,
  state: MapViewState,
  fieldWidth: number = MAP_FIELD_REFERENCE_WIDTH,
) {
  return mapNodeStyleOn(record, interaction, state, fieldWidth);
}

function mapEdgeStyle(
  record: IndexedRelation,
  interaction: MapInteraction,
  state: MapViewState,
  fieldWidth: number = MAP_FIELD_REFERENCE_WIDTH,
) {
  return mapEdgeStyleOn(record, interaction, state, fieldWidth);
}

/**
 * A record carrying a value the contract does not declare.
 *
 * Not hypothetical: the vocabularies are generated from `constants.py`, and a
 * build of this UI can be older than the index the server is serving.
 */
function withUnknown<T extends object>(record: T, fields: Record<string, string>): T {
  return { ...record, ...fields } as T;
}

describe("provenance is never a colour-only distinction", () => {
  it("gives every provenance class its own shape", () => {
    const shapes = PROVENANCE_CLASSES.map((provenance) => NODE_PROVENANCE_MARK[provenance].shape);
    expect(new Set(shapes).size).toBe(PROVENANCE_CLASSES.length);
    expect(shapes).not.toContain(UNRECOGNISED_PROVENANCE_MARK.shape);
  });

  it("separates two nodes of different provenance in greyscale", () => {
    // The real pair this protects: the same statement extracted from the
    // medium and synthesised by the library are one shape apart, not one hue
    // apart, so nothing about the distinction depends on seeing colour.
    const grounded = mapNodeStyle(unit("KU-000001"), "normal", view());
    const derived = mapNodeStyle(
      unit("KU-000001", { provenance_class: "derived" }),
      "normal",
      view(),
    );
    expect(derived.shape).not.toBe(grounded.shape);
    // And the hue is the *kind's*, so it deliberately does not move with
    // provenance -- which is what makes the shape load-bearing.
    expect(derived.color).toBe(grounded.color);
  });

  it("renders a provenance class it has never heard of as itself", () => {
    const alien = withUnknown(unit("KU-000001"), { provenance_class: "syndicated" });
    const style = mapNodeStyle(alien, "normal", view());
    expect(style.shape).toBe(UNRECOGNISED_PROVENANCE_MARK.shape);
    for (const provenance of PROVENANCE_CLASSES) {
      expect(style.shape).not.toBe(NODE_PROVENANCE_MARK[provenance].shape);
    }
    expect(nodeProvenanceMark(null)).toBe(UNRECOGNISED_PROVENANCE_MARK);
  });
});

describe("kind", () => {
  it("places every kind the contract declares, with nothing left over", () => {
    // `KIND_FAMILY` is a `Record<KnowledgeKind, ...>`, so this cannot fail
    // without the contract having changed -- which is exactly why it is a test
    // rather than a comment: the compile error and this assertion name the
    // same event from two directions.
    for (const kind of KNOWLEDGE_KINDS) {
      expect(KIND_FAMILIES).toContain(KIND_FAMILY[kind]);
    }
    expect(Object.keys(KIND_FAMILY).sort()).toEqual([...KNOWLEDGE_KINDS].sort());
    expect(Object.keys(KIND_FAMILY)).toHaveLength(31);
  });

  it("gives every family a colour, and no two families the same one", () => {
    const colours = KIND_FAMILIES.map((family) => KIND_FAMILY_COLOUR[family]);
    expect(new Set(colours).size).toBe(KIND_FAMILIES.length);
    expect(Object.keys(KIND_FAMILY_COLOUR).sort()).toEqual([...KIND_FAMILIES].sort());
  });

  it("tells a kind the record does not state from one it does not recognise", () => {
    // A source, an artifact and a caption are graph nodes with no kind, and
    // that is correct rather than missing. A kind string this build has never
    // seen is a different statement and gets a different mark.
    expect(kindFamily(null)).toBe("unstated");
    expect(kindFamily(undefined)).toBe("unstated");
    expect(kindFamily("counterexample")).toBe("unrecognised");
    expect(KIND_FAMILY_COLOUR.unrecognised).not.toBe(KIND_FAMILY_COLOUR.unstated);
    for (const kind of KNOWLEDGE_KINDS) {
      expect(KIND_FAMILY_COLOUR[KIND_FAMILY[kind]]).not.toBe(KIND_FAMILY_COLOUR.unrecognised);
    }
  });

  it("colours the two kinds the real graph is mostly made of", () => {
    const claim = mapNodeStyle(unit("KU-000001"), "normal", view());
    const canonical = mapNodeStyle(concept("C-000001"), "normal", view());
    expect(claim.color).toBe(KIND_FAMILY_COLOUR.thesis);
    expect(canonical.color).toBe(KIND_FAMILY_COLOUR.concept);
    expect(claim.color).not.toBe(canonical.color);
  });

  it("lists a family's kinds for the legend, from the same table it draws from", () => {
    expect(kindsOfFamily("thesis")).toEqual(["claim", "principle"]);
    expect(kindsOfFamily("concept")).toContain("canonical_concept");
    expect(kindsOfFamily("unstated")).toEqual([]);
  });
});

describe("edges", () => {
  it("gives every relation vocabulary its own head shape and weight", () => {
    const heads = RELATION_VOCABULARIES.map(
      (vocabulary) => EDGE_VOCABULARY_MARK[vocabulary].head,
    );
    expect(new Set(heads).size).toBe(RELATION_VOCABULARIES.length);
    expect(heads).not.toContain(UNRECOGNISED_VOCABULARY_MARK.head);
    // Canonical evidence is the heaviest line: the library's own synthesis
    // must not read as though it had been extracted from the medium.
    expect(EDGE_VOCABULARY_MARK.canonical.size).toBeGreaterThan(
      EDGE_VOCABULARY_MARK.library_synthetic.size,
    );
  });

  it("styles the two library-synthetic relations that dominate the real graph", () => {
    // 45 `derived_from` and 17 `expresses_concept` of 118, and neither is in
    // `RELATION_TYPES` (§10). The vocabulary field is what is styled; the
    // relation name itself is printed verbatim on an active path.
    const expresses = expressesConcept(KU1, C1);
    const derivedFrom = expressesConcept(KU1, C1);
    derivedFrom.relation = "derived_from";

    for (const record of [expresses, derivedFrom]) {
      const style = mapEdgeStyle(record, "normal", view());
      expect(style.head).toBe(EDGE_VOCABULARY_MARK.library_synthetic.head);
      expect(style.color).toBe(EDGE_PROVENANCE_MARK.derived.colour);
      expect(style.tail).toBe(EDGE_PROVENANCE_MARK.derived.tail);
    }

    const canonical = mapEdgeStyle(edge(KU1, KU2), "normal", view());
    expect(canonical.head).toBe(EDGE_VOCABULARY_MARK.canonical.head);
    expect(canonical.head).not.toBe(EDGE_VOCABULARY_MARK.library_synthetic.head);
  });

  it("keeps edge provenance out of colour alone as well", () => {
    const tails = PROVENANCE_CLASSES.map((provenance) => EDGE_PROVENANCE_MARK[provenance].tail);
    const colours = PROVENANCE_CLASSES.map(
      (provenance) => EDGE_PROVENANCE_MARK[provenance].colour,
    );
    expect(new Set(tails).size).toBe(PROVENANCE_CLASSES.length);
    expect(new Set(colours).size).toBe(PROVENANCE_CLASSES.length);
  });

  it("renders a vocabulary or a provenance it has never heard of as itself", () => {
    const alien = withUnknown(edge(KU1, KU2), {
      relation_vocabulary: "imported",
      provenance_class: "syndicated",
    });
    const style = mapEdgeStyle(alien, "normal", view());
    expect(style.head).toBe(UNRECOGNISED_VOCABULARY_MARK.head);
    expect(style.tail).toBe(UNRECOGNISED_EDGE_PROVENANCE_MARK.tail);
    expect(style.color).toBe(UNRECOGNISED_EDGE_PROVENANCE_MARK.colour);
    for (const vocabulary of RELATION_VOCABULARIES) {
      expect(style.head).not.toBe(EDGE_VOCABULARY_MARK[vocabulary].head);
    }
    expect(edgeVocabularyMark(undefined)).toBe(UNRECOGNISED_VOCABULARY_MARK);
    expect(edgeProvenanceMark("")).toBe(UNRECOGNISED_EDGE_PROVENANCE_MARK);
  });

  it("separates parallel edges instead of drawing one line for two relations", () => {
    // The same pair of entities carries a canonical relation and a
    // library-synthetic one often enough that two straight lines would be one
    // drawn line and one edge the Map counted but nobody can see.
    expect(mapEdgeStyle(edge(KU1, KU2), "normal", view()).parallelPath).toBe("curved");
  });
});

describe("the four interaction states", () => {
  const record = unit("KU-000001");

  it("resolves a node's state from the selection, the peek and the neighbourhood", () => {
    const focused = view({
      selectedNode: KU1,
      hoveredNode: KU2,
      neighbourNodes: new Set([C1]),
    });
    expect(nodeInteraction(KU1, focused)).toBe("selected");
    expect(nodeInteraction(KU2, focused)).toBe("hovered");
    expect(nodeInteraction(C1, focused)).toBe("neighbour");
    expect(nodeInteraction("youtube:pqlWNihgdjI:KU-000009", focused)).toBe("normal");
  });

  it("counts Sigma's own hover and a keyboard focus as the same state", () => {
    // D-120: no operation is pointer-only. Peek reached from the keyboard has
    // to be the same state as Peek reached from the pointer, or the keyboard
    // path is a simulation of the real one rather than a peer of it.
    expect(nodeInteraction(KU2, view(), true)).toBe("hovered");
    expect(nodeInteraction(KU2, view({ hoveredNode: KU2 }))).toBe("hovered");
    expect(nodeInteraction(KU2, view(), false)).toBe("normal");
  });

  it("reads an edge's state from its own endpoints", () => {
    const focused = view({ selectedNode: KU1 });
    expect(edgeInteraction(edge(KU1, KU2), focused)).toBe("selected");
    expect(edgeInteraction(edge(KU2, KU1), focused)).toBe("selected");
    expect(edgeInteraction(edge(KU2, C1), focused)).toBe("normal");

    const context = view({ selectedNode: KU1, neighbourNodes: new Set([KU2, C1]) });
    expect(edgeInteraction(edge(KU2, C1), context)).toBe("neighbour");

    const peeked = view({ hoveredNode: C1 });
    expect(edgeInteraction(edge(KU2, C1), peeked)).toBe("hovered");
  });

  it("gives the selection more than one signal, because size alone was not enough", () => {
    // `T-202`: "the gate's size-only selection is indistinguishable at real
    // node density". So selection is four things at once, and this asserts all
    // four rather than the largest of them.
    const selected = mapNodeStyle(record, "selected", view({ selectedNode: KU1 }));
    const normal = mapNodeStyle(record, "normal", view());
    expect(selected.size).toBeGreaterThan(normal.size);
    expect(selected.backdropVisibility).toBe("visible");
    expect(selected.backdropBorderWidth).toBeGreaterThan(0);
    expect(selected.depth).toBe("topNodes");
    expect(selected.zIndex).toBeGreaterThan(normal.zIndex);
    expect(selected.labelVisibility).toBe("visible");
    expect(normal.backdropVisibility).toBe("hidden");
  });

  it("orders the four states, on nodes and on edges alike", () => {
    const order: MapInteraction[] = ["normal", "neighbour", "hovered", "selected"];
    expect(MAP_INTERACTIONS).toEqual(order);
    for (let index = 1; index < order.length; index += 1) {
      const previous = order[index - 1] as MapInteraction;
      const current = order[index] as MapInteraction;
      expect(NODE_INTERACTION[current].scale).toBeGreaterThanOrEqual(
        NODE_INTERACTION[previous].scale,
      );
      expect(NODE_INTERACTION[current].zIndex).toBeGreaterThan(NODE_INTERACTION[previous].zIndex);
      expect(EDGE_INTERACTION[current].zIndex).toBeGreaterThan(EDGE_INTERACTION[previous].zIndex);
    }
  });

  it("produces a style for every state, on every kind of record", () => {
    for (const interaction of MAP_INTERACTIONS) {
      for (const node of [unit("KU-000001"), concept("C-000001")]) {
        const style = mapNodeStyle(node, interaction, view({ selectedNode: KU1 }));
        expect(style.size).toBeGreaterThan(0);
        expect(style.color).toMatch(/^#[0-9a-f]{6}$/);
      }
      for (const relation of [edge(KU1, KU2), expressesConcept(KU1, C1)]) {
        const style = mapEdgeStyle(relation, interaction, view({ selectedNode: KU1 }));
        expect(style.size).toBeGreaterThan(0);
        expect(style.color).toMatch(/^#[0-9a-f]{6}$/);
      }
    }
  });
});

describe("a mark's size is a function of the field, and of nothing else", () => {
  /*
   * `T-216`, D-197. This is the clause the browser cannot assert: a canvas
   * label and a WebGL mark have no DOM node, and the gate says so rather than
   * pretending otherwise (`SPEC.md` §16). What *is* assertable is the rule
   * itself -- that the two settings which used to make a mark's size a
   * function of the framing are gone, and that the scale that replaced them
   * reads the field's width and nothing else.
   */
  it("asks Sigma for screen sizes, which is what drops the framing term", () => {
    // Sigma's default is `"positions"`: a size is a distance in graph units,
    // multiplied at draw time by `cameraRatio * graphToViewportRatio`. The
    // second factor is the field, so the same graph drew marks several times
    // larger at 2852 px than at 1440 px -- the largest of the three
    // differences `T-215`'s comparison found.
    expect(MAP_SIZE_SETTINGS.itemSizesReference).toBe("screen");
  });

  it("keeps a floor below the thinnest thickness the table itself declares", () => {
    // Sigma's own floor is 1.7, which is above every thickness this table
    // draws at the reference width -- so it would have clamped a
    // library-synthetic edge up to a canonical one's neighbourhood and
    // deleted a distinction the constants preserve.
    const thinnest = Math.min(
      ...RELATION_VOCABULARIES.map((vocabulary) => EDGE_VOCABULARY_MARK[vocabulary].size),
      UNRECOGNISED_VOCABULARY_MARK.size,
    );
    expect(MAP_SIZE_SETTINGS.minEdgeThickness).toBeLessThan(
      thinnest * edgeFieldScale(MAP_FIELD_REFERENCE_WIDTH),
    );
  });

  it("scales every mark by the field width and no ratio by anything", () => {
    // The property SPEC §3 states in words: "Mark size scales with the
    // viewport; the ratios do not."
    const wide = 2852;
    for (const provenance of PROVENANCE_CLASSES) {
      const record = unit("KU-000001", { provenance_class: provenance });
      const narrow = mapNodeStyle(record, "normal", view(), MAP_FIELD_REFERENCE_WIDTH);
      const large = mapNodeStyle(record, "normal", view(), wide);
      expect(large.size / narrow.size).toBeCloseTo(wide / MAP_FIELD_REFERENCE_WIDTH, 6);
    }
    // ... and the ratio between two provenances is the same on both fields.
    const circle = NODE_PROVENANCE_MARK.source;
    const diamond = NODE_PROVENANCE_MARK.derived;
    for (const width of [MAP_FIELD_REFERENCE_WIDTH, wide]) {
      const one = mapNodeStyle(unit("KU-000001"), "normal", view(), width);
      const two = mapNodeStyle(
        unit("KU-000001", { provenance_class: "derived" }),
        "normal",
        view(),
        width,
      );
      expect(two.size / one.size).toBeCloseTo(diamond.size / circle.size, 6);
    }
  });

  it("draws the approved composition on a field narrower than the reference", () => {
    // A stage that has not been measured yet reports zero, and a route about
    // to be measured is not a route with no marks: the scale floors at the
    // reference width rather than collapsing.
    expect(markFieldScale(0)).toBe(MAP_MARK_FIELD_SCALE);
    expect(markFieldScale(390)).toBe(MAP_MARK_FIELD_SCALE);
    expect(markFieldScale(MAP_FIELD_REFERENCE_WIDTH)).toBe(MAP_MARK_FIELD_SCALE);
    expect(edgeFieldScale(0)).toBe(MAP_EDGE_FIELD_SCALE);
    // An edge thickens later than a mark does, which is the mockup's own
    // curve: `max(1, MARK * 0.55)` rather than `MARK`.
    expect(edgeFieldScale(MAP_FIELD_REFERENCE_WIDTH)).toBe(MAP_EDGE_FIELD_SCALE);
    expect(edgeFieldScale(MAP_EDGE_FIELD_THICKEN_WIDTH * 2)).toBeCloseTo(
      MAP_EDGE_FIELD_SCALE * 2,
      6,
    );
  });

  it("reproduces the diameters the approved capture was measured at", () => {
    // The numbers in `SPEC.md` §3 and §17, as arithmetic rather than as a
    // picture: a source circle is 12 px across on a 1280 px field, 14 on
    // 1440 and 27 on 2852, and a canonical edge is 1.4 px thick on the first
    // two and 2.3 on the last.
    const diameter = (width: number) =>
      mapNodeStyle(unit("KU-000001"), "normal", view(), width).size * 2;
    expect(Math.round(diameter(1280))).toBe(12);
    expect(Math.round(diameter(1440))).toBe(14);
    expect(Math.round(diameter(2852))).toBe(27);

    const thickness = (width: number) =>
      mapEdgeStyle(edge(KU1, KU2), "normal", view(), width).size;
    expect(thickness(1280)).toBeCloseTo(1.36, 2);
    expect(thickness(1440)).toBeCloseTo(1.36, 2);
    expect(thickness(2852)).toBeCloseTo(2.26, 2);
  });

  it("hands the field to the reducers through the one style table", () => {
    const style = new MapStyle();
    expect(style.fieldWidth).toBe(0);
    expect(style.setField(2852)).toBe(true);
    expect(style.fieldWidth).toBe(2852);
    // The same width twice is not a redraw, and neither is a measurement that
    // has not arrived: a `ResizeObserver` fires on the height alone often
    // enough that either would be a redraw per scrollbar.
    expect(style.setField(2852)).toBe(false);
    expect(style.setField(Number.NaN)).toBe(false);

    const attributes = nodeAttributes(unit("KU-000001"));
    const wide = style.nodeReducer(KU1, undefined, attributes, { isHovered: false });
    style.setField(MAP_FIELD_REFERENCE_WIDTH);
    const narrow = style.nodeReducer(KU1, undefined, attributes, { isHovered: false });
    expect(wide.size).toBeGreaterThan(narrow.size);
  });
});

describe("the overview is quiet, and a focus is quieter still", () => {
  it("draws the overview's edges faint, and lights them under the pointer", () => {
    // `T-214`'s one unimplemented clause, implemented (`SPEC.md` §15, §17):
    // §6 proposed `--edge-faint` for "the quiet Explore field" and a canvas
    // cannot read a custom property, so the number lives in the one table a
    // renderer can reach.
    const overview = mapEdgeStyle(edge(KU1, KU2), "normal", view());
    expect(overview.opacity).toBe(MAP_QUIET_EDGE_OPACITY);
    expect(overview.opacity).toBeGreaterThan(MAP_MIN_VISIBLE_OPACITY);
    expect(overview.visibility).toBe("visible");

    // Hovering a mark still lights its own edges: the quiet rule is about the
    // `normal` state, not about the absence of a selection.
    const peeked = view({ hoveredNode: KU1 });
    const lit = mapEdgeStyle(edge(KU1, KU2), edgeInteraction(edge(KU1, KU2), peeked), peeked);
    expect(lit.opacity).toBeGreaterThan(MAP_QUIET_EDGE_OPACITY);
  });

  it("orders the three levels an edge is drawn at", () => {
    // Unrelated with a focus on stage, unrelated with nothing focused, and on
    // the active path -- in the order a reader meets them.
    const focused = view({ selectedNode: KU1 });
    expect(MAP_DIMMED_EDGE_OPACITY).toBeLessThan(MAP_QUIET_EDGE_OPACITY);
    expect(MAP_QUIET_EDGE_OPACITY).toBeLessThan(EDGE_INTERACTION.selected.opacity);
    expect(mapEdgeStyle(edge(KU2, C1), "normal", focused).opacity).toBe(MAP_DIMMED_EDGE_OPACITY);
    expect(mapEdgeStyle(edge(KU1, KU2), "selected", focused).opacity).toBe(
      EDGE_INTERACTION.selected.opacity,
    );
  });

  it("leaves the marks at full strength, because a grey field is not a quiet one", () => {
    // ADR 0006 clause 3: marks and structure dominate and text arrives on
    // demand. Quieting both would produce a grey picture rather than a quiet
    // one, so only the web behind the marks is faint.
    const mark = mapNodeStyle(unit("KU-000001"), "normal", view());
    expect(mark.opacity).toBe(NODE_INTERACTION.normal.opacity);
  });
});

describe("de-emphasis is not absence", () => {
  it("dims unrelated structure while a focus is on stage, and keeps it drawn", () => {
    const focused = view({ selectedNode: KU1, neighbourNodes: new Set([KU2]) });
    const unrelated = mapNodeStyle(concept("C-000001"), "normal", focused);
    expect(unrelated.opacity).toBe(MAP_DIMMED_NODE_OPACITY);
    expect(unrelated.opacity).toBeGreaterThan(MAP_MIN_VISIBLE_OPACITY);
    expect(unrelated.visibility).toBe("visible");

    const unrelatedEdge = mapEdgeStyle(edge(KU2, C1), "normal", focused);
    expect(unrelatedEdge.opacity).toBe(MAP_DIMMED_EDGE_OPACITY);
    expect(unrelatedEdge.opacity).toBeGreaterThan(MAP_MIN_VISIBLE_OPACITY);
    expect(unrelatedEdge.visibility).toBe("visible");
  });

  it("dims nothing at all when nothing is focused", () => {
    expect(hasFocus(view())).toBe(false);
    expect(mapNodeStyle(unit("KU-000001"), "normal", view()).opacity).toBe(1);
  });

  it("never draws anything at or below the visible floor", () => {
    const focused = view({ selectedNode: KU1 });
    for (const interaction of MAP_INTERACTIONS) {
      for (const state of [view(), focused]) {
        expect(mapNodeStyle(unit("KU-000001"), interaction, state).opacity).toBeGreaterThan(
          MAP_MIN_VISIBLE_OPACITY,
        );
        expect(mapEdgeStyle(edge(KU1, KU2), interaction, state).opacity).toBeGreaterThan(
          MAP_MIN_VISIBLE_OPACITY,
        );
      }
    }
  });
});

describe("what the marks say", () => {
  it("never draws a whole statement, at any zoom or in any state", () => {
    // D-122's finding, as an assertion: a knowledge unit's label is its entire
    // `normalized_statement`, and 86 of those at once is the pile that hid the
    // graph. The full text lives in the record and in Quick Read.
    const long = unit("KU-000001", {
      label: "A sentence long enough to be a real one. ".repeat(20),
    });
    for (const interaction of MAP_INTERACTIONS) {
      const style = mapNodeStyle(long, interaction, view());
      expect(style.label).not.toBeNull();
      expect(isTruncated(style.label)).toBe(true);
      expect(Array.from(style.label ?? "").length).toBeLessThanOrEqual(
        MAP_LABEL_CHARS[interaction] + MAP_LABEL_ELLIPSIS.length,
      );
      expect(long.label?.startsWith((style.label ?? "").slice(0, -1))).toBe(true);
    }
  });

  it("names the real relation on an active path, and nothing on the rest", () => {
    const focused = view({ selectedNode: KU1 });
    const active = mapEdgeStyle(expressesConcept(KU1, C1), "selected", focused);
    expect(active.label).toBe("expresses_concept");
    expect(active.labelVisibility).toBe("visible");

    const quiet = mapEdgeStyle(edge(KU2, C1), "normal", focused);
    expect(quiet.label).toBeNull();
    expect(quiet.labelVisibility).toBe("hidden");
  });

  it("draws no label for a node whose record states none", () => {
    const unlabelled = unit("KU-000001", { label: null });
    expect(mapNodeStyle(unlabelled, "selected", view()).label).toBeNull();
  });
});

describe("MapStyle, and the graph it must not touch", () => {
  function sample(): GraphSnapshot {
    const snapshot = new GraphSnapshot({});
    snapshot.applyPage(
      payload({
        nodes: [unit("KU-000001"), unit("KU-000002"), concept("C-000001")],
        edges: [edge(KU1, KU2), expressesConcept(KU1, C1)],
      }),
      page(),
    );
    return snapshot;
  }

  it("styles every node and edge of the real snapshot without writing to it", () => {
    // D-124, from the other side: the reducers are the whole styling path, so
    // running them over the graph is the strongest available statement that
    // styling adds no attribute to it.
    const style = new MapStyle();
    const graph = sample().graph;
    style.setView({ selectedNode: KU1, neighbourNodes: new Set([KU2, C1]) });

    graph.forEachNode((key, attributes) => {
      const drawn = style.nodeReducer(key, {}, attributes, { isHovered: false });
      expect(drawn.size).toBeGreaterThan(0);
    });
    graph.forEachEdge((key, attributes) => {
      const drawn = style.edgeReducer(key, {}, attributes);
      expect(drawn.size).toBeGreaterThan(0);
    });

    graph.forEachNode((_key, attributes) => {
      expect(Object.keys(attributes).sort()).toEqual(["record", "x", "y"]);
    });
    graph.forEachEdge((_key, attributes) => {
      expect(Object.keys(attributes)).toEqual(["record"]);
    });
  });

  it("draws the selection through the reducer, not only through the table", () => {
    const style = new MapStyle();
    const attributes = nodeAttributes(unit("KU-000001"));
    expect(style.nodeReducer(KU1, {}, attributes, { isHovered: false }).labelVisibility).toBe(
      "auto",
    );

    style.setView({ selectedNode: KU1 });
    const selected = style.nodeReducer(KU1, {}, attributes, { isHovered: false });
    expect(selected.labelVisibility).toBe("visible");
    expect(selected.depth).toBe("topNodes");

    const active = style.edgeReducer("e", {}, edgeAttributes(edge(KU1, KU2)));
    expect(active.label).toBe("supports");
    expect(active.depth).toBe("topEdges");
  });

  it("reports whether a view change is actually a change", () => {
    // A pointer moving inside the node it is already on must not cost a
    // redraw, and a redraw is what `MapSession.refresh()` costs.
    const style = new MapStyle();
    expect(style.setView({ hoveredNode: KU1 })).toBe(true);
    expect(style.setView({ hoveredNode: KU1 })).toBe(false);
    expect(style.setView({ neighbourNodes: new Set([KU2]) })).toBe(true);
    expect(style.setView({ neighbourNodes: new Set([KU2]) })).toBe(false);
    expect(style.setView({ neighbourNodes: new Set([C1]) })).toBe(true);
    expect(style.view.selectedNode).toBeNull();
    expect(style.clear()).toBe(true);
    expect(style.clear()).toBe(false);
    expect(style.view).toEqual(EMPTY_VIEW_STATE);
  });

  it("is a pure function of the record and the state", () => {
    // Two calls, one record: the same drawing. Nothing here reads a clock, a
    // counter or an insertion order, which is what lets a reload reproduce the
    // picture the user last saw.
    const record: EntityRef = unit("KU-000001");
    const relation: IndexedRelation = edge(KU1, KU2);
    const state = view({ selectedNode: KU1 });
    expect(mapNodeStyle(record, "selected", state)).toEqual(mapNodeStyle(record, "selected", state));
    expect(mapEdgeStyle(relation, "selected", state)).toEqual(
      mapEdgeStyle(relation, "selected", state),
    );
  });
});
