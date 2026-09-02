/**
 * Quick Read (`T-207`, D-131, ADR 0005 invariant 12).
 *
 * Four claims, and each of them is a way a "detail panel" usually goes wrong:
 *
 * - **The statement is complete.** Preview cards cut; this surface exists so
 *   the whole stored statement can be read, and a cut here would mean the
 *   canonical text is nowhere in the application.
 * - **The order is the stated one.** D-131 fixes it -- statement, evidence,
 *   relation, derivation, provenance, then technical metadata -- so the order
 *   is asserted as an order rather than as a set of present fields.
 * - **Nothing absent is filled in.** No confidence becomes `0.00`, no missing
 *   locator becomes a time range, no absent derivation becomes an empty list.
 * - **The Reader link carries the recorded time**, and carries none when the
 *   record states none (D-069).
 */

import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { EntityRef } from "../api/contract";
import { ApiFailure } from "../api/errors";
import { concept, edge, expressesConcept, unit } from "../test/graphRecords";
import { renderApp } from "../test/render";
import type { ActiveRelation } from "../map/neighbourhood";
import { MapQuickRead } from "./MapQuickRead";

const KU1 = "youtube:pqlWNihgdjI:KU-000001";
const KU2 = "youtube:pqlWNihgdjI:KU-000002";
const C1 = "library:concepts:C-000001";

/** A statement longer than any preview budget, so a cut would be visible. */
const LONG = `${"A statement the transcript actually makes, at length. ".repeat(12)}End.`;

function sourceUnit(overrides: Partial<EntityRef> = {}): EntityRef {
  return unit("KU-000001", {
    label: LONG,
    locator: {
      type: "time_range",
      start_sec: 92.5,
      end_sec: 118,
      segment_id: "SEG-0007",
      artifact_id: "youtube:pqlWNihgdjI:transcript.json",
      excerpt: "the words the speaker actually said",
    },
    ...overrides,
  });
}

const OUTGOING: ActiveRelation = {
  record: edge(KU1, KU2, "supports"),
  direction: "outgoing",
  otherId: KU2,
};

const SYNTHETIC: ActiveRelation = {
  record: expressesConcept(KU1, C1),
  direction: "outgoing",
  otherId: C1,
};

function quickRead(
  props: Partial<Parameters<typeof MapQuickRead>[0]> = {},
) {
  return renderApp(
    <MapQuickRead
      focus={KU1}
      entity={sourceUnit()}
      error={null}
      onRetry={() => undefined}
      relations={[OUTGOING]}
      {...props}
    />,
  );
}

/** The section headings, in the order the DOM has them. */
function headings(): string[] {
  return [...document.querySelectorAll("h3")].map((node) => node.textContent ?? "");
}

