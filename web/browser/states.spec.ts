/**
 * The Map's seven honest states, in a real browser (`T-209`).
 *
 * `T-208` reduced five ad-hoc conditions to two total functions and named the
 * pairs they must not collapse (D-139-D-141): unasked is not empty, partial is
 * not whole, refused is not empty, undrawn is not absent, and a browser with
 * no WebGL2 is not a renderer that refused *this container*. All of it was
 * asserted in jsdom, where the renderer is a fake that throws on command and
 * every element measures zero -- so the two states that are *about the
 * renderer* had never been produced by a renderer.
 *
 * Here they are produced by the real one:
 *
 * - `unavailable` by removing `WebGL2RenderingContext` before the bundle
 *   loads, which is what a browser without it looks like from the module's
 *   point of view -- `sigma` reads that global while its module body evaluates
 *   (D-127), so the import rejects and the phase is `module`.
 * - `refused` by giving the stage no height, which is what
 *   `allowInvalidContainer: false` is for.
 *
 * And what `T-209` measured about the second one is the reason the CSS floor
 * on the stage matters, but not for the reason D-144 assumed: Sigma refuses a
 * container only when a dimension is *exactly* zero. A stage two pixels high
 * is accepted, drawn into, and reported as a picture. So the floor is not a
 * way of avoiding a stated refusal -- it is what keeps a small window from
 * producing an unreadable two-pixel graph that the route calls drawn (D-145).
 */

import { expect, test, type Page } from "@playwright/test";

import { counts, mapUrl, openPanel, panels, reading, servedGraph } from "./gate";

/**
 * Serve the document with one extra stylesheet, before the bundle runs.
 *
 * The stylesheet has to be in the document rather than added afterwards: the
 * renderer is created as soon as the first page of the graph arrives, so a
 * rule injected after load would arrive after the decision it is meant to
 * change.
 */
async function withStageStyle(page: Page, css: string): Promise<void> {
  await page.route("**/*", async (route) => {
    if (route.request().resourceType() !== "document") return route.continue();
    const response = await route.fetch();
    const body = (await response.text()).replace("</head>", `<style>${css}</style></head>`);
    await route.fulfill({
      response,
      body,
      headers: { ...response.headers(), "content-type": "text/html" },
    });
  });
}

test.describe("the states of the graph", () => {
  test("prints no number for a question that has not been answered (D-139)", async ({ page }) => {
    // Held in flight on purpose: `unasked`/`loading` is the state where a
    // count would be an answer to a question nobody has answered yet, which
    // is D-068's shape all over again.
    let release: () => void = () => {};
    const held = new Promise<void>((resolve) => {
      release = resolve;
    });
    await page.route("**/api/graph?**", async (route) => {
      await held;
      await route.continue();
    });

    await page.goto(mapUrl());
    await expect(page.locator(".map")).toBeVisible();
    expect((await reading(page)).graph).toMatch(/^(unasked|loading)$/);
    // No counts panel at all -- not a panel of zeros.
    await expect(page.locator("[data-map-nodes]")).toHaveCount(0);
    await expect(page.locator(".map")).toContainText(/Reading a page|has been asked/i);
    // No picture, and no claim of one.
    await expect(page.locator("[data-map-stage]")).not.toHaveAttribute("role", "img");
    // And no camera, because there is no renderer to drive (finding 4).
    await expect(page.getByRole("button", { name: "Zoom in" })).toBeDisabled();

    release();
    await expect(page.locator('.map[data-map-canvas="drawing"]')).toBeVisible();
    expect(await reading(page)).toEqual({ graph: "whole", canvas: "drawing" });
  });

  test("keeps the pages that arrived countable when a later one is refused", async ({ page }) => {
    // Refused is not empty (D-139): the first page is real, still drawn, and
    // still true -- but it is not an answer to the request that failed, and
    // the route has to say so out loud rather than leave a count under an
    // error panel.
    let calls = 0;
    await page.route("**/api/graph?**", async (route) => {
      calls += 1;
      if (calls === 1) {
        const url = new URL(route.request().url());
        url.searchParams.set("limit", "3");
        return route.continue({ url: url.toString() });
      }
      return route.fulfill({
        status: 503,
        contentType: "application/json",
        body: JSON.stringify({
          error: { code: "index_unavailable", message: "The index is not available." },
        }),
      });
    });

    await page.goto(mapUrl());
    await expect(page.locator('.map[data-map-canvas="drawing"]')).toBeVisible();
    const first = await counts(page);
    expect(first.nodes).toBeGreaterThan(0);

    await page.locator("[data-map-load-more]").click();
    await expect(page.locator(".map")).toHaveAttribute("data-map-reading", "refused");
    // The error is stated as an error, the counts survive, and they are
    // marked as not being an answer to what failed.
    await expect(page.getByRole("alert").first()).toBeVisible();
    await expect(page.locator("[data-map-reading-stale]")).toBeVisible();
    expect(await counts(page)).toEqual(first);
  });
});

