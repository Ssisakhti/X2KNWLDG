/**
 * `T-208`: the Map without a pointer, without WebGL, and in Persian.
 *
 * `T-204`-`T-207` proved the Map draws the right graph, states what it holds
 * and can be read. This suite asks the question those could not: is any of it
 * *reachable*. So every walk below uses real controls and platform events
 * only -- a button is clicked, a control receives focus, a disclosure is
 * expanded -- and two of the walks remove the canvas entirely, because a
 * journey that needs the canvas is a journey half the readers do not have.
 *
 * Four claims, in the order the gate states them:
 *
 * 1. **The whole journey exists in the DOM.** Search -> preview -> focus ->
 *    related knowledge -> Quick Read -> Reader, with no `mouseEnter` anywhere
 *    in this file's keyboard walk and no canvas event fired.
 * 2. **Empty is not absent and partial is not whole**, on screen and not only
 *    in `mapState.ts`'s unit tests.
 * 3. **A browser with no WebGL2 loses the picture and nothing else** -- and
 *    the companion list opens itself rather than waiting to be found.
 * 4. **Direction is data.** In Persian the document mirrors, the messages are
 *    Persian, and identifiers stay left to right inside them.
 */

import { fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { mapStyle } from "../map/mapStyle";
import { fakeRenderers } from "../test/mapRenderer";
import { KU1, KU2, graphBody, library, mapFetch } from "../test/mapServer";
import { concept, unit } from "../test/graphRecords";
import { renderApp } from "../test/render";

import { MapView } from "./MapView";

/** A panel by the name `Disclosure` gives it. */
function panel(id: string): HTMLElement {
  const found = document.querySelector<HTMLElement>(`[data-map-panel='${id}']`);
  if (found === null) throw new Error(`the Map is missing its ${id} panel`);
  return found;
}

function isOpen(id: string): boolean {
  return panel(id).dataset.mapPanelOpen === "true";
}

/** Expand a panel the way a reader does: the summary is the control. */
function expand(id: string): void {
  const details = panel(id).querySelector("details") as HTMLDetailsElement;
  if (details.open) return;
  details.open = true;
  fireEvent(details, new Event("toggle"));
}

/** The route's two readings, from the one attribute each carries. */
function readings(): { graph: string | null; canvas: string | null } {
  const root = document.querySelector<HTMLElement>(".map");
  return {
    graph: root?.dataset.mapReading ?? null,
    canvas: root?.dataset.mapCanvas ?? null,
  };
}

async function counted(): Promise<HTMLElement> {
  await waitFor(() => expect(document.querySelector("[data-map-nodes]")).not.toBeNull());
  return document.querySelector<HTMLElement>("[data-map-nodes]") as HTMLElement;
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  mapStyle.clear();
});

