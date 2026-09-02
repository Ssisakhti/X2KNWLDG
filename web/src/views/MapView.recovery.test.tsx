/**
 * The three Map defects that a green suite could not see (D-176-D-178).
 *
 * Every one of them is about *when* the route redraws, so none of them shows up
 * in a test that renders once and asserts. They are grouped here because they
 * share a harness — a fake renderer whose refusal can be turned off, and a
 * stage whose size can arrive late.
 *
 * 1. A renderer that refused its container never retried, while two shipped
 *    strings promised "the next layout recovers it".
 * 2. A filter change left the previous question's graph drawn and interactive
 *    while the stage was marked `aria-hidden`.
 * 3. Every continuation page re-framed the camera, discarding the reader's pan
 *    and zoom.
 */

import { fireEvent, waitFor } from "@testing-library/react";
import { act } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { mapStyle } from "../map/mapStyle";
import { fakeRenderers } from "../test/mapRenderer";
import { KU1, KU2, graphBody, library, mapFetch, sizeTheStage } from "../test/mapServer";
import { edge, unit } from "../test/graphRecords";
import { renderApp } from "../test/render";

import { MapView } from "./MapView";

function root(): HTMLElement {
  const found = document.querySelector<HTMLElement>(".map");
  if (found === null) throw new Error("the Map did not render");
  return found;
}

async function counted(): Promise<void> {
  await waitFor(() => expect(document.querySelector("[data-map-nodes]")).not.toBeNull());
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  mapStyle.clear();
});

describe("a renderer that refused its container", () => {
  it("draws on the next layout, which is what the route already promises", async () => {
    vi.stubGlobal("fetch", library());
    // Mutated below: `fakeRenderers` reads the flag on every create, so the
    // first attach refuses and a later one does not — a stage that had no size
    // and then has one.
    const options = { failOnCreate: true };
    const harness = fakeRenderers(options);
    renderApp(<MapView createRenderer={harness.factory} />, { route: "/map" });
    await counted();
    await waitFor(() => expect(root().dataset.mapCanvas).toBe("refused"));

    // The layout arrives.
    options.failOnCreate = false;
    sizeTheStage();
    await act(async () => {
      window.dispatchEvent(new Event("resize"));
    });

    await waitFor(() => expect(root().dataset.mapCanvas).not.toBe("refused"));
    // Invariant 10, whatever the route did to get here: one renderer created
    // and none left over.
    const created = harness.events.filter((name) => name === "create").length;
    const killed = harness.events.filter((name) => name === "kill").length;
    expect(created - killed).toBe(1);
  });

  it("does not retry in a loop at a size that is still unusable", async () => {
    vi.stubGlobal("fetch", library());
    const harness = fakeRenderers({ failOnCreate: true });
    renderApp(<MapView createRenderer={harness.factory} />, { route: "/map" });
    await counted();
    await waitFor(() => expect(root().dataset.mapCanvas).toBe("refused"));

    sizeTheStage();
    for (let attempt = 0; attempt < 4; attempt += 1) {
      await act(async () => {
        window.dispatchEvent(new Event("resize"));
      });
    }
    const refusals = harness.events.filter((name) => name === "refused").length;
    expect(refusals).toBeLessThanOrEqual(2);
    expect(root().dataset.mapCanvas).toBe("refused");
  });
});

describe("a filter change", () => {
  it("retires the previous question's picture rather than leaving it drawn", async () => {
    // The second request never answers, so the new snapshot stays at zero
    // pages — which is exactly the window the defect lived in. Before, the
    // draw effect returned early and the live renderer kept snapshot N-1 on
    // screen: a visible, interactive picture of question A, marked
    // `aria-hidden`, beside a route describing question B.
    const one = unit("KU-000001");
    const two = unit("KU-000002");
    let graphCalls = 0;
    vi.stubGlobal("fetch", ((input: RequestInfo | URL) => {
      const url = typeof input === "string" ? input : input.toString();
      if (url.includes("/api/graph") && !url.includes("neighborhood")) {
        graphCalls += 1;
        if (graphCalls > 1) return new Promise<Response>(() => {});
        return Promise.resolve(
          new Response(
            JSON.stringify(graphBody([one, two], [edge(KU1, KU2, "supports")])),
            { status: 200, headers: { "Content-Type": "application/json" } },
          ),
        );
      }
      return Promise.resolve(
        new Response(JSON.stringify({ data: [], page: { limit: 200, next_cursor: null, total: 0 } }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      );
    }) as typeof fetch);
    sizeTheStage();
    const harness = fakeRenderers();
    renderApp(<MapView createRenderer={harness.factory} />, { route: "/map" });
    await counted();
    await waitFor(() => expect(harness.all.length).toBe(1));
    const drawnBefore = root().dataset.mapCanvas;
    expect(drawnBefore).not.toBe("refused");

    const filter = document.querySelector<HTMLSelectElement>(
      "[data-map-filter='provenance_class']",
    );
    expect(filter).not.toBeNull();
    await act(async () => {
      fireEvent.change(filter as HTMLSelectElement, { target: { value: "source" } });
    });
    await waitFor(() => expect(graphCalls).toBe(2));

    await waitFor(() => {
      const created = harness.events.filter((name) => name === "create").length;
      const killed = harness.events.filter((name) => name === "kill").length;
      // Nothing is holding a renderer while the new question has no page yet.
      expect(created - killed).toBe(0);
    });
    expect(root().dataset.mapCanvas).not.toBe(drawnBefore);
  });
});

describe("a continuation page", () => {
  it("does not re-frame the camera under a reader who has zoomed in", async () => {
    const one = unit("KU-000001");
    const two = unit("KU-000002");
    const three = unit("KU-000003");
    // Two pages, so `Load more` exists and merging it bumps `pages`.
    let page = 0;
    vi.stubGlobal(
      "fetch",
      mapFetch((url) => {
        if (!url.includes("/api/graph") || url.includes("neighborhood")) {
          return { body: { data: [], page: { limit: 200, next_cursor: null, total: 0 } } };
        }
        page += 1;
        return page === 1
          ? {
              body: graphBody([one, two], [edge(KU1, KU2, "supports")], {
                next: "cursor-2",
              }),
            }
          : { body: graphBody([three], [], { next: null }) };
      }),
    );
    sizeTheStage();
    // A framing gesture needs display positions; without them `frame` has
    // nothing to aim at and never reaches the camera.
    const harness = fakeRenderers({
      display: { [KU1]: { x: 10, y: 10 }, [KU2]: { x: 20, y: 20 } },
    });
    renderApp(<MapView createRenderer={harness.factory} />, {
      route: `/map?focus=${encodeURIComponent(KU1)}`,
    });
    await counted();
    await waitFor(() => expect(harness.all.length).toBe(1));
    await waitFor(() =>
      expect(harness.events.filter((name) => name === "animate").length).toBeGreaterThan(0),
    );
    const framedOnce = harness.events.filter((name) => name === "animate").length;

    const more = document.querySelector<HTMLButtonElement>("[data-map-load-more]");
    expect(more).not.toBeNull();
    await act(async () => {
      fireEvent.click(more as HTMLButtonElement);
    });
    await waitFor(() => expect(page).toBe(2));

    // Framed once per selection, not once per page.
    expect(harness.events.filter((name) => name === "animate").length).toBe(framedOnce);
  });
});
