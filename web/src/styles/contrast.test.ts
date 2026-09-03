/**
 * The contrast the palette owes, as a stylesheet rule.
 *
 * The same argument as `logical.test.ts`, `accessibility.test.ts` and
 * `visualSystem.test.ts`, and the one gap they left. Those three assert that
 * motion is answered, that a target is big enough, that an identifier is
 * isolated and that provenance survives greyscale -- and none of them ever
 * looks at a *number*. So a token could be, and was, edited to a value that no
 * one could read, and every one of the 654 frontend tests stayed green.
 *
 * Two rules run through this file, and neither is a style preference:
 *
 * 1. **A value the canonical data does not state is not a lesser value.**
 *    ADR 0001 invariant 2 says an honest incomplete result must not read as a
 *    weaker version of a good one, and `.missing` -- the class that renders
 *    "not stated" -- is the place that promise is kept or broken. A greyed-out
 *    "not stated" *is* the invariant failing, whatever the components do.
 * 2. **A control is identified by its border.** WCAG 2.2 SC 1.4.11 asks 3:1 of
 *    the visual information needed to identify a control, and an empty search
 *    field has nothing else: its border is the whole affordance. `T-215`'s own
 *    capture at 2852x1688 shows the Map's search input reading as blank space
 *    for exactly this reason.
 *
 * The pairs below are every ground a token is actually painted on, not every
 * combination the palette permits: `--fg-faint` is used on `--bg-sunken` by
 * `.map__float`, so `--bg-sunken` is the ground that has to hold, and the
 * worst ground is the one the assertion uses.
 *
 * Ratios are WCAG 2.x relative luminance. `4.5` is SC 1.4.3 for text at the
 * sizes this UI uses -- `--text-xs` through `--text-lg` are all below the
 * large-text threshold -- and `3` is SC 1.4.11 for a control's boundary.
 */

import { describe, expect, it } from "vitest";

import tokens from "./tokens.css?raw";

/* The token tables ------------------------------------------------------ */

/**
 * The declarations inside the first at-rule whose prelude matches, or the
 * whole sheet's bare `:root` when no prelude is given.
 *
 * Written by hand rather than with a CSS parser for the same reason the three
 * sibling suites do it: the dependency would be one more thing to keep, and
 * the shape being read here is two flat blocks of custom properties.
 */
