/**
 * One route, two Maps (`T-256`).
 *
 * The dispatch is three lines and this suite is longer than it, because the
 * thing being asserted is not the branch but **D-249**: the Knowledge Map is
 * reached through the mode switch without having been edited for it, and a URL
 * that says nothing about a mode is still the Map it has always been. A
 * regression here would not look like a bug — it would look like the Knowledge
 * Map quietly becoming a Source Map for readers with an old link.
 */

import { describe, expect, it, vi } from "vitest";
import { waitFor } from "@testing-library/react";

import { jsonFetch, renderApp } from "../test/render";
import { graphPayload, graphResponse, sourceNode, PASS } from "../test/sourceRecords";
import { sizeTheStage } from "../test/mapServer";
import { MapRoute } from "./MapRoute";

/**
 * A server that answers *both* Maps.
 *
 * Deliberately not two servers: the assertion is which request the route makes,
 * and a stub that could only answer one of them would pass by refusing the
 * other rather than by the route choosing.
 */
function bothMaps(): { fetch: typeof fetch; asked: string[] } {
  const asked: string[] = [];
  const stub = jsonFetch((url) => {
    asked.push(url);
    if (url.includes("/api/source-graph")) {
      return { body: graphResponse(graphPayload([sourceNode(PASS)], [])) };
    }
    if (url.includes("/api/graph")) {
      return {
        api_version: "v1",
        body: {
          api_version: "v1",
          schema_version: "1.0",
          data: { nodes: [], edges: [], truncated: false },
          page: { limit: 500, next_cursor: null, total: 0 },
        },
      };
    }
    if (url.includes("/api/sources")) {
      return { body: { data: [], page: { limit: 200, next_cursor: null, total: 0 } } };
    }
    return { body: { data: [], page: { limit: 25, next_cursor: null, total: 0 } } };
  });
  return { fetch: stub, asked };
}

describe("the /map route", () => {
  it("is the Knowledge Map when the URL says nothing about a mode", async () => {
    const server = bothMaps();
    vi.stubGlobal("fetch", server.fetch);
    sizeTheStage();
    renderApp(<MapRoute />, { route: "/map" });

    await waitFor(() => expect(server.asked.length).toBeGreaterThan(0));
    expect(document.querySelector("[data-map-of='sources']")).toBeNull();
    // The request it made is the Knowledge Map's, not the Source Map's.
    expect(server.asked.some((url) => url.includes("/api/graph"))).toBe(true);
    expect(server.asked.some((url) => url.includes("/api/source-graph"))).toBe(false);
  });

  it("is still the Knowledge Map when the mode is one it does not know", async () => {
    // An unreadable value is ignored rather than repaired, which for a *mode*
    // means the reader stays where they were.
    const server = bothMaps();
    vi.stubGlobal("fetch", server.fetch);
    sizeTheStage();
    renderApp(<MapRoute />, { route: "/map?of=source" });

    await waitFor(() => expect(server.asked.length).toBeGreaterThan(0));
    expect(server.asked.some((url) => url.includes("/api/source-graph"))).toBe(false);
  });

  it("is the Source Map at `of=sources`", async () => {
    const server = bothMaps();
    vi.stubGlobal("fetch", server.fetch);
    sizeTheStage();
    renderApp(<MapRoute />, { route: "/map?of=sources" });

    await waitFor(() =>
      expect(document.querySelector("[data-map-of='sources']")).not.toBeNull(),
    );
    expect(server.asked.some((url) => url.includes("/api/source-graph"))).toBe(true);
  });

  it("keeps the Knowledge Map's filters addressable beside the mode", async () => {
    // The mode is a fifth parameter, not a replacement for the other four: an
    // old link with filters still filters, and a new one may carry both.
    const server = bothMaps();
    vi.stubGlobal("fetch", server.fetch);
    sizeTheStage();
    renderApp(<MapRoute />, { route: "/map?source_id=youtube:abc&provenance_class=derived" });

    await waitFor(() => expect(server.asked.length).toBeGreaterThan(0));
    const graphCall = server.asked.find((url) => url.includes("/api/graph"));
    expect(graphCall).toContain("source_id=youtube%3Aabc");
    expect(graphCall).toContain("provenance_class=derived");
  });
});
