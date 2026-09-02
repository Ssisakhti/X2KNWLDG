/**
 * The Peek card (`T-206`, D-131/D-133).
 *
 * A Peek exists to answer "is this worth opening?" from the record alone. So
 * the tests below check that it shows the record -- and that it says what it
 * is: a preview that selected nothing.
 */

import { fireEvent, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { concept, unit } from "../test/graphRecords";
import { renderApp } from "../test/render";
import { MapPeekCard, PEEK_LIMIT } from "./MapPeekCard";

const STATEMENT = "Coverage is audited window by window.";
const KU = unit("KU-000001", {
  label: STATEMENT,
  confidence: 0.91,
  locator: { type: "time_range", start_sec: 30, end_sec: 60, excerpt: "verbatim" },
});

describe("MapPeekCard", () => {
  it("shows the loaded record: statement, kind, provenance, confidence and time", () => {
    renderApp(<MapPeekCard peek={{ globalId: KU.global_id, record: KU, origin: "pointer" }} />);
    expect(screen.getByText(STATEMENT)).not.toBeNull();
    expect(screen.getByText("claim")).not.toBeNull();
    expect(document.body.textContent).toContain("0.91");
    expect(document.body.textContent).toContain("0:30");
    expect(document.querySelector("[data-map-peek]")?.getAttribute("data-map-peek")).toBe(
      KU.global_id,
    );
  });

  it("says it selected nothing", () => {
    // A card that appears under the pointer and a card that appears after a
    // click otherwise look like the same event.
    renderApp(<MapPeekCard peek={{ globalId: KU.global_id, record: KU, origin: "keyboard" }} />);
    expect(document.body.textContent).toContain("Nothing is selected");
    expect(document.querySelector("[data-peek-origin]")?.getAttribute("data-peek-origin")).toBe(
      "keyboard",
    );
  });

  it("takes no focus of its own", () => {
    // `status`, not `dialog`: a Peek that trapped focus would fight the
    // keyboard walk that opened it.
    renderApp(<MapPeekCard peek={{ globalId: KU.global_id, record: KU, origin: "keyboard" }} />);
    const card = document.querySelector("[data-map-peek]");
    expect(card?.getAttribute("role")).toBe("status");
    expect(card?.hasAttribute("tabindex")).toBe(false);
  });

  it("renders an absent confidence as an absence", () => {
    const C = concept("C-000001");
    renderApp(<MapPeekCard peek={{ globalId: C.global_id, record: C, origin: "pointer" }} />);
    expect(document.body.textContent).toContain("not stated");
    expect(document.body.textContent).not.toContain("0.00");
  });

  it("shortens a long statement visibly, and keeps the glance shorter than a list entry", () => {
    const long = unit("KU-000002", { label: `${"word ".repeat(200)}end` });
    renderApp(<MapPeekCard peek={{ globalId: long.global_id, record: long, origin: "pointer" }} />);
    const shown = document.querySelector("p[dir='auto']")?.textContent ?? "";
    expect(shown.length).toBeLessThanOrEqual(PEEK_LIMIT);
    expect(document.querySelector("[data-truncated]")).not.toBeNull();
  });

  it("can be dismissed, for the keyboard path that has no leave", () => {
    const closed = vi.fn();
    renderApp(
      <MapPeekCard
        peek={{ globalId: KU.global_id, record: KU, origin: "keyboard" }}
        onClose={closed}
      />,
    );
    fireEvent.click(screen.getByText("Close the peek"));
    expect(closed).toHaveBeenCalledTimes(1);
  });
});
