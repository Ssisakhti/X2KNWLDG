/**
 * The Map against the **real** server (`T-204`).
 *
 * The hermetic tests prove the view states what the snapshot holds; this one
 * proves the numbers on screen are the server's own. It is the check a stub
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
import type { MapCamera, MapRenderer, MapRendererFactory } from "../map/mapSession";
import { renderApp } from "../test/render";
import { MapView } from "./MapView";

declare const process: { env: Record<string, string | undefined> };

const BASE = process.env.X2KNWLDG_API_BASE;
const client = new ApiClient({ baseUrl: BASE ?? "" });

function fakeRenderer(events: string[]): MapRenderer {
  const camera: MapCamera = {
    zoomIn: () => events.push("zoomIn"),
    zoomOut: () => events.push("zoomOut"),
    reset: () => events.push("reset"),
  };
  return {
    resize: () => events.push("resize"),
    refresh: () => events.push("refresh"),
    kill: () => events.push("kill"),
    getCamera: () => camera,
  };
}

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
    const events: string[] = [];
    const createRenderer: MapRendererFactory = () => fakeRenderer(events);

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
});
