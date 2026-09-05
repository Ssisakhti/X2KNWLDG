/**
 * What the Source Map's style table draws, and — mostly — what it refuses to.
 *
 * The refusals are the reason this file is long. D-247 and D-274 are decisions
 * about records, and a decision about records is only kept if the *drawing*
 * keeps it: a table that quietly sized a mark by `basis_total` would satisfy
 * every schema in the project and still put a ranking on the field. So each
 * refusal is asserted the only way a refusal can be — by moving the value it
 * refuses to read and showing that nothing moved.
 */

import { describe, expect, it } from "vitest";

import { EMPTY_VIEW_STATE, edgeFieldScale } from "./mapStyle";
import {
  EMPTY_SOURCE_VIEW_STATE,
  SOURCE_BRIEF_MARK,
  SOURCE_EDGE_SIZE,
  SOURCE_MARK_SIZE,
  SOURCE_MEDIUM_INK,
  SourceStyle,
  sourceBriefMark,
  sourceEdgeInteraction,
  sourceEdgeStyle,
  sourceMediumMark,
  sourceNodeStyle,
  type SourceViewState,
} from "./sourceStyle";

// Per stage now (`map/stage.ts`): no one ink clears 4.5:1 on both grounds.
// jsdom has no `matchMedia`, so `mapStage()` answers `light` throughout this suite.
const SOURCE_MEDIUM_MARK = SOURCE_MEDIUM_INK.light;
import { PASS, POST, sourceNode, summary } from "../test/sourceRecords";

const FIELD = 1280;

function view(overrides: Partial<SourceViewState> = {}): SourceViewState {
  return { ...EMPTY_SOURCE_VIEW_STATE, ...overrides };
}

describe("the refusals", () => {
  it("draws every relationship at one weight, whatever its basis carries", () => {
    const one = sourceEdgeStyle(summary(POST, PASS, { basis_total: 1 }), "normal", view(), FIELD);
    const forty = sourceEdgeStyle(
      summary(POST, PASS, { basis_total: 40 }),
      "normal",
      view(),
      FIELD,
    );
    expect(one.size).toBe(forty.size);
    // And it is the declared constant scaled by the field and by nothing else,
    // so a future change has to move the constant rather than drift the drawing.
    const quiet = sourceEdgeStyle(summary(POST, PASS), "normal", view(), FIELD);
    expect(quiet.size).toBeCloseTo(SOURCE_EDGE_SIZE * edgeFieldScale(FIELD), 5);
  });

  it("draws every source at one size, whatever it is", () => {
    const youtube = sourceNodeStyle(sourceNode(PASS), "normal", view(), FIELD);
    const twitter = sourceNodeStyle(sourceNode(POST), "normal", view(), FIELD);
    expect(youtube.size).toBe(twitter.size);
  });

  it("never states a freshness, because no record carries one", () => {
    const style = sourceEdgeStyle(summary(POST, PASS), "selected", view(), FIELD);
    // Every field of the display, and none of them is a freshness channel.
    expect(Object.keys(style).sort()).toEqual(
      [
        "color",
        "depth",
        "head",
        "label",
        "labelColor",
        "labelVisibility",
        "opacity",
        "parallelPath",
        "size",
        "tail",
        "visibility",
        "zIndex",
      ].sort(),
    );
  });

  it("gives every relationship the same colour, because provenance has one value", () => {
    const a = sourceEdgeStyle(summary(POST, PASS, { relation_type: "supports" }), "normal", view(), FIELD);
    const b = sourceEdgeStyle(
      summary(POST, PASS, { relation_type: "contradicts" }),
      "normal",
      view(),
      FIELD,
    );
    expect(a.color).toBe(b.color);
  });
});

