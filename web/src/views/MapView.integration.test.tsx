/**
 * The Map against the **real** server (`T-204`).
 *
 * The hermetic tests prove the view states what the snapshot holds; these
 * prove the numbers on screen are the server's own -- the counts beside the
 * canvas (`T-204`) and the related list beside a real selection (`T-207`). It is the check a stub
 * cannot give: the counts here come from `/api/graph` as it is actually
 * served, so a view that quietly recomputed a total, dropped a straddling
 * edge, or called one page the graph would disagree with the payload beside it.
 *
 * The renderer is still a fake -- jsdom has no WebGL, and drawing is not what
 * this file is about. Sigma over this same graph is walked in a browser
 * (`T-202` recorded that walk; `T-209` repeats it for the Map).
 *
 * Skipped unless `X2KNWLDG_API_BASE` names a running server:
 *
 *     npm run dev:api                                  # terminal one
 *     X2KNWLDG_API_BASE=http://127.0.0.1:8931 npm test # terminal two
 */

import { screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiClient } from "../api/client";
import { fakeRenderers } from "../test/mapRenderer";
import { renderApp } from "../test/render";
import { MapView } from "./MapView";

declare const process: { env: Record<string, string | undefined> };

const BASE = process.env.X2KNWLDG_API_BASE;
const client = new ApiClient({ baseUrl: BASE ?? "" });

describe.skipIf(BASE === undefined || BASE === "")("the Map over the served graph", () => {
  beforeEach(() => {
    // Only the origin is stubbed. The application asks for `/api/...` on its
    // own origin, which the Vite proxy and the production server both provide;
    // jsdom has none, so relative paths resolve against the server under test.
    const real = globalThis.fetch;
    vi.stubGlobal("fetch", ((input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input.toString();
      return real(url.startsWith("/api") ? `${BASE}${url}` : url, init);
    }) as typeof fetch);
  });

  afterEach(() => vi.unstubAllGlobals());

  it("draws the graph the server returns, and counts it the way the server does", async () => {
    const whole = await client.call("getGraph", { query: { limit: 500 } });
    const { factory: createRenderer, events } = fakeRenderers();

    const view = renderApp(<MapView createRenderer={createRenderer} />);

    await waitFor(() => expect(document.querySelector("[data-map-nodes]")).not.toBeNull(), {
      timeout: 5000,
    });
    const panel = document.querySelector<HTMLElement>("[data-map-nodes]");
    expect(panel?.dataset.mapNodes).toBe(String(whole.data.nodes.length));
    expect(panel?.dataset.mapEdges).toBe(String(whole.data.edges.length));
    // Nothing may be waiting for an endpoint once the whole graph is in: an
    // edge held at the end of a walk is a relation the Map is not drawing.
    expect(panel?.dataset.mapHeld).toBe("0");
    expect(panel?.dataset.mapTruncated).toBe(String(whole.data.truncated));

    // The fixtures fit one page at the contract maximum, so the Map has the
    // whole graph and says so. If this fires, the fixtures have outgrown a
    // single page and the assertion above about `held` is measuring a
    // different situation -- not a failure of the view.
    expect(whole.page.next_cursor).toBeNull();
    expect(panel?.dataset.mapComplete).toBe("true");
    expect(screen.getByText("This is the whole graph these filters describe.")).toBeDefined();
    expect(document.querySelector("[data-map-load-more]")).toBeNull();
    expect(events.filter((name) => name === "kill")).toHaveLength(0);

    view.unmount();
    expect(events.filter((name) => name === "kill")).toHaveLength(1);
  });

  it("lists the neighbours the server returned for a real selection, and reads it whole", async () => {
    // `T-207` end to end, against the served index: the row count is the
    // server's own node count, and Quick Read shows the server's own label
    // without shortening it. A view that cut the statement, or that listed
    // only the neighbours its cards could place, would disagree with the
    // payload it is standing next to.
    const graph = await client.call("getGraph", { query: { limit: 500 } });
    const degree = new Map<string, number>();
    for (const relation of graph.data.edges) {
      for (const endpoint of [relation.from_id, relation.to_id]) {
        degree.set(endpoint, (degree.get(endpoint) ?? 0) + 1);
      }
    }
    const [busiest] = [...degree.entries()].sort(
      (left, right) => right[1] - left[1] || (left[0] < right[0] ? -1 : 1),
    )[0] ?? [null];
    expect(busiest).not.toBeNull();
    const entityId = busiest as string;

    const [entity, hood] = await Promise.all([
      client.call("getEntity", { params: { entity_id: entityId } }),
      client.call("getNeighborhood", { params: { entity_id: entityId }, query: { depth: 1 } }),
    ]);
    const neighbours = hood.data.nodes.filter((node) => node.global_id !== entityId).length;
    expect(neighbours).toBeGreaterThan(1);

    const { factory: createRenderer } = fakeRenderers();
    renderApp(<MapView createRenderer={createRenderer} />, {
      route: `/map?focus=${entityId}`,
    });

    await waitFor(
      () =>
        expect(document.querySelectorAll("[data-map-related-entity]")).toHaveLength(neighbours),
      { timeout: 5000 },
    );
    expect(
      document.querySelector("[data-map-related]")?.getAttribute("data-map-related"),
    ).toBe(String(neighbours));
    expect(document.querySelector("[data-map-statement='complete']")?.textContent).toBe(
      entity.data.label,
    );
  });
});
