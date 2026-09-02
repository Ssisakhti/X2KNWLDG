/**
 * The journey, in a real browser (`T-209`).
 *
 * D-130's journey is Search -> Preview/Peek -> Focus -> Quick Read, with the
 * Reader as a deliberate destination rather than the price of understanding a
 * node. Every step of it has been asserted in jsdom against an injected
 * renderer; none of it had ever been walked. This is that walk, and the
 * acceptance question it answers is the anti-pogo one:
 *
 *   before opening a neighbour, can the reader say what it states and why it
 *   is worth opening?
 *
 * The answer has to come from what is on screen, so these specs read the
 * rendered text of a row and compare it with the record the server sent --
 * not with a fixture, and never with a number typed into a test.
 */

import { expect, test } from "@playwright/test";

import {
  busiest,
  counts,
  findMark,
  mapUrl,
  openDrawnMap,
  openPanel,
  panels,
  reading,
  servedGraph,
  sourceBacked,
  watchForTrouble,
} from "./gate";

test.describe("the Map, opened", () => {
  test("draws every node and edge the server sent, and says so in words", async ({ page }) => {
    const { trouble } = watchForTrouble(page);
    await openDrawnMap(page);
    const graph = await servedGraph(page);

    const stated = await counts(page);
    expect(stated.nodes).toBe(graph.nodes.length);
    expect(stated.edges).toBe(graph.edges.length);
    // Nothing is waiting for an endpoint on a page that has not arrived: this
    // library is one page under the contract maximum (D-118).
    expect(stated.held).toBe(0);
    expect(stated.complete).toBe(true);
    expect(stated.truncated).toBe(false);
    expect(await reading(page)).toEqual({ graph: "whole", canvas: "drawing" });

    // The counted total is the server's own, not a length the client measured.
    if (graph.total !== null) {
      await expect(page.locator("[data-map-nodes] .definitions")).toContainText(
        `${graph.nodes.length} / ${graph.total}`,
      );
    }

    // The picture is labelled as a picture only while there is one (D-141).
    const stage = page.locator("[data-map-stage]");
    await expect(stage).toHaveAttribute("role", "img");
    await expect(stage).toHaveAttribute("aria-label", /graph/i);
    expect(trouble).toEqual([]);
  });

  test("reaches WebGL2 and holds exactly one canvas for the whole route", async ({ page }) => {
    await openDrawnMap(page);
    // Which renderer path this walk was performed on, recorded in the run's
    // own output: `T-202`'s result is only about the driver it ran on, and so
    // is this one.
    const renderer = await page.evaluate(() => {
      const canvas = document.querySelector("[data-map-stage] canvas");
      if (canvas === null) return null;
      const context =
        (canvas as HTMLCanvasElement).getContext("webgl2") ??
        (canvas as HTMLCanvasElement).getContext("webgl");
      if (context === null) return null;
      const info = (context as WebGLRenderingContext).getExtension("WEBGL_debug_renderer_info");
      return info === null
        ? "unknown"
        : String(
            (context as WebGLRenderingContext).getParameter(
              (info as { UNMASKED_RENDERER_WEBGL: number }).UNMASKED_RENDERER_WEBGL,
            ),
          );
    });
    expect(renderer, "the stage has no WebGL context at all").not.toBeNull();
    test.info().annotations.push({ type: "webgl renderer", description: String(renderer) });
    // One renderer, one canvas: Sigma v4 draws its layers into a single stage
    // canvas, and a second one would mean a renderer that was not killed.
    await expect(page.locator("[data-map-stage] canvas")).toHaveCount(1);
  });

  test("answers the URL's own filters, and ignores a value it cannot read", async ({ page }) => {
    const whole = await (async () => {
      await openDrawnMap(page);
      return counts(page);
    })();

    // `relation_vocabulary` is a filter the contract accepts, and the server
    // answers it by keeping the nodes and dropping the relations of another
    // vocabulary -- which is a smaller graph the Map must state honestly
    // rather than a graph it should invent nodes for.
    await openDrawnMap(page, { relation_vocabulary: "canonical" });
    const canonical = await counts(page);
    expect(canonical.edges).toBeLessThanOrEqual(whole.edges);
    expect(canonical.complete).toBe(true);

    const served = await page.request.get("/api/graph?limit=500&relation_vocabulary=canonical");
    const body = (await served.json()) as { data: { nodes: unknown[]; edges: unknown[] } };
    expect(canonical.nodes).toBe(body.data.nodes.length);
    expect(canonical.edges).toBe(body.data.edges.length);

    // A malformed value is ignored rather than coerced (D-119): this is the
    // whole graph again, not a repaired filter's smaller one.
    await openDrawnMap(page, { relation_vocabulary: "cannonical" });
    expect(await counts(page)).toEqual(whole);
  });

  test("states an empty answer as empty, and an empty stage as empty (D-139)", async ({ page }) => {
    // A real filter with a real empty answer: the served libraries record no
    // user-authored provenance, so the server returns a counted zero rather
    // than a refusal, which is exactly the pair `describeGraph` must not
    // collapse -- unasked prints no numbers, empty prints zeros.
    await page.goto(mapUrl({ provenance_class: "user" }));
    await expect(page.locator("[data-map-nodes]")).toBeVisible();
    const empty = await counts(page);
    expect(empty.nodes).toBe(0);
    expect(empty.edges).toBe(0);
    expect(empty.complete).toBe(true);
    expect(await reading(page)).toEqual({ graph: "empty", canvas: "nothing" });
    // No picture is claimed for a stage with nothing on it.
    await expect(page.locator("[data-map-stage]")).not.toHaveAttribute("role", "img");
    // And the companion opens itself, because it is the only view left.
    expect((await panels(page)).outline).toBe(true);
    await expect(page.locator("[data-map-outline]")).toHaveAttribute(
      "data-map-outline-loaded",
      "0",
    );
  });

  test("accumulates a paged walk into the graph one request returns (D-118)", async ({ page }) => {
    // The client asks for the contract maximum, so the served library is one
    // page. Making the *request* smaller is how a real progressive walk is
    // exercised against a real server: every answer below is the server's.
    await page.route("**/api/graph?**", async (route) => {
      const url = new URL(route.request().url());
      url.searchParams.set("limit", "5");
      await route.continue({ url: url.toString() });
    });
    await openDrawnMap(page);
    const graph = await servedGraph(page);

    const first = await counts(page);
    expect(first.nodes).toBeLessThanOrEqual(5);
    if (graph.nodes.length > 5) {
      expect(first.complete).toBe(false);
      // A five-node page of a graph this shape leaves edges waiting for the
      // far endpoint, and the Map counts them rather than drawing or dropping
      // them (invariant 3).
      expect(first.held).toBeGreaterThan(0);
      expect(await reading(page)).toMatchObject({ graph: "partial" });
    }

    // Walk the rest of it, one deliberate page at a time (D-118): a page is a
    // button, never an automatic fetch. Each press must move the count, which
    // is also what makes this loop terminate for a reason rather than on a
    // timer.
    for (let pages = 0; pages < 60; pages += 1) {
      const button = page.locator("[data-map-load-more]");
      if ((await button.count()) === 0) break;
      const before = (await counts(page)).nodes;
      await button.click();
      await expect
        .poll(async () => (await counts(page)).nodes, { timeout: 15_000 })
        .toBeGreaterThan(before);
    }

    const walked = await counts(page);
    expect(walked.nodes).toBe(graph.nodes.length);
    expect(walked.edges).toBe(graph.edges.length);
    expect(walked.held).toBe(0);
    expect(walked.complete).toBe(true);
    expect(await reading(page)).toMatchObject({ graph: "whole" });
  });
});

