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

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { EntityRef, IndexedRelation } from "../api/contract";
import type { MapCamera, MapRenderer, MapRendererFactory } from "../map/mapSession";
import { App } from "../App";
import { concept, edge, expressesConcept, unit } from "../test/graphRecords";
import { mapStyle } from "../map/mapStyle";
import { jsonFetch, renderApp } from "../test/render";

import { MapView } from "./MapView";

/**
 * The graph responder, plus the source list the filters ask for.
 *
 * `MapFilters` fetches `listSources` to fill its one server-backed control, so
 * the Map route now calls two endpoints and a stub answering every URL with a
 * graph page hands the filter a page envelope where a source array belongs.
 * Routing by path rather than answering everything the same way is also what
 * keeps a test honest about *which* request it is asserting on.
 *
 * The list is empty on purpose: these tests are about the graph, and
 * `MapFilters.test.tsx` is where the source control's own behaviour is
 * checked. An empty list still renders the control, so nothing here depends on
 * a source existing.
 */
function mapFetch(responder: (url: string) => { status?: number; body: unknown }): typeof fetch {
  return jsonFetch((url) =>
    url.includes("/sources")
      ? { body: { data: [], page: { limit: 200, next_cursor: null, total: 0 } } }
      : responder(url),
  );
}

const KU1 = "youtube:pqlWNihgdjI:KU-000001";
const KU2 = "youtube:pqlWNihgdjI:KU-000002";
const C1 = "library:concepts:C-000001";

function graphBody(
  nodes: EntityRef[],
  edges: IndexedRelation[],
  options: { truncated?: boolean; next?: string | null; total?: number | null } = {},
) {
  return {
    api_version: "v1",
    schema_version: "1.0",
    data: { nodes, edges, truncated: options.truncated ?? false },
    page: { limit: 500, next_cursor: options.next ?? null, total: options.total ?? null },
  };
}

/** A renderer that records the lifecycle, and the camera the controls drive. */
function recorder(behaviour: { failOnCreate?: boolean } = {}) {
  const events: string[] = [];
  const factory: MapRendererFactory = () => {
    if (behaviour.failOnCreate === true) {
      events.push("refused");
      throw new Error("WebGL2 is not available in this browser.");
    }
    events.push("create");
    const camera: MapCamera = {
      zoomIn: () => events.push("zoomIn"),
      zoomOut: () => events.push("zoomOut"),
      reset: () => events.push("reset"),
    };
    const renderer: MapRenderer = {
      resize: () => events.push("resize"),
      refresh: () => events.push("refresh"),
      kill: () => events.push("kill"),
      getCamera: () => camera,
    };
    return renderer;
  };
  return { events, factory };
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
    expect(events.filter((name) => name === "create")).toHaveLength(1);
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
    expect(events.filter((name) => name === "create")).toHaveLength(1);

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
    expect(events.filter((name) => name === "create")).toHaveLength(1);
    expect(events).toContain("refresh");
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
    expect(events.filter((name) => name === "create")).toHaveLength(1);

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
    await waitFor(() =>
      expect(document.querySelector("[data-map-renderer-failed]")).not.toBeNull(),
    );
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
