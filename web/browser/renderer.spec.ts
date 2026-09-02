/**
 * The renderer's own life, and the numbers nobody had measured (`T-209`).
 *
 * ADR 0005 invariant 10 -- "a filter/reload loop must not accumulate WebGL
 * contexts or workers" -- is the one invariant in this phase that *cannot* be
 * checked anywhere but a browser: jsdom has no WebGL, so the Map's suites
 * assert the create/kill *sequence* against an injected fake and the contexts
 * themselves are counted here. Browsers publish no count of live contexts and
 * answer an excess by losing the oldest, so a leak surfaces as a blank canvas
 * somewhere unrelated, long after the mistake.
 *
 * Counting them here found the leak the phase had: a renderer that **refused**
 * its container had already created its canvas and taken a context, and the
 * object whose `kill()` would release it was never handed over, so nothing
 * released it. Seven refused attaches left seven live contexts and seven
 * orphan canvases in the stage (D-145). The fake could not have shown it,
 * because a fake factory throws without having created anything.
 *
 * The other specs here measure what was chosen by argument: the card budget,
 * the cell that became a footprint, the framing margin, and the accounting
 * that says no neighbour is ever silently dropped (R20).
 */

import { expect, test } from "@playwright/test";

import {
  busiest,
  contextReport,
  countContexts,
  mapUrl,
  openDrawnMap,
  servedGraph,
  settledStage,
} from "./gate";

test.describe("the renderer's lifecycle", () => {
  test("releases every context it creates, across filters and route changes", async ({ page }) => {
    await countContexts(page);
    await openDrawnMap(page);
    expect(await contextReport(page)).toMatchObject({ created: 1, live: 1 });

    // A filter change is a different question, so it is a different snapshot
    // and a new renderer (D-118). Each replacement must kill its predecessor.
    for (const value of ["source", "derived", ""]) {
      await page.locator('[data-map-filter="provenance_class"]').selectOption(value);
      await expect(page.locator("[data-map-nodes]")).toBeVisible();
    }
    // Leaving the route and coming back is the other half: `MapSession.kill()`
    // on unmount is all that stands between this and a pile of contexts.
    for (let trip = 0; trip < 5; trip += 1) {
      await page.getByRole("link", { name: "Library" }).click();
      await expect(page.locator(".map")).toHaveCount(0);
      await page.getByRole("link", { name: "Map" }).click();
      await expect(page.locator('.map[data-map-canvas="drawing"]')).toBeVisible();
    }

    const report = await contextReport(page);
    // Exactly one alive -- the one on screen -- and every other one lost,
    // with a `webglcontextlost` event for each, because Sigma's `kill()`
    // calls `loseContext()` explicitly rather than leaving it to the
    // collector.
    expect(report.live).toBe(1);
    expect(report.lost).toBe(report.created - 1);
    expect(report.lostEvents).toBeGreaterThanOrEqual(report.created - 1);
    // And several were really created: a test that passed because nothing
    // happened would prove nothing.
    expect(report.created).toBeGreaterThan(5);
    await expect(page.locator("[data-map-stage] canvas")).toHaveCount(1);
  });

  test("releases the context a refused container left behind (D-145)", async ({ page }) => {
    // The leak, as a regression. The stage is given no height at all, which
    // is what `allowInvalidContainer: false` refuses, and then the route is
    // asked to draw seven times over.
    await countContexts(page);
    await page.route("**/*", async (route) => {
      if (route.request().resourceType() !== "document") return route.continue();
      const response = await route.fetch();
      const body = (await response.text()).replace(
        "</head>",
        "<style>.map__stage{block-size:0px !important;min-block-size:0px !important;border:0 !important}</style></head>",
      );
      await route.fulfill({
        response,
        body,
        headers: { ...response.headers(), "content-type": "text/html" },
      });
    });

    await page.goto(mapUrl());
    await expect(page.locator("[data-map-renderer-failed]")).toBeVisible();
    for (const value of ["source", "derived", "", "source", "derived", ""]) {
      await page.locator('[data-map-filter="provenance_class"]').selectOption(value);
      await expect(page.locator("[data-map-renderer-failed]")).toBeVisible();
    }

    const report = await contextReport(page);
    // Several refusals really happened, which is what makes the rest of this
    // an assertion rather than a description of an empty page. A floor rather
    // than a count of the presses above: a snapshot the walk decides is the
    // same question does not re-attach, and how many attempts a driver gets
    // through in the time available differs -- Chrome on the GPU reached
    // seven here, the software rasteriser three.
    expect(report.created).toBeGreaterThanOrEqual(2);
    // Nothing alive, because nothing is drawn: every refused attempt released
    // what it had taken.
    expect(report.live).toBe(0);
    expect(report.lostEvents).toBeGreaterThanOrEqual(report.created);
    // And the container is empty rather than holding a stack of dead canvases.
    await expect(page.locator("[data-map-stage] canvas")).toHaveCount(0);
  });
});

