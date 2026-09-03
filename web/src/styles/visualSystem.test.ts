/**
 * `T-214` as stylesheet rules: hierarchy, and what colour is never allowed to
 * carry on its own (ADR 0006 clause 5, D-154).
 *
 * The same argument as `logical.test.ts` and `accessibility.test.ts`. These are
 * properties of the *whole* stylesheet rather than of any one component, they
 * rot one declaration at a time, and the failure they produce is a screen that
 * still passes every behavioural test. So they are checked mechanically and the
 * failure names what is missing.
 *
 * Three clauses, and each is a rule rather than a number's beauty: provenance
 * is distinguishable without colour, the kind's hue is a cue and never a
 * surface, and the focused card is the centre by more than one means.
 */

import { describe, expect, it } from "vitest";

import base from "./base.css?raw";
import tokens from "./tokens.css?raw";

/** The body of the first rule whose selector matches. */
function rule(source: string, selector: RegExp): string {
  const found = new RegExp(`${selector.source}\\s*\\{[^}]*\\}`).exec(source);
  return found === null ? "" : found[0];
}

const PROVENANCE = ["source", "derived", "user"] as const;

describe("provenance is never signalled by colour alone", () => {
  it("gives each class its own line style, and three different ones", () => {
    // ADR 0001 invariant 10. Three tokens carrying one value each would let a
    // careless edit make two classes identical in greyscale without changing
    // anything a colour test can see.
    const styles = PROVENANCE.map((value) => {
      const found = new RegExp(`--provenance-${value}-border:\\s*([a-z]+)`).exec(tokens);
      return found?.[1] ?? "";
    });
    expect(styles).toEqual(["solid", "dashed", "dotted"]);
    expect(new Set(styles).size).toBe(3);
  });

  it("wears that line style on the card's rail, not only on the badge", () => {
    // A card is what a reader sees on the stage; the badge may be cropped by
    // a narrow card and the rail runs its whole height.
    for (const value of PROVENANCE) {
      const body = rule(base, new RegExp(`\\.card--${value}`));
      expect(body).toMatch(new RegExp(`border-inline-start-style:\\s*var\\(--provenance-${value}-border\\)`));
      expect(body).toMatch(new RegExp(`border-inline-start-color:\\s*var\\(--provenance-${value}-fg\\)`));
    }
  });
});

describe("the kind's hue is a cue, never a surface", () => {
  it("draws it as a small swatch with a stated size", () => {
    // SPEC §6: "Kind hue is a small cue, never a card fill: an 8 px swatch in
    // the badge and the mark's own colour on the stage."
    const swatch = rule(base, /\.badge__swatch/);
    expect(swatch).toMatch(/inline-size:\s*8px/);
    expect(swatch).toMatch(/block-size:\s*8px/);
  });

  it("never fills a card with it", () => {
    // The colour is written inline by `KindBadge` from `KIND_FAMILY_COLOUR`,
    // and the only element that may carry it is the swatch. A card tinted by
    // kind reads as a category with a status, and the only classification this
    // project colours a whole surface with is provenance.
    expect(base).not.toMatch(/\.card[^{]*\{[^}]*--kind/);
    expect(base).not.toMatch(/background:\s*var\(--kind/);
  });
});

describe("the focused card is the centre by more than one means", () => {
  const primary = rule(base, /\.map__card--primary/);

  it("carries a doubled border, an accent ring and a glow", () => {
    expect(primary).toMatch(/border-width:\s*calc\(var\(--border-width\) \* 2\)/);
    expect(primary).toMatch(/outline:\s*1px solid var\(--accent\)/);
    expect(primary).toMatch(/box-shadow:[^;]*var\(--accent\)/);
  });

  it("keeps the rail for provenance rather than spending it on the accent", () => {
    // The accent says "this is the one you asked for"; the rail says where the
    // statement came from. Confusing the two on the one card a reader is
    // actually reading is the worst place to do it.
    expect(primary).toMatch(/border-inline-start-width:\s*var\(--rail-width\)/);
    expect(primary).not.toMatch(/border-inline-start-color/);
  });

  it("adds the ground tint only where a glow reads as weaker", () => {
    // A 4 % accent wash is invisible on a dark field, and the glow is what
    // carries that job there. Stated as "not dark" so the default
    // `color-scheme: light dark` still gets it.
    const tinted = /@media not \(prefers-color-scheme: dark\)\s*\{\s*\.map__card--primary/;
    expect(base).toMatch(tinted);
  });

  it("gives the three card sizes three type sizes", () => {
    // The focused statement is being read, a neighbour's is being judged, and
    // a mark further out carries less by design.
    expect(base).toMatch(/\.map__card--primary[^{]*\{[^}]*font-size:\s*var\(--text-md\)/);
    expect(rule(base, /\.map__card/)).toMatch(/font-size:\s*var\(--text-sm\)/);
    expect(rule(base, /\.map__card--chip/)).toMatch(/font-size:\s*var\(--text-xs\)/);
  });
});

describe("nothing decorative implies a quantity the records do not carry", () => {
  it("keys no size, opacity or colour to a confidence", () => {
    // ADR 0006's rejected fourth alternative: the project has no defensible
    // magnitude, importance or cluster value, so none is drawn. `confidence`
    // is a real field and it is *printed*, never turned into a channel.
    expect(base).not.toMatch(/confidence[^;}]*:\s*(opacity|scale|size)/);
    expect(tokens).not.toMatch(/--confidence/);
  });
});