function block(prelude: RegExp | null): string {
  if (prelude === null) {
    // The light palette is the bare `:root`, which is the first rule in the
    // file; the dark one is a `:root` nested inside a media query.
    const start = tokens.search(/^:root\s*\{/m);
    if (start < 0) return "";
    const end = tokens.indexOf("\n}", start);
    return end < 0 ? "" : tokens.slice(start, end);
  }
  const start = tokens.search(prelude);
  if (start < 0) return "";
  let depth = 0;
  for (let index = start; index < tokens.length; index += 1) {
    if (tokens[index] === "{") depth += 1;
    if (tokens[index] === "}") {
      depth -= 1;
      if (depth === 0) return tokens.slice(start, index + 1);
    }
  }
  return "";
}

/** Every `--name: #rrggbb` in a block, lower-cased. */
function palette(source: string): Record<string, string> {
  const found: Record<string, string> = {};
  for (const match of source.matchAll(/(--[a-z0-9-]+):\s*(#[0-9a-fA-F]{6})\s*;/g)) {
    found[match[1] as string] = (match[2] as string).toLowerCase();
  }
  return found;
}

const LIGHT = palette(block(null));
const DARK = { ...LIGHT, ...palette(block(/@media \(prefers-color-scheme: dark\)/)) };

/* The ratio ------------------------------------------------------------- */

function channel(value: number): number {
  const unit = value / 255;
  return unit <= 0.04045 ? unit / 12.92 : ((unit + 0.055) / 1.055) ** 2.4;
}

/** WCAG 2.x relative luminance. */
function luminance(hex: string): number {
  const [red, green, blue] = [1, 3, 5].map((at) => channel(parseInt(hex.slice(at, at + 2), 16)));
  return 0.2126 * (red as number) + 0.7152 * (green as number) + 0.0722 * (blue as number);
}

function contrast(a: string, b: string): number {
  const [high, low] = [luminance(a), luminance(b)].sort((x, y) => y - x) as [number, number];
  return (high + 0.05) / (low + 0.05);
}

/* The pairs ------------------------------------------------------------- */

/** `[foreground, background, minimum, why]`. */
type Pair = readonly [string, string, number, string];

/**
 * Text. Every ground each token is painted on, worst first -- `--bg-sunken`
 * under a floating Map surface, `--bg-raised` under a card, `--bg` on the page.
 */
const TEXT: readonly Pair[] = [
  ["--fg", "--bg", 4.5, "body text on the page"],
  ["--fg", "--bg-raised", 4.5, "body text on a card"],
  ["--fg", "--bg-sunken", 4.5, "body text on a sunken surface"],
  ["--fg-muted", "--bg", 4.5, ".muted, a definition term"],
  ["--fg-muted", "--bg-raised", 4.5, ".muted on a card"],
  ["--fg-muted", "--bg-sunken", 4.5, ".muted on a sunken surface"],
  // The three below are the ones this suite was written for.
  ["--fg-faint", "--bg", 4.5, ".faint -- a count, a note, a hop label"],
  ["--fg-faint", "--bg-raised", 4.5, ".faint on a card"],
  ["--fg-faint", "--bg-sunken", 4.5, ".faint on a floating Map surface"],
  ["--missing-fg", "--bg", 4.5, '.missing -- "not stated" (ADR 0001 invariant 2)'],
  ["--missing-fg", "--bg-raised", 4.5, '.missing on a card'],
  ["--accent", "--bg", 4.5, "a link, a focused card's ring"],
  ["--accent", "--bg-raised", 4.5, "a link on a card"],
  ["--accent-contrast", "--accent", 4.5, "the label on a pressed button"],
  ["--provenance-source-fg", "--provenance-source-bg", 4.5, "the source badge"],
  ["--provenance-derived-fg", "--provenance-derived-bg", 4.5, "the derived badge"],
  ["--provenance-user-fg", "--provenance-user-bg", 4.5, "the user badge"],
  ["--status-pass-fg", "--status-pass-bg", 4.5, "a PASS chip"],
  // PARTIAL and FAIL are held to the same number as PASS on purpose: ADR 0001
  // invariant 2 again, one level down. An honest bad result that is harder to
  // read than a good one is the same failure in a different place.
  ["--status-partial-fg", "--status-partial-bg", 4.5, "a PARTIAL chip"],
  ["--status-fail-fg", "--status-fail-bg", 4.5, "a FAIL chip"],
  ["--status-unknown-fg", "--status-unknown-bg", 4.5, "an UNKNOWN chip"],
];

/**
 * Non-text. SC 1.4.11 -- the boundary that says "this is a control".
 *
 * `--border` is deliberately absent: it draws a panel's edge and a rule
 * between rows, which are decoration beside content that is already legible,
 * and holding a hairline divider to 3:1 would turn the quiet editorial field
 * ADR 0006 asks for into a wireframe. `--border-strong` is the one that draws
 * controls -- `.button`, `.field > select`, `.field > input`, `.notice`,
 * `.shell__skip` -- so it is the one that has to carry the number.
 */
const CONTROL: readonly Pair[] = [
  ["--border-strong", "--bg", 3, "a control's edge on the page"],
  ["--border-strong", "--bg-raised", 3, "a control's edge on a card"],
  ["--focus", "--bg", 3, "the focus ring on the page"],
  ["--focus", "--bg-raised", 3, "the focus ring on a card"],
];

const THEMES: readonly [string, Record<string, string>][] = [
  ["light", LIGHT],
  ["dark", DARK],
];

describe("the palette parses", () => {
  it("finds both themes", () => {
    // If this fails the rest of the suite is asserting nothing, which is the
    // one way a mechanical check like this goes quietly wrong.
    expect(Object.keys(LIGHT).length).toBeGreaterThan(20);
    expect(Object.keys(DARK).length).toBeGreaterThan(20);
    expect(DARK["--bg"]).not.toBe(LIGHT["--bg"]);
  });
});

for (const [theme, values] of THEMES) {
  describe(`${theme}: text carries its contrast`, () => {
    for (const [fg, bg, minimum, why] of TEXT) {
      it(`${fg} on ${bg} -- ${why}`, () => {
        const front = values[fg];
        const ground = values[bg];
        expect(front, `${fg} is not a hex value in the ${theme} palette`).toBeDefined();
        expect(ground, `${bg} is not a hex value in the ${theme} palette`).toBeDefined();
        const ratio = contrast(front as string, ground as string);
        expect(
          Number(ratio.toFixed(2)),
          `${fg} (${front}) on ${bg} (${ground}) is ${ratio.toFixed(2)}:1, below ${minimum}:1`,
        ).toBeGreaterThanOrEqual(minimum);
      });
    }
  });

  describe(`${theme}: a control's boundary carries its contrast`, () => {
    for (const [fg, bg, minimum, why] of CONTROL) {
      it(`${fg} on ${bg} -- ${why}`, () => {
        const front = values[fg];
        const ground = values[bg];
        expect(front, `${fg} is not a hex value in the ${theme} palette`).toBeDefined();
        expect(ground, `${bg} is not a hex value in the ${theme} palette`).toBeDefined();
        const ratio = contrast(front as string, ground as string);
        expect(
          Number(ratio.toFixed(2)),
          `${fg} (${front}) on ${bg} (${ground}) is ${ratio.toFixed(2)}:1, below ${minimum}:1`,
        ).toBeGreaterThanOrEqual(minimum);
      });
    }
  });

  describe(`${theme}: the quiet steps stay a hierarchy`, () => {
    it("orders --fg, --fg-muted and --fg-faint by distance from the ground", () => {
      // Raising a token to reach 4.5:1 is only half the fix. The three greys
      // mean three levels of emphasis, and a palette where `.faint` reads as
      // loud as `.muted` has traded one defect for another.
      const ground = values["--bg"] as string;
      const steps = ["--fg", "--fg-muted", "--fg-faint"].map((name) =>
        contrast(values[name] as string, ground),
      );
      expect(steps[0] as number).toBeGreaterThan(steps[1] as number);
      expect(steps[1] as number).toBeGreaterThan(steps[2] as number);
    });
  });
}
