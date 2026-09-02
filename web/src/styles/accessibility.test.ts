/**
 * `T-208` as stylesheet rules: motion, targets and direction.
 *
 * The same argument as `logical.test.ts`. These are properties of the *whole*
 * stylesheet rather than of any one component, they rot one declaration at a
 * time, and reviewing for them by eye does not scale -- so they are checked
 * mechanically and the failure names what is missing.
 *
 * What is asserted here is the *rule*, never the number's beauty: that a
 * reduced-motion block exists and neutralises both animation and transition,
 * that the interactive elements have a stated minimum target on a coarse
 * pointer, that a narrow screen keeps the stage sized rather than collapsing
 * it into a renderer refusal, and that neutral text -- identifiers, codes,
 * counts -- is isolated so a Persian paragraph cannot reorder it.
 */

import { describe, expect, it } from "vitest";

import base from "./base.css?raw";

/** The declarations inside the first at-rule whose prelude matches. */
function atRule(source: string, prelude: RegExp): string {
  const start = source.search(prelude);
  if (start < 0) return "";
  let depth = 0;
  for (let index = start; index < source.length; index += 1) {
    if (source[index] === "{") depth += 1;
    if (source[index] === "}") {
      depth -= 1;
      if (depth === 0) return source.slice(start, index + 1);
    }
  }
  return "";
}

/** The body of the first rule whose selector matches. */
function rule(source: string, selector: RegExp): string {
  const found = new RegExp(`${selector.source}\\s*\\{[^}]*\\}`).exec(source);
  return found === null ? "" : found[0];
}

describe("the stylesheet answers a reduced-motion preference", () => {
  const block = atRule(base, /@media \(prefers-reduced-motion: reduce\)/);

  it("has the block at all", () => {
    expect(block).not.toBe("");
  });

  it("neutralises animation and transition rather than listing what to neutralise", () => {
    // A blanket rule, because a list is what rots: the next transition
    // somebody adds is covered without anyone remembering this block exists.
    expect(block).toMatch(/\*\s*,/);
    expect(block).toMatch(/animation-duration:\s*0\.01ms\s*!important/);
    expect(block).toMatch(/transition-duration:\s*0\.01ms\s*!important/);
    expect(block).toMatch(/animation-iteration-count:\s*1\s*!important/);
  });

  it("does not pretend to cover the camera, which is animated in script", () => {
    // `map/motion.ts` reads the same preference for the canvas. This is the
    // reminder that the stylesheet cannot reach it.
    expect(base).toMatch(/motion\.ts/);
  });
});

describe("the stylesheet states its touch targets", () => {
  const coarse = atRule(base, /@media \(pointer: coarse\)/);

  it("gives every control a minimum on a coarse pointer", () => {
    expect(coarse).not.toBe("");
    for (const selector of [".button", "summary", "select", "input"]) {
      expect(coarse).toContain(selector);
    }
    expect(coarse).toMatch(/min-block-size:\s*2\.75rem/);
  });

  it("keeps the one control that is only a line of text big enough on any pointer", () => {
    // A panel's `<summary>` is its only control, and a line of text is the
    // hardest thing on the page to press.
    expect(rule(base, /\.disclosure__summary/)).toMatch(/min-block-size:\s*2\.75rem/);
  });
});

describe("the stylesheet discloses rather than collapses on a narrow screen", () => {
  const narrow = atRule(base, /@media \(max-width: 48rem\)/);

  it("keeps the stage sized, because a sizeless stage is a stated refusal", () => {
    expect(narrow).toContain(".map__stage");
    expect(narrow).toMatch(/min-block-size:\s*240px/);
    expect(narrow).toMatch(/block-size:\s*min\(/);
  });
});

describe("neutral text is isolated from the paragraph that surrounds it", () => {
  it("lays identifiers out left to right in either direction", () => {
    // An identifier, a path or a URL is not Persian and not English, and a
    // Persian paragraph must not reorder one (D-012, `T-208`).
    for (const selector of [/\.mono/, /\.notice__code/]) {
      const body = rule(base, selector);
      expect(body).toMatch(/direction:\s*ltr/);
      expect(body).toMatch(/unicode-bidi:\s*isolate/);
    }
  });

  it("isolates a panel's own count from its heading", () => {
    expect(rule(base, /\.disclosure__count/)).toMatch(/unicode-bidi:\s*isolate/);
  });

  it("still shows keyboard focus", () => {
    expect(rule(base, /:focus-visible/)).toMatch(/outline:/);
  });
});
