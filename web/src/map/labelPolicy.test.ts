/**
 * D-122's policy, asserted (`T-205`).
 *
 * Two failures are being guarded against here, and they are opposites. The
 * first is the one the `T-202` gate walked into: 86 full sentences drawn at
 * once, a graph hidden by its own annotations. The second is subtler and
 * worse -- a truncation that does not look like one, or a "label" the client
 * composed. ADR 0005 invariant 12 permits visible presentational truncation
 * and forbids client-authored knowledge, so every test below checks that the
 * cut is *visible* and that what remains is a prefix of what the record
 * actually says.
 */

import { describe, expect, it } from "vitest";

import {
  MAP_EDGE_LABEL_CHARS,
  MAP_LABEL_CHARS,
  MAP_LABEL_ELLIPSIS,
  MAP_LABEL_NEIGHBOUR_BUDGET,
  MAP_LABEL_SETTINGS,
  edgeLabelVisibility,
  isTruncated,
  nodeLabelVisibility,
  truncateForDisplay,
} from "./labelPolicy";
import { edge } from "../test/graphRecords";
import { EMPTY_VIEW_STATE, MAP_INTERACTIONS, type MapViewState } from "./mapStyle";

/** A real knowledge-unit label: a whole sentence, which is what `library.py` stores. */
const STATEMENT =
  "The model's autonomy loop is intent, then context, then action, then feedback, and " +
  "removing any one of the four turns the remaining three into a demo rather than a system.";

/** The node under test, and the other end of an edge from it. */
const NODE = "youtube:v:KU-000001";
const OTHER = "youtube:v:KU-000002";

function view(overrides: Partial<MapViewState> = {}): MapViewState {
  return { ...EMPTY_VIEW_STATE, ...overrides };
}

function neighbours(count: number): ReadonlySet<string> {
  return new Set(Array.from({ length: count }, (_value, index) => `youtube:v:KU-${index}`));
}

