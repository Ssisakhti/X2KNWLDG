/**
 * D-203 — a single-page navigation moved focus nowhere and announced nothing.
 *
 * Follow a source card's link and the Reader mounts, the link unmounts, focus
 * falls to `<body>`, and a screen reader says nothing at all. The next `Tab`
 * then restarts at the skip link, so returning to where the reader was means
 * tabbing through the brand, both nav links, the language select and the whole
 * search form. `withFocusRescue` covers seven buttons and no links.
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App } from "../App";

function serve() {
  return vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    const body = url.includes("/api/status")
      ? {
          api_version: "v1",
          schema_version: "1.0",
          data: {
            index: { state: "ready", built_at: null },
            counts: { sources: 0, artifacts: 0, entities: 0, relations: 0 },
            sources_by_status: {},
            adapters: [],
          },
        }
      : {
          api_version: "v1",
          schema_version: "1.0",
          data: [],
          page: { limit: 50, next_cursor: null, total: 0 },
        };
    return new Response(JSON.stringify(body), {
      status: 200,
      headers: { "content-type": "application/json" },
    });
  });
}

afterEach(() => vi.unstubAllGlobals());

describe("navigating between routes", () => {
  it("does not take focus on the first render", async () => {
    vi.stubGlobal("fetch", serve());
    window.location.hash = "#/";
    render(<App />);
    await waitFor(() => expect(screen.getByRole("main")).toBeTruthy());
    // A page that steals focus on load has taken the reader's place in it away
    // before they had one.
    expect(document.activeElement).toBe(document.body);
  });

  it("moves focus into the new view, so the next Tab starts there", async () => {
    vi.stubGlobal("fetch", serve());
    window.location.hash = "#/";
    render(<App />);
    await waitFor(() => expect(screen.getByRole("main")).toBeTruthy());

    fireEvent.click(screen.getByRole("link", { name: /map/i }));

    const main = screen.getByRole("main");
    await waitFor(() => expect(document.activeElement).toBe(main));
    // It is the region the skip link already targets, reached automatically
    // rather than through a second idea of where a route begins.
    expect(main.id).toBe("content");
    expect(main.getAttribute("tabindex")).toBe("-1");
  });

  it("leaves focus alone for a selection made inside a route", async () => {
    // `#/map?focus=...` is not a navigation to a reader, and moving focus for
    // one would take the keyboard out of the search rail on every result.
    vi.stubGlobal("fetch", serve());
    window.location.hash = "#/map";
    render(<App />);
    await waitFor(() => expect(screen.getByRole("main")).toBeTruthy());

    const before = document.activeElement;
    window.location.hash = "#/map?focus=youtube:v:KU-000001";
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(document.activeElement).toBe(before);
  });
});