describe("the Map's journey without a pointer", () => {
  it("walks search, preview, focus, related knowledge, Quick Read and the Reader", async () => {
    // D-130's journey, entirely through controls. Nothing here hovers
    // anything and nothing fires a canvas event: the renderer is injected and
    // then ignored.
    vi.stubGlobal("fetch", library());
    const harness = fakeRenderers();
    renderApp(<MapView createRenderer={harness.factory} />, { route: "/map" });
    await counted();

    // Search: a real form, a real submit.
    // "at length" is in the long statement `library()` gives `KU-000001`, so
    // the walk lands on the entity with a neighbourhood to compare.
    fireEvent.change(screen.getByLabelText("Search"), { target: { value: "at length" } });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    await waitFor(() =>
      expect(document.querySelectorAll("[data-map-result='graph']").length).toBeGreaterThan(0),
    );

    // Preview: keyboard focus on a result opens the one Peek, and says it came
    // from the keyboard rather than from a pointer.
    const first = document.querySelector(
      "[data-map-result='graph'] [data-map-focus-action]",
    ) as HTMLButtonElement;
    fireEvent.focus(first);
    await waitFor(() => expect(document.querySelector("[data-map-peek]")).not.toBeNull());
    expect(document.querySelector("[data-map-peek]")?.getAttribute("data-peek-origin")).toBe(
      "keyboard",
    );

    // Focus: the same button selects, which is the same identity a canvas
    // click resolves.
    fireEvent.click(first);
    await waitFor(() =>
      expect(document.querySelector("[data-map-quickread]")?.getAttribute("data-map-quickread")).toBe(
        KU1,
      ),
    );

    // Related knowledge: the complete list, opened by the selection.
    expect(isOpen("related")).toBe(true);
    await waitFor(() =>
      expect(document.querySelectorAll("[data-map-related-entity]")).toHaveLength(2),
    );

    // Quick Read: the whole stored statement, in the panel the selection
    // opened.
    expect(isOpen("quickread")).toBe(true);
    expect(document.querySelector("[data-map-statement='complete']")).not.toBeNull();

    // The Reader: a real link, at the recorded time.
    const reader = document.querySelector("[data-map-reader-link]") as HTMLAnchorElement;
    expect(reader.getAttribute("href")).toContain("/sources/");
  });

  it("previews a neighbour before opening it, from the keyboard", async () => {
    // D-130's acceptance question is whether a reader can say what a
    // neighbour states before opening it. Hover answers it for a pointer;
    // this is the other half.
    vi.stubGlobal("fetch", library());
    const harness = fakeRenderers();
    renderApp(<MapView createRenderer={harness.factory} />, { route: `/map?focus=${KU1}` });
    await counted();
    await waitFor(() =>
      expect(document.querySelectorAll("[data-map-related-entity]")).toHaveLength(2),
    );

    const row = document.querySelector(
      `[data-map-related] [data-map-focus-action='${KU2}']`,
    ) as HTMLButtonElement;
    fireEvent.focus(row);
    await waitFor(() =>
      expect(document.querySelector("[data-map-peek]")?.getAttribute("data-map-peek")).toBe(KU2),
    );
    // And Escape dismisses it, because a keyboard has no "leave".
    fireEvent.keyDown(row, { key: "Escape" });
    await waitFor(() => expect(document.querySelector("[data-map-peek]")).toBeNull());
  });

  it("puts away the step it is not on, and never puts away the count", async () => {
    // "Collapsible rather than permanent competing panels", which is the
    // sentence `T-207` left for this task. The rule is that a folded panel
    // still states what it holds.
    vi.stubGlobal("fetch", library());
    const harness = fakeRenderers();
    renderApp(<MapView createRenderer={harness.factory} />, { route: "/map" });
    await counted();

    expect(isOpen("search")).toBe(true);
    expect(isOpen("quickread")).toBe(false);
    expect(isOpen("related")).toBe(false);
    expect(isOpen("legend")).toBe(false);
    // Folded, and still speaking: the summary says there is no selection
    // rather than leaving a bare heading.
    expect(screen.getAllByText("nothing focused").length).toBeGreaterThan(0);

    expand("outline");
    fireEvent.click(
      document.querySelector(
        `[data-map-panel='outline'] [data-map-focus-action='${KU1}']`,
      ) as HTMLButtonElement,
    );

    await waitFor(() => expect(isOpen("quickread")).toBe(true));
    expect(isOpen("related")).toBe(true);
    // The search rail is folded now that the journey has moved on, and it
    // still says what it found.
    expect(isOpen("search")).toBe(false);
    expect(screen.getByText("nothing searched yet")).toBeDefined();
  });

  it("shows the one Peek outside the panel that folds", async () => {
    // The regression this placement fixes: with something selected the search
    // rail folds, and the Peek used to be rendered inside it -- so a pointer
    // on a mark opened a card inside a closed `<details>`, which is a card
    // nobody can see. It is the route's now, and rendered once (invariant 13).
    vi.stubGlobal("fetch", library());
    const harness = fakeRenderers();
    renderApp(<MapView createRenderer={harness.factory} />, { route: `/map?focus=${KU1}` });
    await counted();
    await waitFor(() => expect(harness.latest()).not.toBeNull());

    expect(isOpen("search")).toBe(false);
    harness.latest()?.fireNode("enterNode", KU2);
    await waitFor(() => expect(document.querySelector("[data-map-peek]")).not.toBeNull());
    const card = document.querySelector("[data-map-peek]") as HTMLElement;
    expect(card.closest("[data-map-panel]")).toBeNull();
    expect(document.querySelectorAll("[data-map-peek]")).toHaveLength(1);
  });
});

