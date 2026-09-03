/**
 * `T-204`, and the two things a Map on screen must not do: claim a page is the
 * graph, and outlive its own route.
 *
 * The renderer is injected here because jsdom has no WebGL. That is not a
 * workaround -- it is the only way to assert the sequence ADR 0005 invariant
 * 10 is about: one renderer per snapshot, another page of the same snapshot
 * reusing it, and a kill on unmount. The real renderer is walked in a browser.
 *
 * Every graph body below is shaped like the server's, including the D-059 case
 * the honest counts exist for: a first page carrying an edge whose far
 * endpoint has not arrived yet.
 */

import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { MapPoint } from "../map/mapSession";
import { App } from "../App";
import { fakeRenderers } from "../test/mapRenderer";
import { concept, edge, expressesConcept, unit } from "../test/graphRecords";
import { ORBIT_TIERS, orbitTier } from "../map/constellation";
import { mapStyle } from "../map/mapStyle";
import { jsonFetch, renderApp } from "../test/render";
// The route's server stub and its sized stage live beside the renderer fake
// (`T-208`), because this route now has two suites and one of each is the
// rule (§8.6).
import {
  C1,
  KU1,
  KU2,
  LONG_STATEMENT,
  entityBody,
  entityIdOf,
  graphBody,
  library,
  mapFetch,
  neighbourhoodBody,
  sizeTheStage,
} from "../test/mapServer";

import { MapView } from "./MapView";


/**
 * A renderer that records the lifecycle, and the camera the controls drive.
 *
 * `fakeRenderers` is shared with the Map's other suites (`T-207`), because the
 * renderer boundary now has event and coordinate adapters and three private
 * copies of a fake would be three chances to diverge from it.
 */
function recorder(
  behaviour: {
    failOnCreate?: boolean;
    points?: Record<string, MapPoint>;
    display?: Record<string, MapPoint>;
  } = {},
) {
  return fakeRenderers(behaviour);
}

function state(): HTMLElement {
  const panel = document.querySelector<HTMLElement>("[data-map-nodes]");
  if (panel === null) throw new Error("the Map states nothing about the graph it drew");
  return panel;
}

async function drawn(): Promise<HTMLElement> {
  await waitFor(() => expect(document.querySelector("[data-map-nodes]")).not.toBeNull());
  return state();
}

afterEach(() => {
  vi.unstubAllGlobals();
  // `mapStyle` is one object because there is one renderer (D-126). A test that
  // left a selection in it would style the next test's graph.
  mapStyle.clear();
});

