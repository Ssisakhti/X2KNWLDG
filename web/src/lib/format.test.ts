/**
 * Formatting, and the absences it must preserve.
 *
 * Every one of these functions is a place where a `?? 0` would have been
 * convenient and dishonest. The tests exist to keep one from appearing.
 */

import { describe, expect, it } from "vitest";

import {
  formatCount,
  formatBytes,
  formatConfidence,
  formatSeconds,
  formatTimestamp,
  sourceIdOf,
  splitGlobalId,
  youtubeTimestampUrl,
} from "./format";

describe("formatSeconds", () => {
  it("formats below and above an hour", () => {
    expect(formatSeconds(0)).toBe("0:00");
    expect(formatSeconds(90)).toBe("1:30");
    expect(formatSeconds(3661)).toBe("1:01:01");
  });

  it("returns null for a value the data does not state, never 0:00", () => {
    expect(formatSeconds(null)).toBeNull();
    expect(formatSeconds(undefined)).toBeNull();
    expect(formatSeconds(Number.NaN)).toBeNull();
  });
});

describe("formatConfidence", () => {
  it("prints the recorded number", () => {
    expect(formatConfidence(0.9)).toBe("0.90");
    expect(formatConfidence(0)).toBe("0.00");
  });

  it("distinguishes an unstated confidence from a zero one (D-043)", () => {
    expect(formatConfidence(null)).toBeNull();
    expect(formatConfidence(0)).toBe("0.00");
  });
});

describe("formatBytes and formatTimestamp", () => {
  it("scale bytes and refuse a missing count", () => {
    // The unit is returned separately rather than baked into the string: it is
    // a word, and this module has no translator. It used to read "512 B" under
    // a Persian label.
    expect(formatBytes(512)).toEqual({ amount: "512", unit: "B" });
    expect(formatBytes(2048)).toEqual({ amount: "2.0", unit: "KB" });
    expect(formatBytes(5 * 1024 * 1024)).toEqual({ amount: "5.0", unit: "MB" });
    expect(formatBytes(null)).toBeNull();
    expect(formatBytes(-1)).toBeNull();
  });

  it("shows an unparseable timestamp as written rather than dropping it", () => {
    expect(formatTimestamp("not a date", "en")).toBe("not a date");
    expect(formatTimestamp(null, "en")).toBeNull();
  });
});

describe("youtubeTimestampUrl", () => {
  it("produces the &t=<int>s form io.timestamp_url contract-locks", () => {
    expect(
      youtubeTimestampUrl("https://www.youtube.com/watch?v=abc123", 30.7),
    ).toBe("https://www.youtube.com/watch?v=abc123&t=30s");
  });

  it("refuses to build a link when either input is missing", () => {
    expect(youtubeTimestampUrl("https://www.youtube.com/watch?v=abc", null)).toBeNull();
    expect(youtubeTimestampUrl(null, 10)).toBeNull();
  });

  it("does not rewrite a non-YouTube URL into one", () => {
    expect(youtubeTimestampUrl("https://example.org/watch?v=abc", 10)).toBeNull();
    expect(youtubeTimestampUrl("javascript:alert(1)", 10)).toBeNull();
    expect(youtubeTimestampUrl("https://notyoutube.com/watch?v=a", 10)).toBeNull();
  });
});

describe("global ids", () => {
  it("splits the three parts (D-011)", () => {
    expect(splitGlobalId("youtube:pqlWNihgdjI:KU-000001")).toEqual({
      sourceType: "youtube",
      externalId: "pqlWNihgdjI",
      localId: "KU-000001",
    });
    expect(sourceIdOf("library:concepts:30ba07eea6c0")).toBe("library:concepts");
  });

  it("returns null rather than guessing at a malformed id", () => {
    expect(splitGlobalId("youtube:only-two")).toBeNull();
    expect(sourceIdOf("nonsense")).toBeNull();
  });
});

describe("counts, in the reader's own digits", () => {
  it("writes a Persian reader's counts in the digits their dates already use", () => {
    // The defect this closes: `formatTimestamp("…","fa")` has always produced
    // Persian-Indic digits, while every count beside it was a bare JS number.
    // One panel, two numeral systems.
    expect(formatCount(1234, "fa")).toBe("۱٬۲۳۴");
    expect(formatCount(4, "fa")).toBe("۴");
    expect(formatCount(1234, "en")).toBe("1,234");
  });

  it("renders a zero, because a zero is a measurement", () => {
    expect(formatCount(0, "fa")).toBe("۰");
    expect(formatCount(0, "en")).toBe("0");
  });

  it("returns null for a count the data does not state", () => {
    expect(formatCount(null, "en")).toBeNull();
    expect(formatCount(undefined, "en")).toBeNull();
    expect(formatCount(Number.NaN, "en")).toBeNull();
    expect(formatCount(Number.POSITIVE_INFINITY, "en")).toBeNull();
  });

  it("falls back to the number itself rather than to nothing on a bad locale", () => {
    expect(formatCount(7, "not a language tag")).toBe("7");
  });
});
