/**
 * `T-212`: the Map is a workspace, not a document.
 *
 * `T-211` measured what this replaces on the real build at 2852x1688: a
 * 1248 px content column with 1604 px of unused width beside it, a stage
 * beginning 790 px down the document, and a *focused* Map 5795 px tall --
 * 3.4 screens, so the Search -> Focus -> Quick Read loop the Map exists for
 * could not be completed without roughly 4100 px of scrolling. Above the
 * stage sat the heading, the subtitle, the filters, the counts, a control row
 * and the search rail; below it five stacked `<details>`.
 *
 * The composition is the subject here, so the claims are structural: which
 * surface holds which panel, what precedes the stage, and what a focus does
 * to the field. Whether the result *looks* like the approved compositions is
 * `T-215`'s question and cannot be answered in jsdom, which has no layout --
 * every rectangle here is zero. What jsdom can answer is whether the DOM the
 * browser will lay out is the one SPEC §7 specifies, and that is what a
 * screen reader and a keyboard get either way.
 *
 * Rendered through `App` rather than `MapView` wherever the claim involves
 * the frame: `Shell` is what decides that this route is a workspace, and a
 * bare `MapView` has no frame to assert about.
 */

import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App } from "../App";
import { mapStyle } from "../map/mapStyle";
import { fakeRenderers } from "../test/mapRenderer";
import { KU1, library } from "../test/mapServer";
import { renderApp } from "../test/render";

import { MapView } from "./MapView";

/** One element by selector, or a failure that names what was missing. */
function one(selector: string): HTMLElement {
  const found = document.querySelector<HTMLElement>(selector);
  if (found === null) throw new Error(`the Map is missing ${selector}`);
  return found;
}

/** Whether `first` precedes `second` in the document. */
function precedes(first: Element, second: Element): boolean {
  return Boolean(
    first.compareDocumentPosition(second) & Node.DOCUMENT_POSITION_FOLLOWING,
  );
}

/** The route's field element. */
function field(): HTMLElement {
  return one(".map");
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  mapStyle.clear();
  window.location.hash = "";
});

describe("the frame the Map is given", () => {
  it("is a workspace on the Map and a document everywhere else", async () => {
    // D-153: the graph occupies the usable route viewport. The frame is what
    // makes that possible -- a two-row grid with no overflow of its own --
    // and the Library and the Reader must keep the scrolling column they are.
    vi.stubGlobal("fetch", library());
    window.location.hash = "#/map";
    render(<App />);

    await waitFor(() => expect(document.querySelector(".map")).not.toBeNull());
    expect(document.querySelector(".shell--workspace")).not.toBeNull();

    // The same document, navigated to the Library.
    (screen.getByRole("link", { name: "Library" }) as HTMLAnchorElement).click();
    await waitFor(() => expect(document.querySelector(".map")).toBeNull());
    expect(document.querySelector(".shell--workspace")).toBeNull();
  });

  it("gives the route a field rather than a column of panels", async () => {
    // `stack map` until `T-212`: a flex column, which is what put the stage
    // 790 px down the document. The class is the composition, so this is the
    // regression guard for it.
    vi.stubGlobal("fetch", library());
    renderApp(<MapView createRenderer={fakeRenderers().factory} />, { route: "/map" });
    await waitFor(() => expect(document.querySelector(".map")).not.toBeNull());
    expect(field().classList.contains("stack")).toBe(false);
    // The stage and the overlay anchored to it share one absolutely placed
    // box, and that box is what is measured and handed to the policy.
    expect(one("[data-map-stage]").parentElement?.classList.contains("map__canvas")).toBe(true);
  });
});

