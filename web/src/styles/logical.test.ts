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

/**
 * The other half of D-012: an inline *style* is a stylesheet too (D-203).
 *
 * The guard above reads the two stylesheets and nothing else, and the
 * codebase relies on that blind spot: `MapOrbit` writes physical `left`/`top`
 * deliberately and correctly, because `placeOrbit` takes `rtl` and mirrors the
 * coordinates itself — a logical inset would mirror an already-mirrored
 * number, which is exactly the defect D-191 carries forward from the mockups.
 *
 * So the rule for components is not "never physical" but "physical only where
 * the file says why, in an allowlist that is short and reviewed". The next
 * component to write `marginLeft` was not caught by anything at all; it is
 * caught here.
 */
describe("components stay on the logical axis, or say why not", () => {
  /*
   * Every module allowed to write a physical inline-axis style, and the
   * reason. A path in here is a decision; a path that needs adding is a
   * decision to make rather than a line to append.
   */
  const ALLOWED = new Map<string, string>([
    [
      "src/components/MapOrbit.tsx",
      "placeOrbit already mirrored these coordinates (D-191); a logical inset " +
        "would mirror them twice",
    ],
  ]);

  /*
   * A *style* write, not any object key called `left`.
   *
   * `MapView.measureChrome` builds `StageRect`s whose fields are named `left`
   * and `right` because they are measured geometry, and a guard that flagged
   * those would be a guard nobody could keep green. The camelCase properties
   * are unambiguous on their own; `left`/`right` are only counted when the
   * value is a CSS length, which is what a style write looks like and what a
   * rectangle never does.
   */
  const PHYSICAL_JSX = [
    /\bmarginLeft\b/,
    /\bmarginRight\b/,
    /\bpaddingLeft\b/,
    /\bpaddingRight\b/,
    /\bborderLeft(?:Width|Color|Style)?\b/,
    /\bborderRight(?:Width|Color|Style)?\b/,
    /\b(?:left|right|insetLeft|insetRight):\s*(?:`[^`]*(?:px|%|r?em)`|"[^"]*(?:px|%|r?em)")/,
    /\bfloat:\s*"(?:left|right)"/,
    /textAlign:\s*"(?:left|right)"/,
  ];

  const modules = import.meta.glob("../{components,views,map}/**/*.tsx", {
    query: "?raw",
    import: "default",
    eager: true,
  }) as Record<string, string>;

  it("looks at the components at all", () => {
    // A glob that matched nothing would make every assertion below vacuous —
    // which is the shape of the defect this whole block is about.
    const names = Object.keys(modules).filter((name) => !name.includes(".test."));
    expect(names.length).toBeGreaterThan(10);
  });

  it("finds no physical inline-axis style outside the allowlist", () => {
    const offenders: string[] = [];
    for (const [path, source] of Object.entries(modules)) {
      if (path.includes(".test.")) continue;
      const relative = path.replace(/^\.\.\//, "src/");
      if (ALLOWED.has(relative)) continue;
      for (const line of source.split("\n")) {
        const code = line.trimStart();
        // Prose about a property is not the property.
        if (code.startsWith("*") || code.startsWith("//")) continue;
        for (const pattern of PHYSICAL_JSX) {
          if (pattern.test(line)) offenders.push(`${relative}: ${code.slice(0, 90)}`);
        }
      }
    }
    expect(offenders).toEqual([]);
  });

  it("the allowlist is not stale", () => {
    // A file that stopped needing its exception should lose it, or the
    // allowlist becomes the thing nobody reads.
    for (const [relative, reason] of ALLOWED) {
      const path = relative.replace(/^src\//, "../");
      const source = modules[path];
      expect(source, `${relative} is allowlisted and does not exist`).toBeTruthy();
      const writes = PHYSICAL_JSX.some((pattern) => pattern.test(source ?? ""));
      expect(writes, `${relative} no longer writes one: ${reason}`).toBe(true);
    }
  });
});
