/**
 * The legend says what the marks say (`T-205`).
 *
 * The legend is the half of ADR 0005 invariant 9 that lives in the DOM: the
 * canvas separates provenance by shape rather than by colour, and a shape
 * means nothing until this component says which shape means what. So these
 * tests do not check that the legend renders *something* -- they check it
 * against `map/mapStyle.ts`'s tables, entry by entry, which is what makes
 * "the legend agrees with the marks" true after a palette change rather than
 * only on the day it was written.
 *
 * The other thing asserted here is that no row is a colour on its own. A
 * legend whose entries were swatches would reintroduce the exact distinction
 * the canvas was built to avoid.
 */

import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PROVENANCE_CLASSES, RELATION_VOCABULARIES } from "../api/vocabulary";
import {
  edgeProvenanceMarks,
  EDGE_VOCABULARY_MARK,
  KIND_FAMILIES,
  kindFamilyColour,
  NODE_PROVENANCE_MARK,
  unrecognisedEdgeProvenanceMark,
  UNRECOGNISED_PROVENANCE_MARK,
  UNRECOGNISED_VOCABULARY_MARK,
} from "../map/mapStyle";

// The three canvas ink tables are per stage now (`map/stage.ts`): no single
// colour clears 4.5:1 on both `#fbfaf8` and `#17161a`, so there cannot be one
// table. jsdom has no `matchMedia`, so `mapStage()` answers `light` here and
// these bindings are the light stage's inks -- the values this suite always read.
const EDGE_PROVENANCE_MARK = edgeProvenanceMarks("light");
const KIND_FAMILY_COLOUR = kindFamilyColour("light");
const UNRECOGNISED_EDGE_PROVENANCE_MARK = unrecognisedEdgeProvenanceMark("light");
import { renderApp } from "../test/render";
import { MapLegend } from "./MapLegend";

function rows(attribute: string): HTMLElement[] {
  return Array.from(document.querySelectorAll<HTMLElement>(`[${attribute}]`));
}

describe("the Map legend", () => {
  it("names every provenance class by the shape the canvas actually draws", () => {
    renderApp(<MapLegend />);
    for (const provenance of PROVENANCE_CLASSES) {
      const row = document.querySelector<HTMLElement>(
        `[data-map-legend-provenance="${provenance}"]`,
      );
      expect(row).not.toBeNull();
      expect(row?.dataset.shape).toBe(NODE_PROVENANCE_MARK[provenance].shape);
    }
    // Four rows, not three: a provenance class this build does not recognise
    // is a state the legend describes rather than a gap in it.
    expect(rows("data-map-legend-provenance")).toHaveLength(PROVENANCE_CLASSES.length + 1);
    expect(
      document.querySelector<HTMLElement>('[data-map-legend-provenance="unrecognised"]')?.dataset
        .shape,
    ).toBe(UNRECOGNISED_PROVENANCE_MARK.shape);
  });

  it("names every relation vocabulary by its head, and every edge provenance by its tail", () => {
    renderApp(<MapLegend />);
    for (const vocabulary of RELATION_VOCABULARIES) {
      const row = document.querySelector<HTMLElement>(
        `[data-map-legend-vocabulary="${vocabulary}"]`,
      );
      expect(row?.dataset.head).toBe(EDGE_VOCABULARY_MARK[vocabulary].head);
    }
    expect(
      document.querySelector<HTMLElement>('[data-map-legend-vocabulary="unrecognised"]')?.dataset
        .head,
    ).toBe(UNRECOGNISED_VOCABULARY_MARK.head);

    for (const provenance of PROVENANCE_CLASSES) {
      const row = document.querySelector<HTMLElement>(
        `[data-map-legend-edge-provenance="${provenance}"]`,
      );
      expect(row?.dataset.tail).toBe(EDGE_PROVENANCE_MARK[provenance].tail);
      expect(row?.dataset.colour).toBe(EDGE_PROVENANCE_MARK[provenance].colour);
    }
    expect(
      document.querySelector<HTMLElement>('[data-map-legend-edge-provenance="unrecognised"]')
        ?.dataset.tail,
    ).toBe(UNRECOGNISED_EDGE_PROVENANCE_MARK.tail);
  });

  it("lists every kind family with the colour the reducer uses for it", () => {
    renderApp(<MapLegend />);
    const listed = rows("data-map-legend-family");
    expect(listed).toHaveLength(KIND_FAMILIES.length);
    for (const family of KIND_FAMILIES) {
      const row = document.querySelector<HTMLElement>(`[data-map-legend-family="${family}"]`);
      expect(row?.dataset.colour).toBe(KIND_FAMILY_COLOUR[family]);
    }
  });

  it("never states a distinction with a colour alone", () => {
    renderApp(<MapLegend />);
    const everyRow = [
      ...rows("data-map-legend-provenance"),
      ...rows("data-map-legend-vocabulary"),
      ...rows("data-map-legend-edge-provenance"),
      ...rows("data-map-legend-family"),
    ];
    expect(everyRow.length).toBeGreaterThan(0);
    for (const row of everyRow) {
      // The glyph is `aria-hidden` decoration; the row's meaning is words, and
      // a row with only a mark in it would be a colour-only legend entry.
      const words = row.querySelector("span:not([aria-hidden])")?.textContent ?? "";
      expect(words.trim().length).toBeGreaterThan(1);
    }
  });

  it("says that shape carries the distinction, and that kind is not a filter", () => {
    renderApp(<MapLegend />);
    expect(screen.getByText(/Shape carries provenance and vocabulary/)).toBeDefined();
    // ADR 0005 invariant 7, stated where a reader would otherwise ask for the
    // control: `GET /api/graph` accepts no `kind`.
    expect(screen.getByText(/GET \/api\/graph does not accept one/)).toBeDefined();
  });

  it("is complete in Persian as well, rather than falling back to a key", () => {
    renderApp(<MapLegend />, { locale: "fa" });
    const legend = document.querySelector<HTMLElement>("[data-map-legend]");
    expect(legend).not.toBeNull();
    const text = legend?.textContent ?? "";
    expect(text).not.toContain("undefined");
    expect(text).toContain("لوزی");
    // The rows are still keyed off the same tables in either locale.
    expect(rows("data-map-legend-family")).toHaveLength(KIND_FAMILIES.length);
  });
});