describe("Quick Read", () => {
  it("shows the complete stored statement, uncut", () => {
    quickRead();
    const statement = document.querySelector("[data-map-statement='complete']");
    expect(statement?.textContent).toBe(LONG);
    // And says so, so a reader knows this is the whole thing rather than a
    // longer preview.
    expect(
      screen.getByText("The complete statement as the index stores it — not shortened here."),
    ).toBeDefined();
    expect(document.querySelector("[data-truncated]")).toBeNull();
  });

  it("orders the sections the way D-131 states them", () => {
    quickRead();
    expect(headings()).toEqual([
      "Stored statement",
      "Recorded evidence",
      "Active relations",
      "Derivation",
      "Provenance and source",
      "Technical metadata",
    ]);
  });

  it("quotes the recorded excerpt and prints the locator as recorded", () => {
    quickRead();
    expect(document.querySelector("[data-map-excerpt]")?.textContent).toBe(
      "the words the speaker actually said",
    );
    expect(screen.getByText("1:32 – 1:58")).toBeDefined();
    expect(screen.getByText("SEG-0007")).toBeDefined();
  });

  it("names each active relation, its direction and its vocabulary", () => {
    quickRead({ relations: [OUTGOING, SYNTHETIC] });
    const rows = [...document.querySelectorAll("[data-relation]")];
    expect(rows).toHaveLength(2);
    expect(rows[0]?.getAttribute("data-relation-direction")).toBe("outgoing");
    expect(screen.getByText("supports")).toBeDefined();
    // A library-synthetic edge says so rather than looking canonical: 62 of
    // the real graph's 118 edges are synthetic (D-006).
    expect(screen.getByText("expresses_concept")).toBeDefined();
    expect(document.querySelector("[data-map-quickread-relations]")?.getAttribute(
      "data-map-quickread-relations",
    )).toBe("2");
  });

  it("states an entity with no relation at this depth instead of leaving a gap", () => {
    quickRead({ relations: [] });
    expect(
      screen.getByText(
        "The bounded neighbourhood returned no relation for this entity at this depth.",
      ),
    ).toBeDefined();
  });

  it("renders a missing confidence as missing, never as zero", () => {
    // D-025: `library.py` used to write `0` -- the *least* confident value --
    // for a unit that stated nothing. The UI must not put the number back.
    quickRead({ entity: concept("C-000001") });
    expect(screen.getAllByText("not stated").length).toBeGreaterThan(0);
    expect(document.body.textContent).not.toContain("0.00");
  });

  it("states an absent locator rather than inventing a time", () => {
    quickRead({ entity: concept("C-000001") });
    expect(screen.getByText("No locator is recorded for this unit.")).toBeDefined();
    expect(document.body.textContent).not.toContain("00:00");
  });

  it("states an absent derivation rather than an empty list", () => {
    quickRead();
    expect(screen.getByText("This entity records no derivation.")).toBeDefined();
  });

  it("shows a derived unit's own work, verbatim", () => {
    quickRead({
      entity: unit("KU-D-0001", {
        provenance_class: "derived",
        derived_from: [KU1, KU2],
        derivation_note: "Both statements describe the same loop from different sides.",
      }),
    });
    expect(
      screen.getByText(/Both statements describe the same loop from different sides\./),
    ).toBeDefined();
    // The id appears in the derivation list, which is the section under test.
    const derivation = [...document.querySelectorAll("section")].find((node) =>
      node.querySelector("h3")?.textContent === "Derivation",
    );
    expect(derivation?.textContent).toContain(KU2);
  });

  it("links into the Reader at the time the locator records", () => {
    quickRead();
    const link = document.querySelector("[data-map-reader-link]");
    // The internal grammar is `t=<seconds>`, and 92.5 is carried as recorded
    // rather than rounded to a whole second.
    expect(link?.getAttribute("href")).toBe(
      // No `#` here: the test router is a `MemoryRouter`, while the
      // application's `HashRouter` renders the same path behind one (D-060).
      `/sources/${encodeURIComponent("youtube:pqlWNihgdjI")}?tab=units&t=92.5`,
    );
    expect(
      screen.getByText("The Reader opens at 1:32, the time the locator records."),
    ).toBeDefined();
  });

  it("carries no timestamp for a record that states no time", () => {
    quickRead({ entity: unit("KU-000001", { locator: null, provenance_class: "user" }) });
    const link = document.querySelector("[data-map-reader-link]");
    expect(link?.getAttribute("href")).toBe(
      `/sources/${encodeURIComponent("youtube:pqlWNihgdjI")}?tab=units`,
    );
    expect(
      screen.getByText(
        "This entity records no time, so the Reader opens at the start of the source.",
      ),
    ).toBeDefined();
  });

  it("offers no Reader link for an entity that belongs to no source", () => {
    // A canonical concept belongs to no source (D-016) and there is nothing to
    // open. An absent link is the honest signal; a dead one would not be.
    quickRead({ entity: concept("C-000001") });
    expect(document.querySelector("[data-map-reader-link]")).toBeNull();
  });

  it("states a refusal instead of an empty panel", () => {
    quickRead({
      entity: null,
      error: new ApiFailure("not_found", "No entity in the index has that id."),
    });
    expect(document.querySelector("[data-error-code='not_found']")).not.toBeNull();
    expect(document.querySelector("[data-map-statement]")).toBeNull();
  });

  it("says nothing is focused rather than rendering an empty record", () => {
    quickRead({ focus: null, entity: null });
    expect(screen.getByText("Nothing is focused, so there is no record to read.")).toBeDefined();
  });
});
