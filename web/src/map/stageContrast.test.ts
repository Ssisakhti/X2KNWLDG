/**
 * The contrast the *canvas* owes, as a rule.
 *
 * `styles/contrast.test.ts` measures the palette in `tokens.css` and says why a
 * number nobody checks is a token that can be, and was, edited to a value no
 * one can read. It reads a stylesheet, so everything it protects is DOM. The
 * Map draws its labels on a WebGL canvas from tables in `mapStyle.ts` and
 * `sourceStyle.ts` — no stylesheet, and therefore no coverage. Seventeen inks
 * sat outside every check in the project.
 *
 * They were one table, described in `mapStyle.ts` as "a single set of mid-tone
 * values chosen to stay legible on both the light (`#fbfaf8`) and dark
 * (`#17161a`) stage". That is not a matter of taste and it is not true. The
 * first assertion below is the proof, kept as a test rather than as a comment
 * because it is the reason this file exists: the two luminance windows are
 * disjoint, so **no colour whatsoever** clears 4.5:1 on both grounds, and the
 * old table could only ever have been legible on one stage at a time. Measured
 * against the old values: eleven of seventeen failed on light, ten failed on
 * dark, four failed on both.
 *
 * Two rules run through the assertions, and they are different rules because
 * WCAG makes them different:
 *
 * 1. **A label is text.** A node's and an edge's label are words drawn on the
 *    canvas at `--text-xs`-to-`--text-sm` sizes, so SC 1.4.3 asks **4.5:1** of
 *    the ink against the ground it is drawn on. `mapNodeStyle` sets
 *    `labelColor` to the mark's own hue, so the mark's hue *is* a text colour
 *    and is held to the text number.
 * 2. **A mark is a graphical object.** SC 1.4.11 asks **3:1** of it. That is a
 *    weaker bar, and — unlike the text one — a single table could satisfy it on
 *    both stages. The marks are held to 4.5:1 here anyway, because they share
 *    the label's value and the stronger of two requirements on one number is
 *    the one that binds.
 *
 * Ratios are WCAG 2.x relative luminance, computed here rather than imported so
 * that the assertion does not depend on the thing it is checking.
 */

import { describe, expect, it } from "vitest";

import { KIND_FAMILIES, KIND_FAMILY_INK, EDGE_PROVENANCE_INK } from "./mapStyle";
import { SOURCE_MEDIUM_INK, SOURCE_RELATION_INK, UNRECOGNISED_MEDIUM_INK } from "./sourceStyle";
import type { MapStage } from "./stage";

/** The two grounds, and they are `--bg`'s two values in `tokens.css`. */
const GROUND: Record<MapStage, string> = { light: "#fbfaf8", dark: "#17161a" };

const STAGES: readonly MapStage[] = ["light", "dark"];

/** SC 1.4.3 for text at the sizes this Map draws. */
const TEXT_CONTRAST = 4.5;

function channel(value: number): number {
  const srgb = value / 255;
  return srgb <= 0.03928 ? srgb / 12.92 : ((srgb + 0.055) / 1.055) ** 2.4;
}

function luminance(hex: string): number {
  const red = channel(parseInt(hex.slice(1, 3), 16));
  const green = channel(parseInt(hex.slice(3, 5), 16));
  const blue = channel(parseInt(hex.slice(5, 7), 16));
  return 0.2126 * red + 0.7152 * green + 0.0722 * blue;
}

function contrast(one: string, other: string): number {
  const first = luminance(one);
  const second = luminance(other);
  return (Math.max(first, second) + 0.05) / (Math.min(first, second) + 0.05);
}

/** Every canvas ink of *stage*, by the name it is known under. */
function inksOf(stage: MapStage): Record<string, string> {
  const inks: Record<string, string> = {};
  for (const family of KIND_FAMILIES) inks[`kind.${family}`] = KIND_FAMILY_INK[stage][family];
  for (const [provenance, mark] of Object.entries(EDGE_PROVENANCE_INK[stage])) {
    inks[`edge.${provenance}`] = mark.colour;
  }
  for (const [medium, mark] of Object.entries(SOURCE_MEDIUM_INK[stage])) {
    inks[`medium.${medium}`] = mark.colour;
  }
  inks["medium.unrecognised"] = UNRECOGNISED_MEDIUM_INK[stage].colour;
  inks["sourceRelation"] = SOURCE_RELATION_INK[stage];
  return inks;
}

describe("one canvas palette for both stages is arithmetically impossible", () => {
  it("has no colour that clears 4.5:1 on both grounds, at any hue", () => {
    // An ink clears 4.5:1 on a ground when its luminance is far enough from the
    // ground's. Solving each direction gives the widest window a colour could
    // occupy, independent of hue — so if these two do not overlap, no hue helps.
    const lightest = (luminance(GROUND.light) + 0.05) / TEXT_CONTRAST - 0.05;
    const darkest = TEXT_CONTRAST * (luminance(GROUND.dark) + 0.05) - 0.05;

    expect(lightest).toBeCloseTo(0.1737, 4);
    expect(darkest).toBeCloseTo(0.2124, 4);
    // Disjoint: an ink legible on the light stage is too dark for the dark one.
    expect(lightest).toBeLessThan(darkest);
  });
});

describe("every canvas ink is legible on the stage it is drawn on", () => {
  for (const stage of STAGES) {
    const ground = GROUND[stage];
    it(`clears ${TEXT_CONTRAST}:1 against ${ground} on the ${stage} stage`, () => {
      const failures: string[] = [];
      for (const [name, ink] of Object.entries(inksOf(stage))) {
        const ratio = contrast(ink, ground);
        if (ratio < TEXT_CONTRAST) failures.push(`${name} ${ink} ${ratio.toFixed(2)}:1`);
      }
      expect(failures).toEqual([]);
    });

    it(`states every ${stage} ink as a six-digit hex the renderer can parse`, () => {
      for (const [name, ink] of Object.entries(inksOf(stage))) {
        expect(ink, name).toMatch(/^#[0-9a-f]{6}$/);
      }
    });
  }

  it("keeps the fourteen families mutually distinct on both stages", () => {
    for (const stage of STAGES) {
      const inks = KIND_FAMILIES.map((family) => KIND_FAMILY_INK[stage][family]);
      expect(new Set(inks).size, stage).toBe(KIND_FAMILIES.length);
    }
  });

  it("gives both stages the same set of names, so neither can gain an ink alone", () => {
    expect(Object.keys(inksOf("light")).sort()).toEqual(Object.keys(inksOf("dark")).sort());
  });
});