describe("truncation for display", () => {
  it("returns a value the record does not state as no label at all", () => {
    // Not an empty string: a node with no label must draw none rather than an
    // empty ghost, and `EntityRef.label` is `string | null | undefined`.
    expect(truncateForDisplay(null, 40)).toBeNull();
    expect(truncateForDisplay(undefined, 40)).toBeNull();
    expect(truncateForDisplay("", 40)).toBeNull();
    expect(truncateForDisplay("   \n  ", 40)).toBeNull();
  });

  it("leaves a short statement exactly as the record spells it", () => {
    expect(truncateForDisplay("Autonomy loop", 40)).toBe("Autonomy loop");
    expect(isTruncated(truncateForDisplay("Autonomy loop", 40))).toBe(false);
  });

  it("collapses the whitespace a stored statement can carry", () => {
    // A `normalized_statement` may hold newlines; a WebGL label is one line,
    // so an uncollapsed newline is a gap in the middle of a sentence.
    expect(truncateForDisplay("two\nlines   and  spaces", 60)).toBe("two lines and spaces");
  });

  it("cuts visibly, and never draws more than the budget", () => {
    const drawn = truncateForDisplay(STATEMENT, 42);
    expect(drawn).not.toBeNull();
    expect(isTruncated(drawn)).toBe(true);
    // The budget plus the one character that says there is more.
    expect(Array.from(drawn ?? "").length).toBeLessThanOrEqual(43);
  });

  it("draws a prefix of the stored statement and never a rewrite of it", () => {
    // The whole of invariant 12 in one assertion: what is on the canvas is
    // the beginning of what the index holds, plus a mark saying so.
    const drawn = truncateForDisplay(STATEMENT, 60) ?? "";
    const body = drawn.slice(0, -MAP_LABEL_ELLIPSIS.length);
    expect(STATEMENT.startsWith(body)).toBe(true);
    expect(body.length).toBeGreaterThan(0);
  });

  it("prefers a word boundary, but not one that would leave almost nothing", () => {
    const wordy = truncateForDisplay("alpha beta gamma delta epsilon", 20) ?? "";
    expect(wordy).toBe(`alpha beta gamma${MAP_LABEL_ELLIPSIS}`);

    // The only space is at character 2, far inside the budget: honouring it
    // would draw "a…" for a 20-character budget.
    const unbroken = truncateForDisplay(`a ${"b".repeat(40)}`, 20) ?? "";
    expect(unbroken.startsWith("a bbb")).toBe(true);
    expect(isTruncated(unbroken)).toBe(true);
  });

  it("cuts by code point, so Persian and astral text survive the cut", () => {
    // `slice` on UTF-16 units halves a surrogate pair and draws a replacement
    // character; the extracted knowledge is Persian as often as English.
    const persian = "حلقهٔ خودگردانی: قصد، زمینه، کنش، بازخورد، و بدون هر کدام تنها یک نمایش می‌ماند.";
    const drawn = truncateForDisplay(persian, 20) ?? "";
    expect(Array.from(drawn).length).toBeLessThanOrEqual(21);
    expect(drawn).not.toContain("�");

    const astral = "𝔞𝔟𝔠𝔡𝔢𝔣𝔤𝔥𝔦𝔧𝔨𝔩";
    const cut = truncateForDisplay(astral, 4) ?? "";
    expect(cut).toBe(`𝔞𝔟𝔠𝔡${MAP_LABEL_ELLIPSIS}`);
  });

  it("gives every interaction state a budget, and the focus the largest one", () => {
    for (const interaction of MAP_INTERACTIONS) {
      expect(MAP_LABEL_CHARS[interaction]).toBeGreaterThan(0);
    }
    expect(MAP_LABEL_CHARS.selected).toBeGreaterThan(MAP_LABEL_CHARS.hovered);
    expect(MAP_LABEL_CHARS.hovered).toBeGreaterThan(MAP_LABEL_CHARS.neighbour);
    expect(MAP_LABEL_CHARS.neighbour).toBeGreaterThan(MAP_LABEL_CHARS.normal);
    // Even the most generous budget is a fraction of what a statement may be:
    // `EntityRef.label` runs to 4096 characters, and Quick Read is where the
    // whole of it belongs (D-131).
    expect(MAP_LABEL_CHARS.selected).toBeLessThan(400);
  });
});