describe("the two added channels", () => {
  it("gives each medium a hue and a glyph, so neither is colour alone", () => {
    for (const [medium, mark] of Object.entries(SOURCE_MEDIUM_MARK)) {
      expect(mark.colour).toMatch(/^#[0-9a-f]{6}$/i);
      expect(mark.glyph.length).toBeGreaterThan(0);
      expect(sourceMediumMark(medium)).toBe(mark);
    }
  });

  it("never rounds an unknown medium onto a known one", () => {
    const unknown = sourceMediumMark("medium");
    expect(unknown).not.toBe(SOURCE_MEDIUM_MARK.youtube);
    expect(unknown).not.toBe(SOURCE_MEDIUM_MARK.twitter);
    expect(sourceMediumMark(null)).toBe(unknown);
  });

  it("fills a mark with a brief and hollows one without", () => {
    expect(SOURCE_BRIEF_MARK.available.filled).toBe(true);
    expect(SOURCE_BRIEF_MARK.stale.filled).toBe(true);
    expect(SOURCE_BRIEF_MARK.unavailable.filled).toBe(false);
    // Stale is neither of the other two: carried, and marked as carried.
    expect(SOURCE_BRIEF_MARK.stale.ring).toBe(true);
    expect(SOURCE_BRIEF_MARK.available.ring).toBe(false);
  });

  it("reads a state it does not know as no brief, which is the honest under-claim", () => {
    expect(sourceBriefMark("refreshing")).toBe(SOURCE_BRIEF_MARK.unavailable);
    expect(sourceBriefMark(undefined)).toBe(SOURCE_BRIEF_MARK.unavailable);
  });

  it("draws a source with no known brief state hollow", () => {
    const style = sourceNodeStyle(sourceNode(PASS), "normal", view(), FIELD);
    expect(style.color).toBe("transparent");
    expect(style.backdropVisibility).toBe("visible");
  });

  it("draws a source with a current brief filled, in its medium's hue", () => {
    const node = sourceNode(PASS);
    const style = sourceNodeStyle(
      node,
      "normal",
      view({ briefStates: new Map([[node.global_id, "available"]]) }),
      FIELD,
    );
    expect(style.color).toBe(SOURCE_MEDIUM_MARK.youtube?.colour);
  });
});

describe("direction and scope", () => {
  it("puts an arrowhead on every edge, at every interaction", () => {
    for (const interaction of ["normal", "selected", "hovered", "neighbour"] as const) {
      expect(sourceEdgeStyle(summary(POST, PASS), interaction, view(), FIELD).head).toBe("arrow");
    }
  });

  it("marks a partial scope and leaves a broad one unmarked", () => {
    expect(sourceEdgeStyle(summary(POST, PASS, { scope: "partial" }), "normal", view(), FIELD).tail)
      .not.toBe("none");
    expect(sourceEdgeStyle(summary(POST, PASS, { scope: "broad" }), "normal", view(), FIELD).tail)
      .toBe("none");
  });

  it("lights an edge from the selected source's own two-part id", () => {
    const selected = view({ selectedNode: `${PASS}:source` });
    expect(sourceEdgeInteraction(summary(POST, PASS), selected)).toBe("selected");
    expect(sourceEdgeInteraction(summary(POST, "youtube:other"), selected)).toBe("normal");
  });

  it("lights nothing when the selection is not a three-part id", () => {
    expect(sourceEdgeInteraction(summary(POST, PASS), view({ selectedNode: "nonsense" }))).toBe(
      "normal",
    );
  });
});

describe("the table", () => {
  it("reports whether a view change was a change", () => {
    const style = new SourceStyle();
    expect(style.setView({ selectedNode: `${PASS}:source` })).toBe(true);
    expect(style.setView({ selectedNode: `${PASS}:source` })).toBe(false);
    expect(style.setView({ briefStates: new Map([["a", "available"]]) })).toBe(true);
    expect(style.setView({ briefStates: new Map([["a", "available"]]) })).toBe(false);
    expect(style.setView({ briefStates: new Map([["a", "stale"]]) })).toBe(true);
  });

  it("starts from the Knowledge Map's empty view plus one map", () => {
    expect(EMPTY_SOURCE_VIEW_STATE.selectedNode).toBe(EMPTY_VIEW_STATE.selectedNode);
    expect(EMPTY_SOURCE_VIEW_STATE.briefStates.size).toBe(0);
  });

  it("keeps the source mark the same size the provenance table gives a source", () => {
    // The two must not drift: every source node *is* `provenance_class: source`.
    expect(SOURCE_MARK_SIZE).toBe(9);
  });
});
