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
import type { MapPoint } from "../map/mapSession";
import { App } from "../App";
import { fakeRenderers } from "../test/mapRenderer";
import { concept, edge, expressesConcept, unit } from "../test/graphRecords";
import { mapStyle } from "../map/mapStyle";
import { jsonFetch, renderApp } from "../test/render";

import { MapView } from "./MapView";

/**
 * The graph responder, plus the three other endpoints this route touches.
 *
 * `MapFilters` fetches `listSources` to fill its one server-backed control,
 * and a selection fetches `getEntity` and `getNeighborhood` (`T-207`) -- so a
 * stub answering every URL with a graph page hands the filter a page envelope
 * where a source array belongs, and hands the neighbourhood a payload with no
 * `center_id`. Routing by path rather than answering everything the same way
 * is also what keeps a test honest about *which* request it is asserting on.
 *
 * The defaults are deliberately the *empty* honest answers -- no sources, a
 * `404` for an entity, an empty neighbourhood -- so a test that cares about
 * one of them says so by overriding it, and a test that does not is not
 * quietly relying on a fixture.
 */
function mapFetch(
  responder: (url: string) => { status?: number; body: unknown },
  extra: (url: string) => { status?: number; body: unknown } | null = () => null,
): typeof fetch {
  return jsonFetch((url) => {
    const override = extra(url);
    if (override !== null) return override;
    if (url.includes("/api/sources")) {
      return { body: { data: [], page: { limit: 200, next_cursor: null, total: 0 } } };
    }
    if (url.includes("/api/entities/")) {
      return {
        status: 404,
        body: { error: { code: "not_found", message: "No entity in the index has that id." } },
      };
    }
    if (url.includes("/api/graph/neighborhood/")) {
      return { body: neighbourhoodBody(entityIdOf(url), []) };
    }
    return responder(url);
  });
}

/** The `entity_id` a path parameter carried, decoded the way the client encoded it. */
function entityIdOf(url: string): string {
  const last = url.split("?")[0]?.split("/").pop() ?? "";
  return decodeURIComponent(last);
}

function entityBody(entity: EntityRef) {
  return { api_version: "v1", schema_version: "1.0", data: entity };
}

function neighbourhoodBody(
  centre: string,
  nodes: EntityRef[],
  edges: IndexedRelation[] = [],
  options: { depth?: number; truncated?: boolean } = {},
) {
  return {
    api_version: "v1",
    schema_version: "1.0",
    data: {
      center_id: centre,
      depth: options.depth ?? 1,
      nodes,
      edges,
      truncated: options.truncated ?? false,
    },
  };
}

const KU1 = "youtube:pqlWNihgdjI:KU-000001";
const KU2 = "youtube:pqlWNihgdjI:KU-000002";
const C1 = "library:concepts:C-000001";

/**
 * A statement longer than any preview budget.
 *
 * So that "the card shortens it visibly" and "Quick Read shows it whole" are
 * two assertions about one record rather than two fixtures.
 */
const LONG_STATEMENT = `${"A statement the transcript actually makes, at length. ".repeat(12)}End.`;

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

/**
 * A renderer that records the lifecycle, and the camera the controls drive.
 *
 * `fakeRenderers` is shared with the Map's other suites (`T-207`), because the
 * renderer boundary now has event and coordinate adapters and three private
 * copies of a fake would be three chances to diverge from it.
 */