test.describe("the numbers the stage was given by argument", () => {
  test("brings a focus and its neighbours onto the stage (D-146)", async ({ page }) => {
    const graph = await servedGraph(page);
    const centre = busiest(graph);

    // Where the focus is drawn, before and after it is selected. Without the
    // framing gesture a selection landed wherever the layout had put it -- and
    // `Zoom in` zooms about the middle of the stage, so pressing it twice
    // pushed the selection off screen entirely.
    await openDrawnMap(page, { focus: centre });
    const stage = await page.locator("[data-map-stage]").boundingBox();
    const box = stage as NonNullable<typeof stage>;
    const primary = page.locator('.map__overlay [data-map-card][data-map-card-primary="true"]');
    await expect(primary).toBeVisible();

    const anchor = await primary.evaluate((element) => ({
      x: Number.parseFloat((element as HTMLElement).style.left),
      y: Number.parseFloat((element as HTMLElement).style.top),
    }));
    // The focus is near the middle of the stage: the gesture centres the
    // focus *and its neighbours*, so it is not exact -- it is nowhere near
    // an edge, which is what mattered.
    expect(Math.abs(anchor.x - box.width / 2)).toBeLessThan(box.width / 4);
    expect(Math.abs(anchor.y - box.height / 2)).toBeLessThan(box.height / 4);

    // Every neighbour's mark stays on the stage, which is what the framing
    // margin was calibrated for: `off_stage` is the omission a framing
    // gesture must never cause.
    const offStage = page.locator('[data-map-stage-omission="off_stage"]');
    expect(await offStage.count()).toBe(0);

    // And zooming keeps the selection on screen rather than losing it.
    await page.getByRole("button", { name: "Zoom in" }).click();
    await page.getByRole("button", { name: "Zoom in" }).click();
    await expect(primary).toBeVisible();
  });

  test("accounts for every neighbour: carded, or counted with a reason (R20)", async ({ page }) => {
    const graph = await servedGraph(page);
    const centre = busiest(graph);
    await openDrawnMap(page, { focus: centre });
    await expect(page.locator("[data-map-quickread]")).toBeVisible();
    await settledStage(page);

    const neighbourhood = await page.request.get(
      `/api/graph/neighborhood/${encodeURIComponent(centre)}?depth=1&limit=200`,
    );
    const body = (await neighbourhood.json()) as {
      data: { center_id: string; nodes: { global_id: string }[] };
    };
    const returned = body.data.nodes.filter((node) => node.global_id !== body.data.center_id);

    const cards = await page
      .locator('.map__overlay [data-map-card][data-map-card-primary="false"]')
      .count();
    const omitted = await page
      .locator("[data-map-stage-omission]")
      .evaluateAll((elements) =>
        elements.map((element) =>
          Number.parseInt((element.textContent ?? "0").trim().split(/\s/u)[0] ?? "0", 10),
        ),
      );
    const counted = omitted.reduce((sum, value) => sum + value, 0);

    // The accounting is total: cards placed plus omissions counted equals the
    // neighbours the server returned. This is the assertion "no neighbour
    // silently disappears" reduces to.
    expect(cards + counted).toBe(returned.length);
    // And the related list holds all of them regardless (invariant 13).
    await expect(page.locator("[data-map-related-entity]")).toHaveCount(returned.length);
    // The stage never carries more cards than the stated budget.
    expect(cards).toBeLessThanOrEqual(4);
  });

  test("draws no two cards over the same pixels (D-145)", async ({ page }) => {
    // The defect this replaced: a 240 px grid placed a neighbour card over
    // two thirds of the focused statement, including the marker that says its
    // text was cut -- the one kind of silent cut D-131 forbids.
    const graph = await servedGraph(page);
    for (const centre of [busiest(graph), graph.nodes[0]?.global_id ?? ""]) {
      await openDrawnMap(page, { focus: centre });
      await settledStage(page);
      const boxes = await page
        .locator(".map__overlay [data-map-card]")
        .evaluateAll((elements) =>
          elements.map((element) => {
            const rect = element.getBoundingClientRect();
            return {
              id: (element as HTMLElement).dataset.mapCard ?? "",
              left: rect.left,
              top: rect.top,
              right: rect.right,
              bottom: rect.bottom,
            };
          }),
        );
      for (let left = 0; left < boxes.length; left += 1) {
        for (let right = left + 1; right < boxes.length; right += 1) {
          const a = boxes[left] as NonNullable<(typeof boxes)[number]>;
          const b = boxes[right] as NonNullable<(typeof boxes)[number]>;
          const overlap =
            a.left < b.right && b.left < a.right && a.top < b.bottom && b.top < a.bottom;
          expect(overlap, `${a.id} and ${b.id} overlap on the stage`).toBe(false);
        }
      }
    }
  });

  test("keeps the overview quiet and lets zoom make it speak (D-122)", async ({ page }) => {
    // The four label numbers, measured the only way a canvas allows: by what
    // the picture *is*. Labels are drawn in WebGL, so there is nothing to
    // count in the DOM -- but the overview, a zoomed view and a focused view
    // must be three different pictures, and a policy that drew every label
    // would make the first two identical piles.
    await page.setViewportSize({ width: 1440, height: 900 });
    await openDrawnMap(page);
    const stage = page.locator("[data-map-stage]");
    await stage.scrollIntoViewIfNeeded();
    const overview = await stage.screenshot();

    await page.getByRole("button", { name: "Zoom in" }).click();
    await page.getByRole("button", { name: "Zoom in" }).click();
    await page.waitForTimeout(600);
    const zoomed = await stage.screenshot();
    expect(zoomed.equals(overview)).toBe(false);

    // Reset returns to the framed whole graph, which is where a reload
    // starts: the same picture as the overview, because the layout is a pure
    // function of the seeds (D-118).
    await page.getByRole("button", { name: "Reset the view" }).click();
    await page.waitForTimeout(900);
    const reset = await stage.screenshot();
    expect(reset.equals(overview)).toBe(true);
  });

  test("reloads to the same picture, from the same URL", async ({ page }) => {
    // Determinism, which is what makes a Map worth having an address: the
    // seeds are hashed from each `global_id` rather than taken from a
    // position in a page (D-118), so a reload reproduces what the reader last
    // saw -- and the framing gesture is a pure function of that layout, so
    // the selection lands in the same place too.
    //
    // Compared by *where the marks are* rather than by pixels. A card is
    // anchored at its mark's own position, so the overlay is a numeric
    // readout of the drawing; two screenshots would compare antialiasing as
    // well, and `PROJECT_MANAGEMENT.md` rules a pixel golden out for exactly
    // that reason -- it differs between a Metal driver and a software
    // rasteriser for reasons that are not defects.
    const graph = await servedGraph(page);
    const anchors = async () => {
      await settledStage(page);
      return page.locator(".map__overlay [data-map-card]").evaluateAll((elements) =>
        elements
          .map((element) => ({
            id: (element as HTMLElement).dataset.mapCard ?? "",
            x: Math.round(Number.parseFloat((element as HTMLElement).style.left)),
            y: Math.round(Number.parseFloat((element as HTMLElement).style.top)),
          }))
          .sort((left, right) => (left.id < right.id ? -1 : 1)),
      );
    };

    await openDrawnMap(page, { focus: busiest(graph) });
    const first = await anchors();
    expect(first.length).toBeGreaterThan(0);

    await page.reload();
    await expect(page.locator('.map[data-map-canvas="drawing"]')).toBeVisible();
    expect(await anchors()).toEqual(first);
  });
});
