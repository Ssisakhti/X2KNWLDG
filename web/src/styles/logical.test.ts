/**
 * D-012 as a test: no physical inline-axis property survives in the stylesheets.
 *
 * `dir` switching is architectural, and the way it rots is one
 * `margin-left` at a time. Reviewing for that by eye does not scale, so the
 * rule is checked mechanically: if a physical property appears in either
 * stylesheet, this fails and names it.
 *
 * Block-axis physical properties (`margin-top`, `border-bottom`) are *not*
 * banned -- they mean the same thing in both directions. Only the inline axis
 * flips.
 */

import { describe, expect, it } from "vitest";

import base from "./base.css?raw";
import tokens from "./tokens.css?raw";

const PHYSICAL = [
  /\bmargin-left\b/,
  /\bmargin-right\b/,
  /\bpadding-left\b/,
  /\bpadding-right\b/,
  /\bborder-left\b/,
  /\bborder-right\b/,
  /\bborder-left-[a-z]+\b/,
  /\bborder-right-[a-z]+\b/,
  /\bleft\s*:/,
  /\bright\s*:/,
  /\bfloat\s*:/,
  /text-align\s*:\s*(left|right)/,
  // A bare `width` declaration; `border-inline-start-width`, `--border-width`
  // and a media query's `max-width` are all preceded by a `-` or a word
  // character and are not physical inline-axis properties.
  /(?<![-\w])width\s*:/,
];

const SHEETS: readonly [string, string][] = [
  ["tokens.css", tokens],
  ["base.css", base],
];

describe("stylesheets stay on the logical axis", () => {
  for (const [name, source] of SHEETS) {
    for (const pattern of PHYSICAL) {
      it(`${name} has no ${pattern.source}`, () => {
        const offenders = source
          .split("\n")
          .filter((line) => pattern.test(line) && !line.trimStart().startsWith("*"));
        expect(offenders).toEqual([]);
      });
    }
  }

  it("base.css does use the logical replacements", () => {
    expect(base).toMatch(/margin-inline/);
    expect(base).toMatch(/padding-inline/);
    expect(base).toMatch(/border-inline-start/);
    expect(base).toMatch(/inline-size/);
  });
});