describe("the workspace's surfaces", () => {
  it("holds the panels SPEC §7 places, in the surfaces it places them in", async () => {
    vi.stubGlobal("fetch", library());
    renderApp(<MapView createRenderer={fakeRenderers().factory} />, { route: "/map" });
    await waitFor(() => expect(document.querySelector("[data-map-nodes]")).not.toBeNull());

    // Search and the list the drawing is a view of: one surface, the field's
    // top start. SPEC §7 numbers the outline after the stage while placing it
    // visually in this drawer's panel list; the visual column is the binding
    // one, because the table's own subject is that tab order follows visual
    // order.
    const search = one(".map__float--search");
    expect(search.contains(one("[data-map-panel='search']"))).toBe(true);
    expect(search.contains(one("[data-map-panel='outline']"))).toBe(true);

    // Filters and counts: the field's top end.
    const status = one(".map__float--status");
    expect(status.contains(one("[data-map-filters]"))).toBe(true);
    expect(status.contains(one("[data-map-nodes]"))).toBe(true);

    // The legend, the quietest surface, at the bottom start.
    expect(one(".map__float--legend").contains(one("[data-map-panel='legend']"))).toBe(true);
  });

  it("makes Quick Read and the related list one drawer, and only one", async () => {
    // ADR 0006 clause 4 rejected a large inspector standing permanently
    // beside the graph and allows *one* primary drawer on demand. Two panels
    // in it, in SPEC §7's reading order: the focus and its active relations,
    // then the wider list.
    vi.stubGlobal("fetch", library());
    renderApp(<MapView createRenderer={fakeRenderers().factory} />, { route: `/map?focus=${KU1}` });
    await waitFor(() => expect(document.querySelector("[data-map-nodes]")).not.toBeNull());

    expect(document.querySelectorAll(".map__drawer")).toHaveLength(1);
    const drawer = one(".map__drawer");
    const quickread = one("[data-map-panel='quickread']");
    const related = one("[data-map-panel='related']");
    expect(drawer.contains(quickread)).toBe(true);
    expect(drawer.contains(related)).toBe(true);
    expect(precedes(quickread, related)).toBe(true);
  });

  it("keeps the camera's controls out from under the drawer", async () => {
    // In the approved Focus capture the drawer is full height at the inline
    // end and the zoom float is at the bottom end underneath it, so the
    // drawer paints over the camera controls: a reader who opens Quick Read
    // cannot zoom the graph they are reading about. Sharing one rail, with
    // the controls last, is what makes that impossible rather than checked.
    vi.stubGlobal("fetch", library());
    renderApp(<MapView createRenderer={fakeRenderers().factory} />, { route: `/map?focus=${KU1}` });
    await waitFor(() => expect(document.querySelector("[data-map-nodes]")).not.toBeNull());

    const rail = one(".map__endrail");
    const drawer = one(".map__drawer");
    const zoom = one(".map__zoom");
    expect(drawer.parentElement).toBe(rail);
    expect(zoom.parentElement).toBe(rail);
    expect(precedes(drawer, zoom)).toBe(true);
    expect(screen.getByRole("group", { name: "Map view controls" })).toBe(zoom);
  });

  it("keeps both drawer panels mounted with nothing selected", async () => {
    // A panel that disappears cannot say that nothing is selected, and the
    // rule `Disclosure` exists for is that a folded panel still states what
    // it holds.
    vi.stubGlobal("fetch", library());
    renderApp(<MapView createRenderer={fakeRenderers().factory} />, { route: "/map" });
    await waitFor(() => expect(document.querySelector("[data-map-nodes]")).not.toBeNull());
    expect(document.querySelector("[data-map-panel='quickread']")).not.toBeNull();
    expect(document.querySelector("[data-map-panel='related']")).not.toBeNull();
    expect(screen.getAllByText("nothing focused").length).toBeGreaterThan(0);
  });
});

describe("what a focus does to the field", () => {
  it("takes the drawer's width out of the field, and gives it back", async () => {
    // SPEC §4 and §8: the drawer's width comes out of the field *before* the
    // centre is placed, so the focused card can never sit underneath it --
    // a WCAG 2.2 AA *Focus Not Obscured* failure rather than a cosmetic
    // overlap. One class carries that fact, because five surfaces have to
    // agree about it: the renderer's container, the counts, the notices, the
    // Peek and the rail itself.
    vi.stubGlobal("fetch", library());
    const { unmount } = renderApp(<MapView createRenderer={fakeRenderers().factory} />, {
      route: "/map",
    });
    await waitFor(() => expect(document.querySelector("[data-map-nodes]")).not.toBeNull());
    expect(field().classList.contains("map--focused")).toBe(false);
    unmount();

    renderApp(<MapView createRenderer={fakeRenderers().factory} />, {
      route: `/map?focus=${KU1}`,
    });
    await waitFor(() => expect(document.querySelector("[data-map-nodes]")).not.toBeNull());
    expect(field().classList.contains("map--focused")).toBe(true);
  });
});

describe("what the card policy is told about the field", () => {
  it("marks every floating surface as chrome, and the transient Peek as not", async () => {
    // The policy refuses a card that would be drawn under a control, and it
    // is told *where* the controls are by measuring the surfaces marked here.
    // A surface that forgets the mark is a surface cards will be drawn under,
    // so the set is asserted rather than assumed.
    vi.stubGlobal("fetch", library());
    renderApp(<MapView createRenderer={fakeRenderers().factory} />, { route: `/map?focus=${KU1}` });
    await waitFor(() => expect(document.querySelector("[data-map-nodes]")).not.toBeNull());

    const marked = [...document.querySelectorAll("[data-map-chrome]")];
    expect(marked).toContain(one(".map__float--search"));
    expect(marked).toContain(one(".map__float--status"));
    expect(marked).toContain(one(".map__float--legend"));
    expect(marked).toContain(one(".map__drawer"));
    expect(marked).toContain(one(".map__zoom"));

    // The rail is not chrome: it spans the field's whole height and is mostly
    // the gap above a closed drawer, which is field a click must reach. The
    // notices are not chrome either -- they are centred *on* the field and
    // only appear when there is no picture to put a card on.
    expect(marked).not.toContain(one(".map__endrail"));
    expect(marked).not.toContain(one(".map__notices"));
  });

  it("states the honest states on the field, before the picture", async () => {
    // D-129 as a document order, unchanged by the recomposition: the text
    // that survives when the WebGL view cannot be read at all comes first.
    vi.stubGlobal("fetch", (() => new Promise(() => undefined)) as typeof fetch);
    renderApp(<MapView createRenderer={fakeRenderers().factory} />, { route: "/map" });
    await waitFor(() =>
      expect(screen.getByText("Reading a page of the graph…")).toBeDefined(),
    );
    const notices = one(".map__notices");
    expect(notices.contains(screen.getByText("Reading a page of the graph…"))).toBe(true);
    expect(precedes(notices, one("[data-map-stage]"))).toBe(true);
    expect(field().contains(notices)).toBe(true);
  });
});