function recorder(behaviour: { failOnCreate?: boolean; points?: Record<string, MapPoint> } = {}) {
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
  const STAGE = { width: 900, height: 600 };

  /** A stage with a real size, which jsdom does not otherwise provide. */
  function sizeTheStage(): void {
    vi.spyOn(Element.prototype, "getBoundingClientRect").mockImplementation(function (
      this: Element,
    ) {
      const sized = this.hasAttribute("data-map-stage");
      const width = sized ? STAGE.width : 0;
      const height = sized ? STAGE.height : 0;
      return {
        x: 0,
        y: 0,
        width,
        height,
        top: 0,
        left: 0,
        right: width,
        bottom: height,
        toJSON: () => ({}),
      } as DOMRect;
    });
  }

  /** The graph, the two entities and the two neighbourhoods of one small library. */
  function library(): typeof fetch {
    const one = unit("KU-000001", { label: LONG_STATEMENT });
    const two = unit("KU-000002");
    const three = concept("C-000001");
    return mapFetch(
      () => ({
        body: graphBody([one, two, three], [edge(KU1, KU2, "supports"), expressesConcept(KU1, C1)], {
          total: 3,
        }),
      }),
      (url) => {
        if (url.includes("/api/entities/")) {
          const id = entityIdOf(url);
          const record = [one, two, three].find((entity) => entity.global_id === id);
          return record === undefined
            ? {
                status: 404,
                body: { error: { code: "not_found", message: "No entity has that id." } },
              }
            : { body: entityBody(record) };
        }
        if (url.includes("/api/graph/neighborhood/")) {
          const id = entityIdOf(url);
          if (id === KU1) {
            return {
              body: neighbourhoodBody(
                KU1,
                [one, two, three],
                [edge(KU1, KU2, "supports"), expressesConcept(KU1, C1)],
              ),
            };
          }
          if (id === KU2) {
            return { body: neighbourhoodBody(KU2, [two, one], [edge(KU1, KU2, "supports")]) };
          }
          return { body: neighbourhoodBody(id, []) };
        }
        return null;
      },
    );
  }

  it("focuses the node a click on the canvas names, through the rail's own function", async () => {
    vi.stubGlobal("fetch", library());
    const harness = recorder();
    renderApp(<MapView createRenderer={harness.factory} />, { route: "/map" });
    await drawn();

    // Nothing selected, and the Map says so rather than showing an empty panel.
    expect(screen.getByText("Nothing is focused, so there is no record to read.")).toBeDefined();

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

  it("places the bounded card constellation over the marks, as presentation only", async () => {
    sizeTheStage();
    vi.stubGlobal("fetch", library());
    const harness = recorder({
      points: {
        [KU1]: { x: 450, y: 300 },
        [KU2]: { x: 120, y: 120 },
        [C1]: { x: 780, y: 480 },
      },
    });
    renderApp(<MapView createRenderer={harness.factory} />, { route: `/map?focus=${KU1}` });
    await drawn();

    await waitFor(() => expect(document.querySelector("[data-map-overlay]")).not.toBeNull());
    const overlay = document.querySelector("[data-map-overlay]") as HTMLElement;
    // Presentation over the canvas: no focusable control, and hidden from the
    // accessibility tree, because every card is a second view of a row in the
    // related list.
    expect(overlay.getAttribute("aria-hidden")).toBe("true");
    expect(overlay.querySelectorAll("button, a, input, select")).toHaveLength(0);

    const cards = [...document.querySelectorAll("[data-map-card]")].map((node) => ({
      id: node.getAttribute("data-map-card"),
      primary: node.getAttribute("data-map-card-primary"),
    }));
    expect(cards).toEqual([
      { id: KU1, primary: "true" },
      { id: C1, primary: "false" },
      { id: KU2, primary: "false" },
    ]);
    // The primary card is anchored where the renderer says its mark is.
    const primary = document.querySelector("[data-map-card='youtube:pqlWNihgdjI:KU-000001']");
    expect((primary as HTMLElement).style.left).toBe("450px");
    expect((primary as HTMLElement).style.top).toBe("300px");
    // And the primary card shortens the statement visibly rather than silently.
    expect(primary?.querySelector("[data-truncated]")).not.toBeNull();
  });

  it("draws no card while the camera is moving, and places them again when it stops", async () => {
    // The same rule `hideLabelsOnMove` applies to labels: text that reflows
    // every frame is unreadable, and re-placing per frame would re-render the
    // related list sixty times a second.
    sizeTheStage();
    vi.stubGlobal("fetch", library());
    const harness = recorder({ points: { [KU1]: { x: 450, y: 300 } } });
    renderApp(<MapView createRenderer={harness.factory} />, { route: `/map?focus=${KU1}` });
    await drawn();
    await waitFor(() => expect(document.querySelector("[data-map-overlay]")).not.toBeNull());

    harness.latest()?.fireRender();
    await waitFor(() => expect(document.querySelector("[data-map-overlay]")).toBeNull());
    await waitFor(() => expect(document.querySelector("[data-map-overlay]")).not.toBeNull(), {
      timeout: 2000,
    });
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
    expect(
      screen.getByText("A statement the transcript actually makes, numbered KU-000002."),
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
    expect(harness.events.filter((name) => name === "create")).toHaveLength(1);
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
    await waitFor(() =>
      expect(document.querySelector("[data-map-renderer-failed]")).not.toBeNull(),
    );
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