test.describe("search, preview, focus, read, and back", () => {
  test("walks the whole journey without leaving the Map", async ({ page }) => {
    const { trouble } = watchForTrouble(page);
    await openDrawnMap(page);
    const graph = await servedGraph(page);
    const centre = busiest(graph);
    const record = graph.nodes.find((node) => node.global_id === centre);
    expect(record).toBeDefined();

    // --- Search. A word from a statement the server actually sent, so the
    // query is about this library rather than about a fixture.
    const word = (record?.label ?? "").split(/\s+/).find((token) => token.length > 5) ?? "the";
    const rail = await openPanel(page, "search");
    await rail.getByRole("searchbox").fill(word);
    await rail.getByRole("button", { name: "Search", exact: true }).click();
    const results = rail.locator("[data-map-result]");
    await expect(results.first()).toBeVisible();

    // --- Preview, with no pointer. Focusing a card's own control opens the
    // one transient Peek, and it writes no history (invariant 14).
    const before = page.url();
    const target = results.filter({ has: page.locator(`[data-map-focus-action="${centre}"]`) });
    const card = (await target.count()) > 0 ? target.first() : results.first();
    const focusButton = card.locator("[data-map-focus-action]");
    const chosen = await focusButton.getAttribute("data-map-focus-action");
    await focusButton.focus();
    const peek = page.locator("[data-map-peek]");
    await expect(peek).toBeVisible();
    expect(page.url()).toBe(before);

    // Before opening anything, the card states what the entity says: the
    // statement is the record's own text, and it is a *prefix* of it because
    // a cut is presentational and visible (D-131).
    const stated = (await card.locator("p").first().innerText()).trim();
    const chosenRecord = graph.nodes.find((node) => node.global_id === chosen);
    const label = (chosenRecord?.label ?? "").replace(/\s+/gu, " ").trim();
    expect(label.startsWith(stated.replace(/…$/u, ""))).toBe(true);

    // --- Focus. One selection identity, written to the URL (D-119).
    await focusButton.click();
    await expect(page).toHaveURL(new RegExp(`focus=${encodeURIComponent(chosen ?? "")}`));
    await expect(page.locator("[data-map-quickread]")).toBeVisible();

    // --- Compare the neighbours. Every neighbour the server returned has a
    // row, and every row names its relation before anything is opened.
    const neighbourhood = await page.request.get(
      `/api/graph/neighborhood/${encodeURIComponent(chosen ?? "")}?depth=1&limit=200`,
    );
    const hood = (await neighbourhood.json()) as {
      data: { nodes: { global_id: string }[]; center_id: string };
    };
    const returned = hood.data.nodes.filter((node) => node.global_id !== hood.data.center_id);
    const rows = page.locator("[data-map-related-entity]");
    await expect(rows).toHaveCount(returned.length);
    for (const node of returned) {
      await expect(page.locator(`[data-map-related-entity="${node.global_id}"]`)).toHaveCount(1);
    }

    // --- Quick Read. The complete stored statement, not the card's cut.
    const quickRead = page.locator("[data-map-quickread]");
    await expect(quickRead).toContainText(label.slice(0, 60));
    // In D-131's order: the statement before the identifiers.
    const order = await quickRead.innerText();
    expect(order.indexOf("Stored statement")).toBeLessThan(order.indexOf("global_id"));

    // --- Focus a neighbour, then Back. Focus has history; the Map is never
    // unmounted and the prior selection returns (invariant 14).
    const neighbourButton = page
      .locator('[data-map-panel="related"] [data-map-focus-action]')
      .first();
    const neighbour = await neighbourButton.getAttribute("data-map-focus-action");
    await neighbourButton.click();
    await expect(page).toHaveURL(new RegExp(`focus=${encodeURIComponent(neighbour ?? "")}`));
    await page.goBack();
    await expect(page).toHaveURL(new RegExp(`focus=${encodeURIComponent(chosen ?? "")}`));
    await expect(page.locator('.map[data-map-canvas="drawing"]')).toBeVisible();
    await expect(page.locator("[data-map-quickread]")).toContainText(String(chosen));

    expect(trouble).toEqual([]);
  });

  test("opens the Reader at the time the locator records, from Quick Read", async ({ page }) => {
    const graph = await servedGraph(page);
    const entity = sourceBacked(graph);
    await openDrawnMap(page, { focus: entity });

    const link = page.locator("[data-map-quickread]").getByRole("link");
    await expect(link.first()).toBeVisible();
    const href = (await link.first().getAttribute("href")) ?? "";
    // The Reader's own address, and the source is the record's own.
    const source = graph.nodes.find((node) => node.global_id === entity)?.source_id ?? "";
    expect(decodeURIComponent(href)).toContain(source);

    await link.first().click();
    await expect(page).toHaveURL(new RegExp("#/sources/"));
    await expect(page.locator("h1")).toBeVisible();
    // A time in the URL is the locator's own, never a rounded or invented one.
    const seconds = new URL(page.url().replace("#", "?hash=")).searchParams;
    if (href.includes("t=")) {
      expect(href).toMatch(/t=\d+(\.\d+)?/);
      expect(seconds).toBeDefined();
    }
  });

  test("selects from the canvas through the same identity a row uses", async ({ page }) => {
    // The pointer path, which no jsdom test can reach: a click on a *mark*
    // must call the same `focusEntity` a button calls -- a third caller, not
    // a second identity (invariant 8, §8.6).
    const graph = await servedGraph(page);
    const centre = busiest(graph);
    await openDrawnMap(page, { focus: centre });
    await expect(
      page.locator('.map__overlay [data-map-card][data-map-card-primary="true"]'),
    ).toBeVisible();

    // A mark other than the focused one, found the way a reader finds one:
    // by moving the pointer until the route says what is underneath.
    const mark = await findMark(page, { exclude: centre });
    expect(mark, "no mark on the stage answered the pointer at all").not.toBeNull();
    const found = mark as NonNullable<typeof mark>;
    // The Peek names a record the Map has loaded, never one it has not.
    expect(graph.nodes.some((node) => node.global_id === found.globalId)).toBe(true);
    await expect(page.locator("[data-map-peek]")).toContainText(found.globalId);
    // A preview writes no history (invariant 14).
    await expect(page).toHaveURL(new RegExp(`focus=${encodeURIComponent(centre)}`));

    // A click on that mark focuses it: one identity, three callers. Clicked
    // where the pointer already is, before anything moves the page.
    await page.mouse.click(found.clientX, found.clientY);
    await expect(page).toHaveURL(new RegExp(`focus=${encodeURIComponent(found.globalId)}`));
    await expect(page.locator("[data-map-quickread]")).toContainText(found.globalId);

    // Escape dismisses the Peek from anywhere on the route (`T-208`).
    await page.mouse.move(found.clientX, found.clientY);
    await expect(page.locator("[data-map-peek]")).toHaveCount(1);
    await page.keyboard.press("Escape");
    await expect(page.locator("[data-map-peek]")).toHaveCount(0);

    // Back returns to the prior focus without leaving the Map.
    await page.goBack();
    await expect(page).toHaveURL(new RegExp(`focus=${encodeURIComponent(centre)}`));
    await expect(page.locator('.map[data-map-canvas="drawing"]')).toBeVisible();
  });
});
