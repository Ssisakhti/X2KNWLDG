/**
 * Result cards (`T-206`, D-131 and D-119).
 *
 * Two rules are tested here harder than anything else, because both fail
 * quietly: a card must not write text the API did not return, and a hit with
 * no `global_id` must not become selectable. The first failure looks like a
 * helpful summary. The second looks like a working button that focuses
 * nothing.
 */

import { fireEvent, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { renderApp } from "../test/render";
import { unit } from "../test/graphRecords";
import { previewOfEntity, previewOfHit, type MapPreview } from "../map/useMapSearch";
import { MapResultCard, PREVIEW_LIMIT, previewText } from "./MapResultCard";

const STATEMENT = "Coverage is audited window by window, and the audit is capped at three passes.";

const LOADED: MapPreview = previewOfEntity(
  unit("KU-000001", { label: STATEMENT, confidence: 0.91 }),
);

const CAPTION: MapPreview = previewOfHit(
  {
    type: "transcript_caption",
    video_id: "pqlWNihgdjI",
    title: "A fixture",
    caption_id: "cap_000002",
    content: "The audit runs window by window.",
    start_sec: 30,
    end_sec: 60,
    source_url: "https://www.youtube.com/watch?v=pqlWNihgdjI&t=30s",
    source_id: "youtube:pqlWNihgdjI",
  },
  0,
  false,
);

const ORPHAN: MapPreview = previewOfHit(
  {
    type: "knowledge_unit",
    video_id: null,
    title: null,
    id: "KU-000007",
    kind: "claim",
    source_class: "source",
    content: "A unit from a run whose metadata states no video id.",
    confidence: null,
    global_id: null,
    source_id: null,
  },
  0,
  false,
);

describe("previewText", () => {
  it("returns short text untouched, and says nothing was cut", () => {
    expect(previewText("short")).toEqual({ shown: "short", truncated: false });
    expect(previewText(null)).toEqual({ shown: null, truncated: false });
  });

  it("returns a prefix of the stored text, never a rewrite", () => {
    const long = `${"word ".repeat(200)}end`;
    const { shown, truncated } = previewText(long);
    expect(truncated).toBe(true);
    expect(shown).not.toBeNull();
    expect(long.startsWith(shown as string)).toBe(true);
    expect((shown as string).length).toBeLessThanOrEqual(PREVIEW_LIMIT);
  });

  it("cuts at the limit when there is no word boundary to cut at", () => {
    const unbroken = "x".repeat(PREVIEW_LIMIT * 2);
    const { shown } = previewText(unbroken);
    expect(shown).toHaveLength(PREVIEW_LIMIT);
  });
});

describe("MapResultCard", () => {
  it("shows the stored statement verbatim when it fits", () => {
    renderApp(<MapResultCard preview={LOADED} onFocus={() => undefined} />);
    expect(screen.getByText(STATEMENT)).not.toBeNull();
    expect(document.querySelector("[data-truncated]")).toBeNull();
  });

  it("states that a long statement was shortened, rather than shortening it silently", () => {
    const long = { ...LOADED, text: `${"word ".repeat(200)}end` };
    renderApp(<MapResultCard preview={long} onFocus={() => undefined} />);
    const note = document.querySelector("[data-truncated]");
    expect(note).not.toBeNull();
    expect(note?.textContent).toContain("shortened");
    // The visible text is a prefix of the record's own, and the tail is gone
    // rather than paraphrased.
    expect(screen.queryByText(/end$/)).toBeNull();
  });

  it("renders a missing confidence as an absence, never as zero", () => {
    const noConfidence = { ...LOADED, confidence: null };
    renderApp(<MapResultCard preview={noConfidence} onFocus={() => undefined} />);
    expect(document.body.textContent).toContain("not stated");
    expect(document.body.textContent).not.toContain("0.00");
  });

  it("focuses by the record's own global id, from a real button", () => {
    const focused = vi.fn();
    renderApp(<MapResultCard preview={LOADED} onFocus={focused} />);
    const button = screen.getByText("Focus");
    expect(button.tagName).toBe("BUTTON");
    fireEvent.click(button);
    expect(focused).toHaveBeenCalledWith("youtube:pqlWNihgdjI:KU-000001");
  });

  it("says when it is the focused card", () => {
    renderApp(<MapResultCard preview={LOADED} focused onFocus={() => undefined} />);
    expect(screen.getByText("Focused").getAttribute("aria-pressed")).toBe("true");
  });

  it("gives a caption hit no focus control, and explains why", () => {
    renderApp(<MapResultCard preview={CAPTION} onFocus={() => undefined} />);
    expect(screen.queryByText("Focus")).toBeNull();
    expect(document.body.textContent).toContain("not an addressable entity");
    // It is still readable and still reachable: source and timestamp, exactly
    // as the Library's search rail does it.
    const links = [...document.querySelectorAll("a")].map((a) => a.getAttribute("href"));
    expect(links).toContain("/sources/youtube%3ApqlWNihgdjI?tab=transcript&t=30");
    expect(links).toContain("https://www.youtube.com/watch?v=pqlWNihgdjI&t=30s");
    expect(document.querySelector("[data-addressable]")?.getAttribute("data-addressable")).toBe(
      "false",
    );
  });

  it("gives a unit with no global id no focus control either", () => {
    renderApp(<MapResultCard preview={ORPHAN} onFocus={() => undefined} />);
    expect(screen.queryByText("Focus")).toBeNull();
    expect(document.body.textContent).toContain("no global id");
    expect(
      document.querySelector("[data-unaddressable-reason]")?.getAttribute(
        "data-unaddressable-reason",
      ),
    ).toBe("no_global_id");
  });

  it("says whether an indexed hit is already drawn on the Map", () => {
    const known = previewOfHit(
      {
        type: "knowledge_unit",
        video_id: "pqlWNihgdjI",
        title: "A fixture",
        id: "KU-000001",
        kind: "principle",
        source_class: "source",
        content: STATEMENT,
        confidence: 0.9,
        global_id: "youtube:pqlWNihgdjI:KU-000001",
        source_id: "youtube:pqlWNihgdjI",
      },
      0,
      false,
    );
    renderApp(<MapResultCard preview={known} onFocus={() => undefined} />);
    expect(document.querySelector("[data-map-loaded]")?.getAttribute("data-map-loaded")).toBe(
      "false",
    );
    expect(document.body.textContent).toContain("Not loaded on the Map yet");
  });

  it("shows a provenance value outside the contract as written", () => {
    const odd = { ...LOADED, provenance: null, provenanceRaw: "workspace" };
    renderApp(<MapResultCard preview={odd} onFocus={() => undefined} />);
    expect(screen.getByText("workspace")).not.toBeNull();
  });

  it("previews on pointer hover and on keyboard focus through the same handlers", () => {
    const events: string[] = [];
    renderApp(
      <MapResultCard
        preview={LOADED}
        onFocus={() => undefined}
        peek={{
          onMouseEnter: () => events.push("enter"),
          onMouseLeave: () => events.push("leave"),
          onFocus: () => events.push("focus"),
          onBlur: () => events.push("blur"),
        }}
      />,
    );
    const card = document.querySelector("[data-map-result]") as HTMLElement;
    fireEvent.mouseEnter(card);
    fireEvent.focus(card);
    expect(events).toEqual(["enter", "focus"]);
  });
});