test.describe("the states of the picture", () => {
  test("says a browser cannot draw at all, and stays usable without it", async ({ page }) => {
    // What a browser with no WebGL2 looks like to the module that needs it.
    await page.addInitScript(() => {
      // @ts-expect-error -- removing a global is the whole point.
      delete window.WebGL2RenderingContext;
    });
    await page.goto(mapUrl());
    await expect(page.locator("[data-map-renderer-unavailable]")).toBeVisible();
    const graph = await servedGraph(page);

    // The graph is whole and the picture is impossible: two different
    // questions with two different answers (D-141).
    expect(await reading(page)).toEqual({ graph: "whole", canvas: "unavailable" });
    expect((await counts(page)).nodes).toBe(graph.nodes.length);
    // Not the *other* renderer state: this one is permanent for this browser.
    await expect(page.locator("[data-map-renderer-failed]")).toHaveCount(0);
    await expect(page.locator("[data-map-stage]")).toHaveAttribute("aria-hidden", "true");
    await expect(page.locator("[data-map-stage]")).not.toHaveAttribute("role", "img");

    // The companion opens itself, because it is now the only view of the
    // graph (D-142, D-143) -- and the whole journey runs from it.
    expect((await panels(page)).outline).toBe(true);
    const outline = page.locator("[data-map-outline]");
    await expect(outline).toHaveAttribute("data-map-outline-loaded", String(graph.nodes.length));
    const rows = outline.locator("[data-map-result]");
    expect(await rows.count()).toBeGreaterThan(0);

    const focus = outline.locator("[data-map-focus-action]").first();
    const chosen = await focus.getAttribute("data-map-focus-action");
    await focus.click();
    await expect(page).toHaveURL(new RegExp(`focus=${encodeURIComponent(chosen ?? "")}`));
    await expect(page.locator("[data-map-quickread]")).toContainText("Stored statement");
    await expect(page.locator("[data-map-panel='related']")).toBeVisible();
  });

  test("says a container was refused, which is a different thing (D-140)", async ({ page }) => {
    // Exactly zero, because that is what Sigma actually refuses -- see this
    // file's header, and the next test.
    await withStageStyle(
      page,
      ".map__stage{block-size:0px !important;min-block-size:0px !important;border:0 !important}",
    );
    await page.goto(mapUrl());
    await expect(page.locator("[data-map-renderer-failed]")).toBeVisible();

    expect(await reading(page)).toMatchObject({ canvas: "refused" });
    // Not the browser's fault, and the message says the next layout usually
    // recovers rather than sending the reader to find another browser.
    await expect(page.locator("[data-map-renderer-unavailable]")).toHaveCount(0);
    await expect(page.locator("[data-map-renderer-failed]")).toContainText(/no size|container/i);
    // The counts are unaffected: only the drawing is missing (D-129).
    const graph = await servedGraph(page);
    expect((await counts(page)).nodes).toBe(graph.nodes.length);
    // And the refusal is not an exception that took the route down.
    await expect(page.locator("[data-map-outline]")).toBeVisible();
  });

  test("draws into a stage two pixels high, which is why the floor is CSS (D-145)", async ({
    page,
  }) => {
    // The measured boundary, recorded as a test because the conclusion is
    // load-bearing and inverted from what `T-208` assumed:
    // `allowInvalidContainer: false` refuses a *zero* dimension, so a
    // nearly-collapsed stage is accepted and reported as a picture. Nothing
    // but the stylesheet's own minimum stands between a small window and a
    // two-pixel graph labelled "drawn".
    //
    // The two pixels are stated by this test rather than left over from the
    // stage's border (`T-212`): in the workspace the stage *is* the field and
    // has no border, so `block-size: 0` collapses it to a genuine zero, which
    // the renderer refuses -- the other state, and the subject of the two
    // tests above. What this one is about is the height the renderer accepts.
    await withStageStyle(
      page,
      ".map__stage{block-size:2px !important;min-block-size:0px !important}",
    );
    await page.goto(mapUrl());
    await expect(page.locator('.map[data-map-canvas="drawing"]')).toBeVisible();
    const height = await page
      .locator("[data-map-stage]")
      .evaluate((element) => element.getBoundingClientRect().height);
    expect(height).toBeGreaterThan(0);
    expect(height).toBeLessThan(8);
    await expect(page.locator("[data-map-renderer-failed]")).toHaveCount(0);
  });

  test("keeps a real stage at the narrow breakpoint the stylesheet states", async ({ page }) => {
    // The other half of D-145, and the claim `T-208` could not witness:
    // jsdom has no layout, so "the narrow-screen rule shortens the stage
    // rather than collapsing it" was a rule nobody had measured.
    const sizes = [
      { width: 1440, height: 900 },
      { width: 900, height: 800 },
      { width: 600, height: 800 },
      { width: 390, height: 844 },
      { width: 320, height: 568 },
    ];
    for (const size of sizes) {
      await page.setViewportSize(size);
      await page.goto(mapUrl());
      await expect(page.locator('.map[data-map-canvas="drawing"]')).toBeVisible();
      const box = await page.locator("[data-map-stage]").boundingBox();
      expect(box, `no stage box at ${size.width}x${size.height}`).not.toBeNull();
      const stage = box as NonNullable<typeof box>;
      // The stylesheet's floors: 320 px, and 240 px under 48rem. Asserted as
      // "a real stage" rather than as an exact number, because the exact one
      // belongs to `base.css` and a viewport-relative height may exceed it.
      expect(stage.height, `stage collapsed at ${size.width}px`).toBeGreaterThanOrEqual(240);
      expect(stage.width).toBeGreaterThan(0);
      // And a renderer that never refused it.
      await expect(page.locator("[data-map-renderer-failed]")).toHaveCount(0);
    }
  });

  test("lists what it holds, bounded, counted, and extendable (D-142)", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto(mapUrl());
    await expect(page.locator('.map[data-map-canvas="drawing"]')).toBeVisible();
    const graph = await servedGraph(page);
    const outline = await openPanel(page, "outline");
    const list = page.locator("[data-map-outline]");

    const listed = await list.locator("[data-map-result]").count();
    const loaded = Number(await list.getAttribute("data-map-outline-loaded"));
    const unlisted = Number(await list.getAttribute("data-map-outline-unlisted"));
    expect(loaded).toBe(graph.nodes.length);
    // Bounded at a stated page, with the remainder *counted* rather than
    // dropped -- and every listed row really in the DOM, because a windowed
    // row is a row no screen reader and no in-page search can reach.
    expect(listed + unlisted).toBe(loaded);

    // "List more" is a real control, and walking it reaches everything.
    const more = list.locator("[data-map-outline-more]");
    for (let clicks = 0; clicks < 20 && (await more.count()) > 0; clicks += 1) {
      await more.first().click();
    }
    expect(await list.locator("[data-map-result]").count()).toBe(loaded);
    expect(Number(await list.getAttribute("data-map-outline-unlisted"))).toBe(0);

    // The order is the API's own, never by degree: an invented importance is
    // what ADR 0005 invariant 15 forbids.
    const drawn = await list
      .locator("[data-map-result]")
      .evaluateAll((elements) =>
        elements.map((element) => (element as HTMLElement).dataset.globalId ?? ""),
      );
    expect(drawn).toEqual(graph.nodes.map((node) => node.global_id));
    expect(outline).toBeDefined();
  });
});