describe("the Map without a canvas", () => {
  it("loses the picture and nothing else, and opens the list that replaces it", async () => {
    // A renderer that refuses to be created is a browser with no WebGL2 and a
    // stage with no size. Everything below is what a reader still has.
    vi.stubGlobal("fetch", library());
    const harness = fakeRenderers({ failOnCreate: true });
    renderApp(<MapView createRenderer={harness.factory} />, { route: "/map" });
    await counted();

    await waitFor(() =>
      expect(document.querySelector("[data-map-renderer-failed]")).not.toBeNull(),
    );
    // A whole graph and no picture of it, which is one state each.
    expect(readings()).toEqual({ graph: "whole", canvas: "refused" });
    // The stage is not announced as a picture of a graph, because there is no
    // picture.
    expect(document.querySelector("[data-map-stage]")?.getAttribute("role")).toBeNull();
    // The companion opened itself, and holds every loaded node.
    expect(isOpen("outline")).toBe(true);
    expect(panel("outline").dataset.mapOutline).toBe("3");
    expect(panel("outline").dataset.mapOutlineUnlisted).toBe("0");

    // And the journey still completes from it.
    fireEvent.click(
      document.querySelector(
        `[data-map-panel='outline'] [data-map-focus-action='${KU1}']`,
      ) as HTMLButtonElement,
    );
    await waitFor(() =>
      expect(document.querySelector("[data-map-quickread]")?.getAttribute("data-map-quickread")).toBe(
        KU1,
      ),
    );
    expect(document.querySelector("[data-map-statement='complete']")).not.toBeNull();
    expect(document.querySelector("[data-map-reader-link]")).not.toBeNull();
  });

  it("states what it holds before the picture, and the picture is not the account", async () => {
    // D-129 as a document order: the counts and the outline both precede the
    // stage, so a reader who never reaches the canvas has not been handed a
    // Map that reads as complete.
    vi.stubGlobal("fetch", library());
    const harness = fakeRenderers();
    renderApp(<MapView createRenderer={harness.factory} />, { route: "/map" });
    const state = await counted();
    const stage = document.querySelector("[data-map-stage]") as HTMLElement;
    expect(state.compareDocumentPosition(stage) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    // And the stage says out loud that its marks are a view of a list.
    expect(document.querySelector("[data-map-stage-companion]")?.textContent).toContain(
      "What this Map holds",
    );
  });
});

describe("the Map's honest states, on screen", () => {
  it("says an unanswered question is unanswered rather than empty", async () => {
    // A request that never resolves. The Map must not fill the silence with
    // zeros -- which would be D-068's shape: an empty answer to a question
    // nobody asked, presented as an answer.
    vi.stubGlobal("fetch", (() => new Promise(() => undefined)) as typeof fetch);
    renderApp(<MapView createRenderer={fakeRenderers().factory} />, { route: "/map" });
    await waitFor(() => expect(screen.getByText("Reading a page of the graph…")).toBeDefined());
    expect(readings()).toEqual({ graph: "loading", canvas: "pending" });
    expect(document.querySelector("[data-map-nodes]")).toBeNull();
    expect(screen.queryByText(/holds no graph node/)).toBeNull();
    // The companion is open, because there is no picture yet either.
    expect(isOpen("outline")).toBe(true);
  });

  it("says an empty graph is empty, and says so beside real counts", async () => {
    vi.stubGlobal("fetch", mapFetch(() => ({ body: graphBody([], [], { total: 0 }) })));
    renderApp(<MapView createRenderer={fakeRenderers().factory} />, { route: "/map" });
    const state = await counted();
    expect(state.dataset.mapNodes).toBe("0");
    expect(readings().graph).toBe("empty");
    expect(screen.getByText(/holds no graph node/)).toBeDefined();
    // An empty stage, stated as empty rather than as a drawing that failed.
    // Awaited, because the renderer takes the graph in an effect: for one
    // render the picture is honestly "not drawn yet" rather than "nothing to
    // draw", and those are two different sentences.
    await waitFor(() =>
      expect(
        screen.getByText("There is no node to draw, so the stage is empty rather than broken."),
      ).toBeDefined(),
    );
    expect(document.querySelector("[data-map-renderer-failed]")).toBeNull();
    // And the outline says *nothing is loaded* rather than that nothing
    // exists, because that is the only thing a list can know.
    expect(screen.getByText(/No node is loaded/)).toBeDefined();
  });

  it("keeps a refused question distinct from an empty answer", async () => {
    vi.stubGlobal(
      "fetch",
      mapFetch(() => ({
        status: 503,
        body: { error: { code: "index_unavailable", message: "not built" } },
      })),
    );
    renderApp(<MapView createRenderer={fakeRenderers().factory} />, { route: "/map" });
    await waitFor(() =>
      expect(document.querySelector("[data-error-code='index_unavailable']")).not.toBeNull(),
    );
    expect(document.querySelector("[data-map-nodes]")).toBeNull();
    // Refused, and *not* empty: the two would count the same nodes.
    expect(readings().graph).toBe("refused");
    expect(screen.queryByText(/holds no graph node/)).toBeNull();
    expect(screen.getByRole("button", { name: "Retry" })).toBeDefined();
  });

  it("says the counts it kept are not an answer to the request that failed", async () => {
    // A first page arrives, a continuation is refused. The graph on screen is
    // still true and is no longer an answer to the question that failed.
    let calls = 0;
    vi.stubGlobal(
      "fetch",
      mapFetch((url) => {
        if (!url.includes("/api/graph")) return { body: graphBody([], []) };
        calls += 1;
        return calls === 1
          ? {
              body: graphBody([unit("KU-000001"), concept("C-000001")], [], {
                next: "cursor-2",
                total: 4,
              }),
            }
          : { status: 500, body: { error: { code: "internal", message: "boom" } } };
      }),
    );
    renderApp(<MapView createRenderer={fakeRenderers().factory} />, { route: "/map" });
    const state = await counted();
    expect(state.dataset.mapNodes).toBe("2");

    fireEvent.click(screen.getByRole("button", { name: "Load the next page" }));
    await waitFor(() => expect(document.querySelector("[data-map-reading-stale]")).not.toBeNull());
    expect(state.dataset.mapNodes).toBe("2");
  });
});

describe("the Map answers a reduced-motion preference", () => {
  it("asks the camera to arrive rather than glide", async () => {
    // The stylesheet cannot reach a camera animated in script on a canvas,
    // which is why `map/motion.ts` exists and why this is asserted through
    // the renderer boundary rather than through the CSS.
    vi.stubGlobal("matchMedia", (query: string) => ({
      matches: query.includes("prefers-reduced-motion"),
      media: query,
    }));
    vi.stubGlobal("fetch", library());
    const harness = fakeRenderers();
    renderApp(<MapView createRenderer={harness.factory} />, { route: "/map" });
    await counted();
    await waitFor(() => expect(screen.getByRole("button", { name: "Zoom in" })).toHaveProperty("disabled", false));

    fireEvent.click(screen.getByRole("button", { name: "Zoom in" }));
    fireEvent.click(screen.getByRole("button", { name: "Reset the view" }));
    expect(harness.latest()?.animations).toEqual([{ duration: 0 }, { duration: 0 }]);
  });

  it("leaves the renderer's own easing alone when motion is welcome", async () => {
    vi.stubGlobal("matchMedia", (query: string) => ({ matches: false, media: query }));
    vi.stubGlobal("fetch", library());
    const harness = fakeRenderers();
    renderApp(<MapView createRenderer={harness.factory} />, { route: "/map" });
    await counted();
    await waitFor(() => expect(screen.getByRole("button", { name: "Zoom out" })).toHaveProperty("disabled", false));

    fireEvent.click(screen.getByRole("button", { name: "Zoom out" }));
    expect(harness.latest()?.animations).toEqual([undefined]);
  });
});

describe("the Map in Persian", () => {
  it("mirrors the interface while identifiers stay left to right", async () => {
    vi.stubGlobal("fetch", library());
    const harness = fakeRenderers();
    renderApp(<MapView createRenderer={harness.factory} />, {
      locale: "fa",
      route: `/map?focus=${KU1}`,
    });
    await counted();

    expect(document.documentElement.getAttribute("dir")).toBe("rtl");
    expect(screen.getByRole("heading", { name: "نقشهٔ دانش", level: 1 })).toBeDefined();
    // The new surfaces are translated too, not left in English.
    expect(screen.getByText("آنچه این نقشه در خود دارد")).toBeDefined();

    // An identifier is neutral text: it goes through `Mono`, which is the one
    // place `direction: ltr` and bidi isolation are stated (D-012).
    await waitFor(() =>
      expect(document.querySelector("[data-map-quickread]")).not.toBeNull(),
    );
    const identity = [...document.querySelectorAll(".mono")].find(
      (node) => node.textContent === KU1,
    );
    expect(identity).toBeDefined();
    // And the record's own statement carries its own direction rather than
    // the page's.
    const statement = document.querySelector("[data-map-statement='complete']");
    expect(statement?.getAttribute("dir")).toBe("auto");
  });

  it("offers the same surfaces in either direction", async () => {
    // There is no second stylesheet and no component that branches on "is
    // this RTL" (D-012), so the claim worth asserting is that nothing is
    // *missing* in Persian: the same five panels, from the same components.
    vi.stubGlobal("fetch", library());
    renderApp(<MapView createRenderer={fakeRenderers().factory} />, {
      locale: "fa",
      route: "/map",
    });
    await counted();
    for (const id of ["search", "outline", "quickread", "related", "legend"]) {
      expect(panel(id)).toBeDefined();
    }
  });
});