describe("the Map", () => {
  it("states one honest page as the whole graph it is", async () => {
    vi.stubGlobal(
      "fetch",
      mapFetch(() =>
        ({
          body: graphBody(
            [unit("KU-000001"), unit("KU-000002"), concept("C-000001")],
            [edge(KU1, KU2), expressesConcept(KU1, C1)],
            { total: 3 },
          ),
        }),
      ),
    );
    const { factory, events } = recorder();
    renderApp(<MapView createRenderer={factory} />);

    const panel = await drawn();
    expect(panel.dataset.mapNodes).toBe("3");
    expect(panel.dataset.mapEdges).toBe("2");
    expect(panel.dataset.mapHeld).toBe("0");
    expect(panel.dataset.mapComplete).toBe("true");
    expect(panel.dataset.mapTruncated).toBe("false");
    expect(screen.getByText("This is the whole graph these filters describe.")).toBeDefined();
    // Nothing to load, so nothing offers to.
    expect(document.querySelector("[data-map-load-more]")).toBeNull();
    /*
     * `waitFor`, because `create` is not the effect `drawn()` waits for.
     *
     * `drawn()` resolves on `[data-map-nodes]` — the counts panel, which
     * appears as soon as the snapshot lands — while the renderer is created by
     * a *different* effect, once the stage has been measured and there is a
     * picture to attach. Asserting the count immediately therefore raced, and
     * it lost about one run in twenty: under CI's parallel load the counts
     * panel is committed a tick before the session effect runs. The same wait
     * is on every positive assertion about a renderer event below, for the
     * same reason.
     */
    await waitFor(() =>
      expect(events.filter((name) => name === "create")).toHaveLength(1),
    );
  });

  it("asks the server the question its URL states, and ignores a filter it cannot read", async () => {
    // The two halves of one rule. `provenance_class=derived` is a value the
    // contract has, so it must reach the request; `relation_vocabulary=cannonical`
    // is a typo, and `mapLink` drops it rather than repairing it to `canonical`
    // -- a repaired filter would draw a graph the user never asked for and
    // would look entirely successful doing it.
    const urls: string[] = [];
    vi.stubGlobal(
      "fetch",
      mapFetch((url) => {
        urls.push(url);
        return { body: graphBody([unit("KU-000001")], [], { total: 1 }) };
      }),
    );
    const { factory } = recorder();
    renderApp(<MapView createRenderer={factory} />, {
      route: "/map?provenance_class=derived&relation_vocabulary=cannonical",
    });

    await drawn();
    const graphUrl = urls.find((url) => url.includes("/graph"));
    expect(graphUrl).toBeDefined();
    expect(graphUrl).toContain("provenance_class=derived");
    expect(graphUrl).not.toContain("relation_vocabulary");
    expect(graphUrl).not.toContain("cannonical");
  });

  it("styles the focus its URL names, once the graph holds it", async () => {
    vi.stubGlobal(
      "fetch",
      mapFetch(() => ({
        body: graphBody(
          [unit("KU-000001"), unit("KU-000002"), concept("C-000001")],
          [edge(KU1, KU2)],
          { total: 3 },
        ),
      })),
    );
    const { factory } = recorder();
    renderApp(<MapView createRenderer={factory} />, { route: `/map?focus=${KU1}` });

    await drawn();
    await waitFor(() => expect(mapStyle.view.selectedNode).toBe(KU1));
    // The neighbours are the ones actually drawn: `KU2` shares an edge, the
    // concept does not. Nothing here claims that is the whole neighbourhood --
    // the bounded one over the API is `T-207`'s.
    expect([...mapStyle.view.neighbourNodes]).toEqual([KU2]);
  });

  it("leaves the style table unfocused when the route unmounts", async () => {
    /*
     * `mapStyle` is a module singleton, and `clear()` was called only in test
     * setup — by the four suites that need it *precisely because* the
     * singleton carries state across mounts. Production never called it:
     * focus something, leave for the Library, come back, and the session
     * effect runs before the view-state write, so the first painted frame
     * dimmed all 86 marks around a selection that no longer existed.
     */
    vi.stubGlobal("fetch", library());
    const { factory } = recorder();
    const view = renderApp(<MapView createRenderer={factory} />, {
      route: `/map?focus=${KU1}`,
    });

    await drawn();
    await waitFor(() => expect(mapStyle.view.selectedNode).toBe(KU1));

    view.unmount();

    expect(mapStyle.view.selectedNode).toBeNull();
    expect(mapStyle.view.hoveredNode).toBeNull();
    expect([...mapStyle.view.neighbourNodes]).toEqual([]);
    expect([...mapStyle.view.cardedNodes]).toEqual([]);
  });

  it("highlights nothing when the URL names a focus the loaded pages do not hold", async () => {
    // Dimming every drawn node around a selection that is not on screen would
    // be a picture of a focus that does not exist. The counts stay true and the
    // canvas stays unfocused.
    vi.stubGlobal(
      "fetch",
      mapFetch(() => ({ body: graphBody([unit("KU-000001")], [], { total: 1 }) })),
    );
    const { factory } = recorder();
    renderApp(<MapView createRenderer={factory} />, {
      route: "/map?focus=youtube:pqlWNihgdjI:KU-999999",
    });

    const panel = await drawn();
    expect(panel.dataset.mapNodes).toBe("1");
    expect(mapStyle.view.selectedNode).toBeNull();
    expect([...mapStyle.view.neighbourNodes]).toEqual([]);
  });

  it("changing a filter is a new question, not a repaint of the old answer", async () => {
    const urls: string[] = [];
    vi.stubGlobal(
      "fetch",
      mapFetch((url) => {
        urls.push(url);
        return { body: graphBody([unit("KU-000001")], [], { total: 1 }) };
      }),
    );
    const { factory, events } = recorder();
    renderApp(<MapView createRenderer={factory} />, { route: "/map" });

    await drawn();
    await waitFor(() =>
      expect(events.filter((name) => name === "create")).toHaveLength(1),
    );

    const vocabulary = screen.getByLabelText("Relation vocabulary");
    fireEvent.change(vocabulary, { target: { value: "canonical" } });

    // A new snapshot, so a new renderer over a new graph (D-118) -- not
    // another page merged into the one already drawn.
    await waitFor(() => expect(events.filter((name) => name === "create")).toHaveLength(2));
    await waitFor(() =>
      expect(urls.some((url) => url.includes("relation_vocabulary=canonical"))).toBe(true),
    );
  });

  it("stays visibly partial until the rest of the graph is loaded", async () => {
    // D-059: the first page carries an edge to a node on the second, so the
    // Map holds that edge rather than drawing it or inventing its endpoint --
    // and says how many it is holding.
    let calls = 0;
    vi.stubGlobal(
      "fetch",
      mapFetch((url) => {
        calls += 1;
        return url.includes("cursor=next")
          ? {
              body: graphBody([unit("KU-000002")], [edge(KU1, KU2)], {
                truncated: true,
                total: 2,
              }),
            }
          : {
              body: graphBody([unit("KU-000001")], [edge(KU1, KU2)], {
                truncated: true,
                next: "next",
                total: 2,
              }),
            };
      }),
    );
    const { factory, events } = recorder();
    renderApp(<MapView createRenderer={factory} />);

    const first = await drawn();
    expect(first.dataset.mapNodes).toBe("1");
    expect(first.dataset.mapEdges).toBe("0");
    expect(first.dataset.mapHeld).toBe("1");
    expect(first.dataset.mapComplete).toBe("false");
    expect(screen.getByText("Part of the graph. More of it exists than is drawn.")).toBeDefined();

    fireEvent.click(screen.getByRole("button", { name: "Load the next page" }));

    await waitFor(() => expect(state().dataset.mapNodes).toBe("2"));
    const second = state();
    expect(second.dataset.mapEdges).toBe("1");
    expect(second.dataset.mapHeld).toBe("0");
    // The last page of a paged walk reports `truncated` too, and the loaded
    // count reaching the stated total is what settles wholeness (D-123).
    expect(second.dataset.mapTruncated).toBe("true");
    expect(second.dataset.mapComplete).toBe("true");
    expect(calls).toBe(2);

    // A second page is more of the same graph: it re-settles the layout of the
    // renderer already on screen rather than creating another one.
    await waitFor(() => expect(events).toContain("refresh"));
    expect(events.filter((name) => name === "create")).toHaveLength(1);
    expect(document.querySelector("[data-map-load-more]")).toBeNull();
  });

  it("kills the renderer when the route closes", async () => {
    vi.stubGlobal(
      "fetch",
      mapFetch(() => ({ body: graphBody([unit("KU-000001")], [], { total: 1 }) })),
    );
    const { factory, events } = recorder();
    const view = renderApp(<MapView createRenderer={factory} />);
    await drawn();
    await waitFor(() =>
      expect(events.filter((name) => name === "create")).toHaveLength(1),
    );

    view.unmount();

    expect(events.filter((name) => name === "kill")).toHaveLength(1);
    expect(events.filter((name) => name === "create")).toHaveLength(1);
  });

  it("drives zoom and reset through the renderer's camera", async () => {
    vi.stubGlobal(
      "fetch",
      mapFetch(() => ({ body: graphBody([unit("KU-000001")], [], { total: 1 }) })),
    );
    const { factory, events } = recorder();
    renderApp(<MapView createRenderer={factory} />);
    await drawn();
    // The counts arrive one render before the camera does: the effect that
    // hands the graph to the renderer runs after the render that first sees
    // the page, and there is no camera to drive until it has (`T-208`).
    await waitFor(() => expect(screen.getByRole("button", { name: "Zoom in" })).toHaveProperty("disabled", false));

    fireEvent.click(screen.getByRole("button", { name: "Zoom in" }));
    fireEvent.click(screen.getByRole("button", { name: "Zoom out" }));
    fireEvent.click(screen.getByRole("button", { name: "Reset the view" }));

    expect(events.filter((name) => ["zoomIn", "zoomOut", "reset"].includes(name))).toEqual([
      "zoomIn",
      "zoomOut",
      "reset",
    ]);
  });

  it("states a renderer it could not create, and keeps the counts readable", async () => {
    // A browser with no WebGL2, or a container with no size, is a state to
    // state: the index answered, and only the drawing is missing.
    vi.stubGlobal(
      "fetch",
      mapFetch(() => ({ body: graphBody([unit("KU-000001")], [], { total: 1 }) })),
    );
    const { factory } = recorder({ failOnCreate: true });
    renderApp(<MapView createRenderer={factory} />);

    await waitFor(() => expect(document.querySelector("[data-map-renderer-failed]")).not.toBeNull());
    expect(screen.getByText("The graph could not be drawn")).toBeDefined();
    expect(state().dataset.mapNodes).toBe("1");
    expect(screen.getByRole("button", { name: "Zoom in" })).toHaveProperty("disabled", true);
  });

  it("renders an unbuilt index as the refusal it is, not as an empty graph", async () => {
    vi.stubGlobal(
      "fetch",
      mapFetch(() => ({
        status: 503,
        body: {
          error: {
            code: "index_unavailable",
            message: "The index has not been built.",
          },
        },
      })),
    );
    const { factory, events } = recorder();
    renderApp(<MapView createRenderer={factory} />);

    await waitFor(() =>
      expect(document.querySelector("[data-error-code='index_unavailable']")).not.toBeNull(),
    );
    expect(document.querySelector("[data-map-nodes]")).toBeNull();
    expect(events).not.toContain("create");
    expect(screen.getByRole("button", { name: "Retry" })).toBeDefined();
  });

  it("says an empty graph is empty rather than drawing nothing silently", async () => {
    vi.stubGlobal(
      "fetch",
      mapFetch(() => ({ body: graphBody([], [], { total: 0 }) })),
    );
    const { factory } = recorder();
    renderApp(<MapView createRenderer={factory} />);

    const panel = await drawn();
    expect(panel.dataset.mapNodes).toBe("0");
    expect(panel.dataset.mapComplete).toBe("true");
    expect(
      screen.getByText(
        "The index holds no graph node, so there is nothing to draw. This is not a drawing that failed.",
      ),
    ).toBeDefined();
  });

  it("refuses a page that contradicts one already drawn, naming the field", async () => {
    // D-125, seen from the view: the page is refused whole, the refusal names
    // the field, and the graph already drawn is still there.
    vi.stubGlobal(
      "fetch",
      mapFetch((url) =>
        url.includes("cursor=next")
          ? {
              body: graphBody([unit("KU-000001", { confidence: 0.2 })], [], {
                truncated: true,
                total: 2,
              }),
            }
          : {
              body: graphBody([unit("KU-000001")], [], {
                truncated: true,
                next: "next",
                total: 2,
              }),
            },
      ),
    );
    const { factory } = recorder();
    renderApp(<MapView createRenderer={factory} />);
    await drawn();

    fireEvent.click(screen.getByRole("button", { name: "Load the next page" }));

    await waitFor(() => expect(document.querySelector("[data-map-conflict]")).not.toBeNull());
    expect(document.querySelector("[data-map-conflict]")?.getAttribute("data-map-conflict")).toBe(
      "confidence",
    );
    expect(state().dataset.mapNodes).toBe("1");
  });
});

