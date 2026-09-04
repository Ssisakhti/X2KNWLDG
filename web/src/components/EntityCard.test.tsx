/**
 * The Reader's knowledge-unit card, over the locator types adapters produce.
 *
 * `T-228` made that plural (D-233): a Twitter claim is a `text_span` into the
 * post it was taken from, and before this the card fell through to
 * `JSON.stringify(locator)` under a comment saying no adapter produced one.
 *
 * Three claims, each a way this surface could quietly misreport a coordinate:
 *
 * - a time range still renders as a time range, unchanged;
 * - a post renders its **own** coordinate and never invents seconds;
 * - the four reserved types still print their own fields rather than being
 *   squeezed into either shape.
 */

import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { EntityRef } from "../api/contract";
import { unit } from "../test/graphRecords";
import { renderApp } from "../test/render";
import { EntityCard } from "./EntityCard";

const POST_ARTIFACT = "twitter:2027781710667010262:post-2027781710667010262";
/** The committed `persian-rtl` fixture's text: ZWNJ-bearing, right-to-left. */
const PERSIAN_EXCERPT = "برنامه‌های بی‌بی‌سی فارسی را از رادیو بشنوید:";

function card(locator: EntityRef["locator"]) {
  return renderApp(<EntityCard entity={unit("KU-000001", { locator })} />);
}

describe("EntityCard locators", () => {
  it("renders a time range as a time range", () => {
    card({
      type: "time_range",
      start_sec: 92.5,
      end_sec: 118,
      segment_id: "SEG-0007",
      artifact_id: "youtube:pqlWNihgdjI:segments",
    });
    expect(screen.getByText("1:32 – 1:58")).toBeDefined();
    expect(screen.getByText("SEG-0007")).toBeDefined();
  });

  it("renders a post span in its own coordinate, and states the post", () => {
    card({
      type: "text_span",
      artifact_id: POST_ARTIFACT,
      start_char: 0,
      end_char: 45,
      excerpt: PERSIAN_EXCERPT,
    });
    expect(screen.getByText("characters 0–45")).toBeDefined();
    expect(screen.getByText(POST_ARTIFACT)).toBeDefined();
    // No seconds anywhere: a post has no timeline, and a `0:00` here would be
    // a coordinate the record does not carry.
    expect(document.body.textContent).not.toMatch(/\d+:\d\d/);
  });

  it("labels the post artifact rather than showing it as a bare artifact_id", () => {
    card({
      type: "text_span",
      artifact_id: POST_ARTIFACT,
      start_char: 0,
      end_char: 45,
    });
    expect(screen.getByText("Post")).toBeDefined();
  });

  it("prints a still-reserved locator type as its own fields", () => {
    card({ type: "page", page: 3 });
    expect(document.body.textContent).toContain('"page"');
    expect(screen.queryByText("characters 0–45")).toBeNull();
  });

  it("says so when a unit records no locator at all", () => {
    card(null);
    expect(document.body.textContent).not.toContain("characters");
  });
});