describe("label density", () => {
  it("draws no forced label on an unfocused overview", () => {
    // The gate's pile of 86 sentences: with nothing selected, every node is
    // `normal` and every label is left to Sigma's grid and size threshold.
    expect(nodeLabelVisibility(NODE, "normal", view())).toBe("auto");
  });

  it("silences unrelated nodes once something is focused, without removing them", () => {
    const focused = view({ selectedNode: "youtube:v:KU-000001" });
    expect(nodeLabelVisibility(NODE, "normal", focused)).toBe("hidden");
    // "hidden" is the *label*. The mark itself is dimmed, not removed --
    // asserted over in `mapStyle.test.ts`, where visibility lives.
  });

  it("always names the focus and the thing being peeked at", () => {
    const focused = view({ selectedNode: "youtube:v:KU-000001" });
    expect(nodeLabelVisibility(NODE, "selected", focused)).toBe("visible");
    expect(nodeLabelVisibility(NODE, "hovered", focused)).toBe("visible");
    expect(nodeLabelVisibility(NODE, "hovered", view())).toBe("visible");
  });

  it("names the neighbours of a focus up to the stated budget, then hands them back", () => {
    const within = view({
      selectedNode: "youtube:v:KU-000001",
      neighbourNodes: neighbours(MAP_LABEL_NEIGHBOUR_BUDGET),
    });
    expect(nodeLabelVisibility(NODE, "neighbour", within)).toBe("visible");

    const beyond = view({
      selectedNode: "youtube:v:KU-000001",
      neighbourNodes: neighbours(MAP_LABEL_NEIGHBOUR_BUDGET + 1),
    });
    // Over budget costs legibility, never data: the labels go back to Sigma's
    // grid, and every neighbour is still a mark and still in the semantic
    // related list (ADR 0005 invariant 13).
    expect(nodeLabelVisibility(NODE, "neighbour", beyond)).toBe("auto");
  });

  it("forces no more neighbour labels than a real fan-out can show (D-145)", () => {
    // Measured in a browser by `T-209`, not argued: forcing a label on all
    // eight neighbours of the real graph's busiest entity drew nine sentences
    // into a cluster about 250 px across, because ForceAtlas2 pulls a node's
    // neighbours towards it -- a fan-out is the densest part of the picture,
    // which is the worst place to bypass Sigma's label grid. The grid's own
    // budget for that area, at `labelGridCellSize: 180`, is one or two.
    expect(MAP_LABEL_NEIGHBOUR_BUDGET).toBeGreaterThan(0);
    expect(MAP_LABEL_NEIGHBOUR_BUDGET).toBeLessThanOrEqual(4);
  });

  it("draws no label for a node the orbit has given a card (`T-214`)", () => {
    // The same statement twice in the same place, the lower copy under the
    // upper one, is the "no graph label under a card" clause ADR 0006 states.
    // The focused node is *always* carded, so this has to beat `selected`.
    const carded = view({
      selectedNode: NODE,
      neighbourNodes: neighbours(2),
      cardedNodes: new Set([NODE, "youtube:v:KU-0"]),
    });
    expect(nodeLabelVisibility(NODE, "selected", carded)).toBe("hidden");
    expect(nodeLabelVisibility("youtube:v:KU-0", "neighbour", carded)).toBe("hidden");
    // And a neighbour the orbit *counted* rather than placed keeps its label,
    // because nothing else on screen names that one.
    expect(nodeLabelVisibility("youtube:v:KU-1", "neighbour", carded)).toBe("visible");
  });

  it("names a relation only on an active path", () => {
    expect(edgeLabelVisibility(edge(NODE, OTHER), "selected", view())).toBe("visible");
    expect(edgeLabelVisibility(edge(NODE, OTHER), "hovered", view())).toBe("visible");
    expect(edgeLabelVisibility(edge(NODE, OTHER), "neighbour", view())).toBe("hidden");
    expect(edgeLabelVisibility(edge(NODE, OTHER), "normal", view())).toBe("hidden");
  });

  it("leaves a relation to its pill once both its endpoints are carded (`T-214`)", () => {
    const carded = view({ selectedNode: NODE, cardedNodes: new Set([NODE, OTHER]) });
    expect(edgeLabelVisibility(edge(NODE, OTHER), "selected", carded)).toBe("hidden");
    // One endpoint carded is not enough: the other end has no card naming it,
    // so the canvas label is still the only place that relation appears.
    const half = view({ selectedNode: NODE, cardedNodes: new Set([NODE]) });
    expect(edgeLabelVisibility(edge(NODE, OTHER), "selected", half)).toBe("visible");
  });

  it("states the zoom and density rule as settings rather than leaving it to a default", () => {
    // D-122: "the Map must have a stated policy rather than inherit whatever a
    // default draws". `T-209` measured all four in a browser and kept them.
    expect(MAP_LABEL_SETTINGS.renderLabels).toBe(true);
    expect(MAP_LABEL_SETTINGS.renderEdgeLabels).toBe(true);
    expect(MAP_LABEL_SETTINGS.labelDensity).toBeGreaterThan(0);
    // Sigma's defaults are a 100 px grid cell and a 6 px size threshold, which
    // are numbers for dots with short words beside them.
    expect(MAP_LABEL_SETTINGS.labelGridCellSize).toBeGreaterThan(100);
    expect(MAP_LABEL_SETTINGS.labelRenderedSizeThreshold).toBeGreaterThan(6);
  });

  it("keeps a relation name short enough to sit on a line", () => {
    expect(MAP_EDGE_LABEL_CHARS).toBeLessThan(MAP_LABEL_CHARS.normal);
    expect(truncateForDisplay("expresses_concept", MAP_EDGE_LABEL_CHARS)).toBe(
      "expresses_concept",
    );
  });
});