/**
 * `T-207`: the canvas as a third caller, the bounded constellation, and the
 * journey D-130 approves -- compare two neighbours, focus one, read it whole,
 * come back.
 *
 * The renderer is still injected, so "a click on the canvas" is the session's
 * `clickNode` handler being fired: what is asserted is that the *view* answers
 * it with the same selection identity the rail's buttons use, which is the
 * property §8.6 forbids a second of.
 */
describe("the Map's canvas and its constellation", () => {

  it("focuses the node a click on the canvas names, through the rail's own function", async () => {
    vi.stubGlobal("fetch", library());
    const harness = recorder();
    renderApp(<MapView createRenderer={harness.factory} />, { route: "/map" });
    await drawn();

    // Nothing selected, and the Map says so on the surface Explore has: the
    // drawer is Focus's and is not mounted at all (`T-216`, D-200), so the
    // sentence comes from the search rail's own focus row.
    expect(document.querySelector(".map__drawer")).toBeNull();
    expect(screen.getByText("Nothing is focused. Choose a result to focus it.")).toBeDefined();

    harness.latest()?.fireNode("clickNode", KU1);

    // The selection reached `focusEntity`, which is the URL -- so the style
    // table, the rail, Quick Read and the related list all agree because none
    // of them keeps its own copy.
    await waitFor(() => expect(mapStyle.view.selectedNode).toBe(KU1));
    await waitFor(() =>
      expect(document.querySelector("[data-map-quickread]")?.getAttribute("data-map-quickread")).toBe(
        KU1,
      ),
    );
  });

  it("opens the one Peek from a pointer on the canvas, and closes it on leaving", async () => {
    vi.stubGlobal("fetch", library());
    const harness = recorder();
    renderApp(<MapView createRenderer={harness.factory} />, { route: "/map" });
    await drawn();

    harness.latest()?.fireNode("enterNode", KU2);
    await waitFor(() => expect(document.querySelectorAll("[data-map-peek]")).toHaveLength(1));
    expect(document.querySelector("[data-map-peek]")?.getAttribute("data-map-peek")).toBe(KU2);
    // A Peek is not a selection, and the URL is the selection.
    expect(document.querySelector("[data-map-quickread]")).toBeNull();

    harness.latest()?.fireNode("leaveNode", KU2);
    await waitFor(() => expect(document.querySelector("[data-map-peek]")).toBeNull());
  });

  it("lights the focus's neighbours from the drawn edges and the bounded answer", async () => {
    vi.stubGlobal("fetch", library());
    const harness = recorder();
    renderApp(<MapView createRenderer={harness.factory} />, { route: `/map?focus=${KU1}` });
    await drawn();

    await waitFor(() => expect(mapStyle.view.neighbourNodes.size).toBe(2));
    expect([...mapStyle.view.neighbourNodes].sort()).toEqual([C1, KU2].sort());
  });

  it("draws the Directional Orbit over the field, as presentation only", async () => {
    // `T-213` replaced the mark-anchored constellation entirely. The marks
    // are still there and still clickable; the *cards* are now placed by
    // direction and hop from the field's centre, so this test no longer
    // arranges anchors -- there is nothing for an anchor to decide.
    sizeTheStage();
    vi.stubGlobal("fetch", library());
    const harness = recorder();
    renderApp(<MapView createRenderer={harness.factory} />, { route: `/map?focus=${KU1}` });
    await drawn();

    await waitFor(() => expect(document.querySelector("[data-map-overlay]")).not.toBeNull());
    const overlay = document.querySelector("[data-map-overlay]") as HTMLElement;
    // Presentation over the canvas: no focusable control, and hidden from the
    // accessibility tree, because every card is a second view of a row in the
    // related list.
    expect(overlay.getAttribute("aria-hidden")).toBe("true");
    expect(overlay.querySelectorAll("button, a, input, select")).toHaveLength(0);
    // A 900x600 stage is the `compact` tier, and the route says which
    // composition it drew rather than leaving it to be counted.
    expect(document.querySelector(".map")?.getAttribute("data-map-tier")).toBe("compact");
    expect(overlay.getAttribute("data-map-orbit-tier")).toBe("compact");

    const cards = [...document.querySelectorAll("[data-map-card]")].map((node) => ({
      id: node.getAttribute("data-map-card"),
      primary: node.getAttribute("data-map-card-primary"),
      side: node.getAttribute("data-map-card-side"),
    }));
    // The focus is the centre, always: it is the one card D-132 guarantees
    // and the composition is built around it.
    expect(cards[0]).toEqual({ id: KU1, primary: "true", side: "centre" });
    // Whatever else this 900x600 field could hold is a neighbour of the focus
    // on the side its own relation runs, and *every* neighbour it could not
    // hold is counted rather than dropped. That accounting is the clause R20
    // rests on; the exact number of cards a 900x600 field fits is not, and
    // asserting it here would be asserting this fixture's geometry twice.
    for (const card of cards.slice(1)) {
      expect([C1, KU2]).toContain(card.id);
      expect(["incoming", "outgoing"]).toContain(card.side);
    }
    const counted = Number(
      document.querySelector("[data-map-stage-omitted]")?.getAttribute("data-map-stage-omitted") ??
        "0",
    );
    expect(cards.length - 1 + counted).toBe(2);

    // The centre card is centred in the measured field, not anchored to a
    // mark. The tier's own box, read from the table rather than restated, so
    // this measures the composition and not a number typed twice.
    const box = ORBIT_TIERS.compact.primaryBox;
    const primary = document.querySelector(`[data-map-card='${KU1}']`) as HTMLElement;
    expect(primary.style.left).toBe(`${(900 - box.width) / 2}px`);
    expect(primary.style.top).toBe(`${(600 - box.height) / 2}px`);
    expect(primary.style.inlineSize).toBe(`${box.width}px`);
    // And it shortens the statement visibly rather than silently.
    expect(primary.querySelector("[data-truncated]")).not.toBeNull();
  });

  it("brings a new focus and its drawn neighbours onto the stage (`T-209`, D-146)", async () => {
    // Selection and the camera used to be two halves that never spoke: the
    // camera framed the whole graph, so a focus sat wherever the layout had
    // put it and its whole neighbourhood was a tenth of the stage wide.
    sizeTheStage();
    vi.stubGlobal("fetch", library());
    const harness = recorder({
      display: {
        [KU1]: { x: 0.1, y: 0.1 },
        [KU2]: { x: 0.5, y: 0.1 },
        [C1]: { x: 0.5, y: 0.3 },
      },
    });
    renderApp(<MapView createRenderer={harness.factory} />, { route: `/map?focus=${KU1}` });
    await drawn();

    await waitFor(() => expect(harness.latest()?.framings.length).toBe(1));
    const target = harness.latest()?.framings[0];
    // The middle of the focus *and its drawn neighbours*, which is what makes
    // the neighbourhood readable rather than the focus merely centred.
    expect(target?.x).toBeCloseTo(0.3);
    expect(target?.y).toBeCloseTo(0.2);
    expect(target?.ratio).toBeGreaterThan(0);

    // And once per selection. The bounded neighbourhood arrives *after* this
    // -- it is a second request -- and moving the camera again when it lands
    // would pull the picture out from under a reader who had started reading.
    await waitFor(() =>
      expect(document.querySelectorAll("[data-map-related-entity]").length).toBeGreaterThan(0),
    );
    expect(harness.latest()?.framings).toHaveLength(1);
  });

  it("frames nothing for a focus these pages have not loaded", async () => {
    // The URL may name an entity this filter never reached. There is no mark
    // to centre, and pointing the camera at where it would have been is a
    // picture of a focus that does not exist.
    sizeTheStage();
    vi.stubGlobal("fetch", library());
    const harness = recorder({ display: { [KU1]: { x: 0.2, y: 0.2 } } });
    renderApp(<MapView createRenderer={harness.factory} />, {
      route: "/map?focus=youtube:pqlWNihgdjI:KU-999999",
    });
    await drawn();
    await waitFor(() => expect(document.querySelector("[data-map-nodes]")).not.toBeNull());
    expect(harness.latest()?.framings).toHaveLength(0);
  });

  it("gives the narrow field SPEC §5's stack tier, with no relation dropped", async () => {
    /*
     * The tier the stylesheet contradicted itself about. One paragraph called
     * the document composition a scope boundary owed to `T-213`; the rule at
     * the end of the same block already said the document *is* the `stack`
     * tier. `T-213` closed and `T-216` closed after it, so each half pointed
     * at the other and no ticket owned the tier.
     *
     * What SPEC §5 asks for below 900px: no orbit at all, the focus card, and
     * then every relation as a row with its own direction and its hop count,
     * none of them dropped.
     */
    sizeTheStage({ width: 390, height: 480 });
    vi.stubGlobal("fetch", library());
    const harness = recorder();
    renderApp(<MapView createRenderer={harness.factory} />, { route: `/map?focus=${KU1}` });
    await drawn();

    // The `stack` tier draws no orbit at all.
    expect(orbitTier(390)).toBe("stack");
    await waitFor(() =>
      expect(document.querySelectorAll("[data-map-related-entity]").length).toBeGreaterThan(0),
    );
    expect(document.querySelector("[data-map-overlay]")).toBeNull();

    // The focus card.
    expect(document.querySelector("[data-map-quickread]")).not.toBeNull();

    // And every relation as a row: the neighbourhood's own count, with a hop
    // count on each. `library()` answers KU1 with two neighbours.
    const rows = [...document.querySelectorAll("[data-map-related-entity]")];
    expect(rows.map((row) => row.getAttribute("data-map-related-entity")).sort()).toEqual(
      [C1, KU2].sort(),
    );
    for (const row of rows) {
      expect(row.textContent).toMatch(/hop/i);
    }
  });

  it("puts the search rail before the counts, which is the order a reader reads", async () => {
    /*
     * The counts are at the inline *end* and the search rail at the inline
     * *start*, and the counts came first in the DOM — so focus landed
     * top-end, jumped to the start, back to the end for the drawer and the
     * camera, and back to the start for the legend: the field crossed twice,
     * in a file that argues tab order must follow visual order.
     *
     * D-129's constraint is the other one asserted here: the counts still
     * precede the stage, because they are the text that survives when the
     * WebGL view cannot be read at all.
     */
    sizeTheStage();
    vi.stubGlobal("fetch", library());
    const harness = recorder();
    renderApp(<MapView createRenderer={harness.factory} />, { route: "/map" });
    await drawn();

    const order = [...document.querySelectorAll(".map__float--search, .map__float--status, [data-map-stage]")];
    const index = (selector: string) =>
      order.findIndex((element) => element.matches(selector));
    expect(index(".map__float--search")).toBeGreaterThanOrEqual(0);
    expect(index(".map__float--search")).toBeLessThan(index(".map__float--status"));
    expect(index(".map__float--status")).toBeLessThan(index("[data-map-stage]"));
  });

  it("still draws the orbit for a focus these pages have not loaded", async () => {
    /*
     * The other half of the case above, and the half that was missing.
     *
     * The test before this one checked only that no camera framing happened,
     * never whether the composition was drawn -- so the orbit memo guarding on
     * `focus.focus` and then passing `drawnFocus` (null unless the graph
     * already holds the node) was invisible to the whole suite. Open
     * `#/map?focus=...` cold and the field drew no centre card, no neighbours,
     * no pills and no rings, while Quick Read and the related list rendered
     * the entity and its neighbours from the same entity request.
     */
    sizeTheStage();
    const one = unit("KU-000001", { label: LONG_STATEMENT });
    const two = unit("KU-000002");
    const three = concept("C-000001");
    // The page holds only KU2 -- the graph filter never reached the focus --
    // while the entity and neighbourhood requests answer for KU1 in full.
    vi.stubGlobal(
      "fetch",
      mapFetch(
        () => ({ body: graphBody([two], [], { total: 1 }) }),
        (url) => {
          if (url.includes("/api/entities/")) {
            return entityIdOf(url) === KU1 ? { body: entityBody(one) } : null;
          }
          if (url.includes("/api/graph/neighborhood/")) {
            return entityIdOf(url) === KU1
              ? {
                  body: neighbourhoodBody(
                    KU1,
                    [one, two, three],
                    [edge(KU1, KU2, "supports"), expressesConcept(KU1, C1)],
                  ),
                }
              : null;
          }
          return null;
        },
      ),
    );
    const harness = recorder({ display: { [KU2]: { x: 0.2, y: 0.2 } } });
    renderApp(<MapView createRenderer={harness.factory} />, { route: `/map?focus=${KU1}` });
    await drawn();

    // The premise: no page holds the focus, so no camera framing happens.
    await waitFor(() => expect(document.querySelector("[data-map-nodes]")).not.toBeNull());
    expect(harness.latest()?.framings).toHaveLength(0);

    // And the related list proves the entity request answered: the record is
    // in hand even though the graph does not hold the node.
    await waitFor(() =>
      expect(document.querySelectorAll("[data-map-related-entity]").length).toBeGreaterThan(0),
    );

    await waitFor(() => expect(document.querySelector("[data-map-overlay]")).not.toBeNull());
    const primary = document.querySelector(`[data-map-card='${KU1}']`);
    expect(primary).not.toBeNull();
    expect(primary?.getAttribute("data-map-card-primary")).toBe("true");
    // And the neighbours it came with, so this is a composition and not a
    // lone card: a centre, at least one neighbour, and a ring.
    expect(document.querySelectorAll("[data-map-card]").length).toBeGreaterThan(1);
    expect(document.querySelectorAll(".map__orbit-ring").length).toBeGreaterThan(0);
  });

  it("closes the Peek on Escape even when nothing on the route has focus", async () => {
    // `T-209`'s correction to `T-208`. The route used to read the key from a
    // React `onKeyDown` on its own element, which only sees a key pressed
    // while focus is *inside* it -- and a canvas takes no focus, so a Peek
    // opened by a pointer on a mark was the one Peek Escape could not close.
    // The key is dispatched at the document here, which is where a browser
    // sends it when nothing is focused.
    vi.stubGlobal("fetch", library());
    const harness = recorder();
    renderApp(<MapView createRenderer={harness.factory} />, { route: "/map" });
    await drawn();

    harness.latest()?.fireNode("enterNode", KU2);
    await waitFor(() => expect(document.querySelector("[data-map-peek]")).not.toBeNull());
    expect(document.activeElement).toBe(document.body);

    fireEvent.keyDown(document.body, { key: "Escape" });
    await waitFor(() => expect(document.querySelector("[data-map-peek]")).toBeNull());
  });

  it("keeps the orbit still through a camera gesture that used to erase it", async () => {
    // The inverse of the test `T-207` wrote here, and the inversion is the
    // point. Cards anchored to marks had to be hidden while the camera moved
    // and placed again when it stopped, because they reflowed every frame.
    // The orbit reads no camera at all: a frame changes nothing about it, so
    // the composition a reader is reading stays on screen and stays put.
    sizeTheStage();
    vi.stubGlobal("fetch", library());
    const harness = recorder();
    renderApp(<MapView createRenderer={harness.factory} />, { route: `/map?focus=${KU1}` });
    await drawn();
    await waitFor(() => expect(document.querySelector("[data-map-overlay]")).not.toBeNull());
    const before = (document.querySelector(`[data-map-card='${KU1}']`) as HTMLElement).style.left;

    harness.latest()?.fireRender();
    harness.latest()?.fireRender();

    expect(document.querySelector("[data-map-overlay]")).not.toBeNull();
    expect((document.querySelector(`[data-map-card='${KU1}']`) as HTMLElement).style.left).toBe(
      before,
    );
  });

  it("draws no constellation at all when the renderer could not be created", async () => {
    // And reports no omissions either: "not drawn on the Map" would explain
    // the wrong thing when the whole canvas is missing. The renderer's own
    // refusal is what is stated, and the related list is complete regardless.
    vi.stubGlobal("fetch", library());
    const harness = recorder({ failOnCreate: true });
    renderApp(<MapView createRenderer={harness.factory} />, { route: `/map?focus=${KU1}` });

    await waitFor(() =>
      expect(document.querySelector("[data-map-renderer-failed]")).not.toBeNull(),
    );
    await waitFor(() => expect(document.querySelectorAll("[data-map-related-entity]")).toHaveLength(2));
    expect(document.querySelector("[data-map-overlay]")).toBeNull();
    expect(document.querySelector("[data-map-stage-omitted]")).toBeNull();
  });

  it("compares two neighbours, focuses one, and reads it whole -- without leaving the Map", async () => {
    // `T-207`'s acceptance criterion, walked.
    vi.stubGlobal("fetch", library());
    const harness = recorder();
    renderApp(<MapView createRenderer={harness.factory} />, { route: `/map?focus=${KU1}` });
    await drawn();

    // Compare: both neighbours, each with its own statement and its own real
    // relation, before anything is opened.
    await waitFor(() => expect(document.querySelectorAll("[data-map-related-entity]")).toHaveLength(2));
    // Scoped to the related list, because `T-208`'s outline lists the same
    // loaded record on the same card -- deliberately: the two panels answer
    // different questions ("what this Map holds" and "what this focus is
    // connected to") about one entity, and the statement is the entity's.
    const relatedPanel = document.querySelector("[data-map-related]") as HTMLElement;
    expect(
      within(relatedPanel).getByText(
        "A statement the transcript actually makes, numbered KU-000002.",
      ),
    ).toBeDefined();
    // Twice each: once on the neighbour's row, once among the focus's own
    // active relations in Quick Read. Both are the same record, named the same
    // way, because both go through `RelationCue`.
    expect(screen.getAllByText("supports")).toHaveLength(2);
    expect(screen.getAllByText("expresses_concept")).toHaveLength(2);

    // Read the focus whole: the complete statement, not a preview of it.
    expect(document.querySelector("[data-map-statement='complete']")?.textContent).toBe(
      LONG_STATEMENT,
    );

    // Focus the neighbour from the list, which is the same identity a canvas
    // click resolves.
    fireEvent.click(
      document.querySelector(`[data-map-focus-action="${KU2}"]`) as HTMLButtonElement,
    );

    await waitFor(() =>
      expect(document.querySelector("[data-map-quickread]")?.getAttribute("data-map-quickread")).toBe(
        KU2,
      ),
    );
    // The new focus has its own neighbourhood, and the Map was never rebuilt
    // to show it: one renderer, one accumulated graph.
    await waitFor(() => expect(document.querySelectorAll("[data-map-related-entity]")).toHaveLength(1));
    await waitFor(() =>
      expect(harness.events.filter((name) => name === "create")).toHaveLength(1),
    );
    expect(harness.events.filter((name) => name === "kill")).toHaveLength(0);
  });
});

