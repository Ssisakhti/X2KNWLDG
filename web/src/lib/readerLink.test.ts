/**
 * The Reader's deep-link grammar (D-069).
 *
 * Built and parsed by one module, so these tests are the round trip: what
 * `readerPath` writes, `parseTab`/`parseSeconds` must read back.
 */

import { describe, expect, it } from "vitest";

import {
  DEFAULT_TAB,
  captionIndexAt,
  parseSeconds,
  parseTab,
  readerPath,
} from "./readerLink";

describe("readerPath", () => {
  it("omits the default tab rather than spelling it", () => {
    // A URL that states the default states nothing; keeping it would make two
    // different strings mean the same page, and the copied link the noisier one.
    expect(readerPath("youtube:x", { tab: DEFAULT_TAB })).toBe("/sources/youtube%3Ax");
    expect(readerPath("youtube:x")).toBe("/sources/youtube%3Ax");
  });

  it("carries the tab and the offset", () => {
    expect(readerPath("youtube:x", { tab: "transcript", seconds: 30 })).toBe(
      "/sources/youtube%3Ax?tab=transcript&t=30",
    );
    expect(readerPath("youtube:x", { tab: "units" })).toBe("/sources/youtube%3Ax?tab=units");
  });

  it("encodes the id, so a colon is not a path separator", () => {
    expect(readerPath("youtube:a/b")).toBe("/sources/youtube%3Aa%2Fb");
  });

  it("omits an absent or unusable offset instead of writing a zero", () => {
    for (const seconds of [null, undefined, -1, Number.NaN, Number.POSITIVE_INFINITY]) {
      expect(readerPath("youtube:x", { tab: "transcript", seconds })).toBe(
        "/sources/youtube%3Ax?tab=transcript",
      );
    }
  });

  it("round-trips through the parsers", () => {
    const path = readerPath("youtube:x", { tab: "transcript", seconds: 30 });
    const query = new URLSearchParams(path.slice(path.indexOf("?")));
    expect(parseTab(query.get("tab"))).toBe("transcript");
    expect(parseSeconds(query.get("t"))).toBe(30);
  });
});

describe("parseTab", () => {
  it("accepts every tab the Reader has", () => {
    for (const tab of ["overview", "transcript", "report", "units", "relations", "artifacts"]) {
      expect(parseTab(tab)).toBe(tab);
    }
  });

  it("returns null for a tab this Reader does not have", () => {
    // Null rather than a throw: a stale or hand-edited link should open the
    // Reader on its default, not refuse to render a source that is fine.
    for (const value of [null, "", "map", "canvas", "OVERVIEW"]) {
      expect(parseTab(value)).toBeNull();
    }
  });
});

describe("parseSeconds", () => {
  it("reads a non-negative finite number", () => {
    expect(parseSeconds("0")).toBe(0);
    expect(parseSeconds("30")).toBe(30);
    expect(parseSeconds("30.5")).toBe(30.5);
  });

  it("ignores what it cannot read rather than coercing it to zero", () => {
    // `Number("")` is 0 and `Number(" ")` is 0, which is why this is a test and
    // not an assumption: reading `t=` as the start of the medium would put the
    // reader somewhere the URL never asked for. That is an invented position.
    for (const value of [null, "", "   ", "x", "abc", "NaN", "-1", "-0.5", "Infinity"]) {
      expect(parseSeconds(value)).toBeNull();
    }
  });
});

describe("captionIndexAt", () => {
  const captions = [
    { startSec: 0, endSec: 30 },
    { startSec: 30, endSec: 60 },
    { startSec: 60, endSec: 90 },
  ];

  it("finds the caption containing the offset", () => {
    expect(captionIndexAt(captions, 0)).toBe(0);
    expect(captionIndexAt(captions, 29.9)).toBe(0);
    expect(captionIndexAt(captions, 30)).toBe(1);
    expect(captionIndexAt(captions, 75)).toBe(2);
  });

  it("has no answer without an offset", () => {
    expect(captionIndexAt(captions, null)).toBeNull();
    expect(captionIndexAt([], 30)).toBeNull();
  });

  it("falls back to the caption that was playing across a gap", () => {
    // A transcript may have gaps: a non-speech cue keeps its timing and loses
    // its text (WORKFLOW.md), so an offset can land between captions. Landing
    // on the one that was playing beats landing on nothing.
    const gapped = [
      { startSec: 0, endSec: 10 },
      { startSec: 50, endSec: 60 },
    ];
    expect(captionIndexAt(gapped, 30)).toBe(0);
  });

  it("returns null before the first caption starts", () => {
    expect(captionIndexAt([{ startSec: 10, endSec: 20 }], 5)).toBeNull();
  });

  it("never picks a caption that states no start time", () => {
    // It has no position, so it cannot be at one. Choosing it would be the
    // invented timestamp the transcript panel exists to refuse.
    const timeless = [
      { startSec: null, endSec: null },
      { startSec: 30, endSec: 60 },
    ];
    expect(captionIndexAt(timeless, 5)).toBeNull();
    expect(captionIndexAt(timeless, 45)).toBe(1);
  });
});