describe("the Map's address", () => {
  it("is reached by navigating straight to `#/map`, and states the renderer it cannot load", async () => {
    // Direct navigation and reload are the same event under `HashRouter`, so
    // this is the reload case too. Nothing is injected here, which means the
    // route takes its real path: it asks for the renderer module, jsdom's
    // missing `WebGL2RenderingContext` refuses it, and the Map renders the
    // graph's counts and a stated refusal instead of an empty page or a crash.
    vi.stubGlobal(
      "fetch",
      mapFetch((url) =>
        url.includes("/api/graph")
          ? { body: graphBody([unit("KU-000001"), unit("KU-000002")], [edge(KU1, KU2)], { total: 2 }) }
          : { status: 503, body: { error: { code: "index_unavailable", message: "not built" } } },
      ),
    );
    window.location.hash = "#/map";
    // `App` brings its own `HashRouter` and locale provider, so it is rendered
    // bare: the test helper's `MemoryRouter` would be a second router.
    render(<App />);

    await waitFor(() => expect(document.querySelector("[data-map-nodes]")).not.toBeNull());
    expect(screen.getByRole("heading", { name: "Knowledge Map", level: 1 })).toBeDefined();
    expect(state().dataset.mapNodes).toBe("2");
    expect(state().dataset.mapEdges).toBe("1");
    // The *module* refused, which is a browser with no WebGL2 -- not a
    // renderer that was reached and refused this container (`T-208`). The two
    // are separate states because they have separate answers, and this is the
    // first one: nothing on this canvas will work in this browser, so the
    // companion list opens itself and every count stays true.
    await waitFor(() =>
      expect(document.querySelector("[data-map-renderer-unavailable]")).not.toBeNull(),
    );
    expect(document.querySelector("[data-map-renderer-failed]")).toBeNull();
    expect(
      document.querySelector("[data-map-panel='outline']")?.getAttribute("data-map-panel-open"),
    ).toBe("true");
  });

  it("comes back to the prior focus without leaving the Map", async () => {
    // The last step of D-130's journey, walked through the *real* router: a
    // focus is a navigation within `#/map`, so Back restores the previous
    // selection and the accumulated graph behind it is never rebuilt (D-133,
    // invariant 14). `App` is rendered rather than `MapView` because the claim
    // is about history, and `MemoryRouter` is not the browser's.
    const one = unit("KU-000001", { label: LONG_STATEMENT });
    const two = unit("KU-000002");
    vi.stubGlobal(
      "fetch",
      jsonFetch((url) => {
        if (url.includes("/api/sources")) {
          return { body: { data: [], page: { limit: 200, next_cursor: null, total: 0 } } };
        }
        if (url.includes("/api/entities/")) {
          const id = entityIdOf(url);
          const record = id === KU1 ? one : two;
          return { body: entityBody(record) };
        }
        if (url.includes("/api/graph/neighborhood/")) {
          const id = entityIdOf(url);
          return {
            body: neighbourhoodBody(id, [one, two], [edge(KU1, KU2, "supports")]),
          };
        }
        return { body: graphBody([one, two], [edge(KU1, KU2, "supports")], { total: 2 }) };
      }),
    );
    window.location.hash = `#/map?focus=${KU1}`;
    render(<App />);

    await waitFor(() =>
      expect(document.querySelector("[data-map-quickread]")?.getAttribute("data-map-quickread")).toBe(
        KU1,
      ),
    );
    fireEvent.click(
      document.querySelector(`[data-map-focus-action="${KU2}"]`) as HTMLButtonElement,
    );
    await waitFor(() =>
      expect(document.querySelector("[data-map-quickread]")?.getAttribute("data-map-quickread")).toBe(
        KU2,
      ),
    );

    window.history.back();

    await waitFor(() =>
      expect(document.querySelector("[data-map-quickread]")?.getAttribute("data-map-quickread")).toBe(
        KU1,
      ),
    );
    // Still the same Map: the counts beside the canvas are the ones the walk
    // accumulated before any of this, not a graph fetched again.
    expect(state().dataset.mapNodes).toBe("2");
  });

  it("is linked from the Shell as its own destination", () => {
    vi.stubGlobal(
      "fetch",
      mapFetch(() => ({
        status: 503,
        body: { error: { code: "index_unavailable", message: "not built" } },
      })),
    );
    render(<App />);
    const link = screen.getByRole("link", { name: "Map" });
    expect(link.getAttribute("href")).toBe("#/map");
    expect(screen.getByRole("navigation", { name: "Sections" })).toBeDefined();
  });
});
