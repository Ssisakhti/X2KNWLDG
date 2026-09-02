/**
 * Usable by everyone, measured rather than asserted by attribute (`T-209`).
 *
 * `T-208` made the DOM path primary and proved it in jsdom by role, attribute
 * and event. Three of its claims were waiting for a browser, and two of them
 * turned out to be false there:
 *
 * - **The keyboard walk.** jsdom has focus but no layout and no tab order of
 *   its own, so "reaches search, preview, focus, related knowledge and Quick
 *   Read with no pointer" was a claim about handlers. Here it is `Tab`.
 * - **Touch targets.** jsdom measures every element as zero, so a rule that
 *   claimed to cover "every interactive element" could not be checked at all.
 *   It did not: the label around the transcript checkbox was 30 px, every
 *   link inside a card was 23 px, and the skip link was 41 px (D-145).
 * - **The camera's reduced-motion duration.** `motion.ts` hands the camera
 *   `{ duration: 0 }`; what Sigma does with it on a real canvas was
 *   unobserved. Measured here in frames: with no preference the zoom is still
 *   mid-flight at 140 ms and settled by 230; with the preference, the first
 *   frame after the press is already the final one.
 */

import { expect, test } from "@playwright/test";

import { openDrawnMap, openPanel, servedGraph } from "./gate";

test.describe("the keyboard, with no pointer at all", () => {
  test("reaches search, preview, focus, related knowledge and Quick Read", async ({ page }) => {
    await openDrawnMap(page);

    // Tab from the top of the document to the search box. Nothing is clicked,
    // hovered or scrolled into view by hand: this is the reader's own path.
    const order: string[] = [];
    let reachedSearch = false;
    for (let presses = 0; presses < 40 && !reachedSearch; presses += 1) {
      await page.keyboard.press("Tab");
      const active = await page.evaluate(() => {
        const element = document.activeElement as HTMLElement | null;
        if (element === null) return { tag: "none", type: null as string | null, text: "" };
        return {
          tag: element.tagName.toLowerCase(),
          type: element.getAttribute("type"),
          text: (element.textContent ?? element.getAttribute("aria-label") ?? "")
            .replace(/\s+/gu, " ")
            .trim()
            .slice(0, 30),
        };
      });
      order.push(`${active.tag}${active.type === null ? "" : `[${active.type}]`}`);
      reachedSearch = active.type === "search";
    }
    expect(reachedSearch, `never reached the search box; tabbed through ${order.join(" ")}`).toBe(
      true,
    );
    // The skip link is the first stop, which is what it is for (D-108).
    expect(order[0]).toBe("a");

    await page.keyboard.type("a");
    await page.keyboard.press("Enter");
    const rail = page.locator('[data-map-panel="search"]');
    await expect(rail.locator("[data-map-result]").first()).toBeVisible();

    // Tab on to a Focus button. A preview appears on the way, from the
    // keyboard, with no `mouseenter` anywhere in this test.
    let previewed: string | null = null;
    let focusAction: string | null = null;
    for (let presses = 0; presses < 15 && focusAction === null; presses += 1) {
      await page.keyboard.press("Tab");
      const seen = await page.evaluate(() => ({
        action: (document.activeElement as HTMLElement | null)?.dataset.mapFocusAction ?? null,
        peek: document.querySelector("[data-map-peek]")?.getAttribute("data-map-peek") ?? null,
        origin: document.querySelector("[data-map-peek]")?.getAttribute("data-peek-origin") ?? null,
      }));
      if (seen.peek !== null && previewed === null) previewed = `${seen.peek}|${seen.origin}`;
      focusAction = seen.action;
    }
    expect(focusAction, "no Focus button was reachable by keyboard").not.toBeNull();
    expect(previewed, "no preview appeared without a pointer").not.toBeNull();
    expect(previewed).toContain("keyboard");

    await page.keyboard.press("Enter");
    await expect(page).toHaveURL(new RegExp(`focus=${encodeURIComponent(focusAction ?? "")}`));
    await expect(page.locator("[data-map-quickread]")).toContainText("Stored statement");
    await expect(page.locator('[data-map-panel="related"]')).toBeVisible();

    // Escape dismisses the transient preview from anywhere on the route.
    await page.keyboard.press("Escape");
    await expect(page.locator("[data-map-peek]")).toHaveCount(0);
  });

  test("completes the same walk with the renderer unavailable", async ({ page }) => {
    // No WebGL2, no pointer: the DOM path is the primary one (D-142), and
    // this is the walk that proves it rather than asserting it.
    await page.addInitScript(() => {
      // @ts-expect-error -- removing a global is the whole point.
      delete window.WebGL2RenderingContext;
    });
    await page.goto("/#/map");
    await expect(page.locator("[data-map-renderer-unavailable]")).toBeVisible();

    const outline = page.locator("[data-map-outline]");
    await expect(outline).toBeVisible();
    // Tab until a Focus button in the outline has focus, then press it.
    let action: string | null = null;
    for (let presses = 0; presses < 60 && action === null; presses += 1) {
      await page.keyboard.press("Tab");
      action = await page.evaluate(() => {
        const element = document.activeElement as HTMLElement | null;
        if (element === null) return null;
        const inOutline = element.closest("[data-map-outline]") !== null;
        return inOutline ? (element.dataset.mapFocusAction ?? null) : null;
      });
    }
    expect(action, "no Focus button in the companion list was reachable by keyboard").not.toBeNull();
    await page.keyboard.press("Enter");
    await expect(page).toHaveURL(new RegExp(`focus=${encodeURIComponent(action ?? "")}`));
    await expect(page.locator("[data-map-quickread]")).toContainText("Stored statement");
    await expect(page.locator("[data-map-related-entity]").first()).toBeVisible();
  });
});

test.describe("touch, motion and direction", () => {
  test("gives every control a 44 px target on a coarse pointer (D-145)", async ({ browser }) => {
    const context = await browser.newContext({
      viewport: { width: 390, height: 844 },
      hasTouch: true,
      isMobile: true,
    });
    const page = await context.newPage();
    const graph = await servedGraph(page);
    await page.goto("/#/map");
    await expect(page.locator("[data-map-nodes]")).toBeVisible();
    // Something focused, so the depth select and the cards' controls exist.
    await page.goto(`/#/map?focus=${encodeURIComponent(graph.nodes[0]?.global_id ?? "")}`);
    await expect(page.locator("[data-map-quickread]")).toBeVisible();
    await openPanel(page, "outline");

    expect(await page.evaluate(() => matchMedia("(pointer: coarse)").matches)).toBe(true);
    const small = await page.evaluate(() => {
      const MINIMUM = 44;
      const out: string[] = [];
      for (const element of document.querySelectorAll("button, summary, select, a, input")) {
        const box = element.getBoundingClientRect();
        // A control with no box is not on screen; a checkbox carries its
        // target on the label around it, which is measured in its place.
        if (box.width === 0 && box.height === 0) continue;
        const target =
          element instanceof HTMLInputElement && element.type === "checkbox"
            ? (element.closest("label") ?? element).getBoundingClientRect()
            : box;
        if (target.height + 0.5 < MINIMUM) {
          out.push(
            `${element.tagName.toLowerCase()} ${Math.round(target.height)}px "${(
              element.textContent ?? ""
            )
              .replace(/\s+/gu, " ")
              .trim()
              .slice(0, 24)}"`,
          );
        }
      }
      return out;
    });
    expect(small).toEqual([]);
    await context.close();
  });

  test("arrives immediately when the reader asks for less motion", async ({ browser }) => {
    // The claim jsdom is the wrong witness for: `{ duration: 0 }` reaches
    // `MapCamera.zoomIn`, and what the renderer does with it is only
    // observable in frames on a real canvas.
    const measure = async (motion: "no-preference" | "reduce") => {
      const context = await browser.newContext({
        reducedMotion: motion,
        viewport: { width: 1440, height: 900 },
      });
      const page = await context.newPage();
      await openDrawnMap(page);
      const stage = page.locator("[data-map-stage]");
      await stage.scrollIntoViewIfNeeded();
      const before = await stage.screenshot();

      const started = Date.now();
      await page.getByRole("button", { name: "Zoom in" }).click();
      // The screenshot's own type, because `Buffer` is a Node global this
      // program deliberately does not declare (`browser/tsconfig.json`).
      type Shot = Awaited<ReturnType<typeof stage.screenshot>>;
      const frames: { at: number; png: Shot }[] = [];
      for (let shot = 0; shot < 6; shot += 1) {
        frames.push({ at: Date.now() - started, png: await stage.screenshot() });
      }
      // Long after any easing could still be running.
      await page.waitForTimeout(900);
      const settled = await stage.screenshot();
      await context.close();
      return {
        moved: !before.equals(settled),
        // Which of the first frames were already the final picture.
        immediate: frames[0]?.png.equals(settled) ?? false,
        midFlight: frames.filter(
          (frame) => !frame.png.equals(settled) && !frame.png.equals(before),
        ).length,
        firstFrameAt: frames[0]?.at ?? 0,
      };
    };

    const eased = await measure("no-preference");
    const reduced = await measure("reduce");
    // Recorded in the run's own output, because the numbers are the result:
    // on Chrome over the GPU the eased zoom was still mid-flight at 68 ms and
    // 142 ms and final by 230, and the reduced one was final at 64.
    test.info().annotations.push({
      type: "camera frames",
      description: `eased ${JSON.stringify(eased)} reduced ${JSON.stringify(reduced)}`,
    });

    // Both actually zoom: a camera that did nothing would pass a test that
    // only checked for the absence of motion.
    expect(eased.moved).toBe(true);
    expect(reduced.moved).toBe(true);
    // With the preference, the first frame after the press is the final view.
    // This is the claim `{ duration: 0 }` exists to make.
    expect(reduced.immediate).toBe(true);
    expect(reduced.midFlight).toBe(0);
    // And the preference never costs *more* motion than its absence. Written
    // as an inequality rather than "the eased zoom is mid-flight", because
    // that depends on the screenshot being faster than the easing: it is on
    // a GPU, and it is not on a software rasteriser, where each capture
    // outlasts the animation it is trying to sample.
    expect(eased.midFlight).toBeGreaterThanOrEqual(reduced.midFlight);
  });

  test("mirrors in Persian while identifiers stay left to right", async ({ page }) => {
    const graph = await servedGraph(page);
    const entity = graph.nodes[0]?.global_id ?? "";
    await openDrawnMap(page, { focus: entity });

    // The locale control is the Shell's own, and switching it must not cost
    // the picture or the state.
    await page.locator("header select, .shell select").first().selectOption({ label: "فارسی" });
    await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
    await expect(page.locator("html")).toHaveAttribute("lang", "fa");
    await expect(page.locator('.map[data-map-canvas="drawing"]')).toBeVisible();

    // An identifier inside mirrored text is isolated left-to-right, so it is
    // never re-ordered by the paragraph's direction (D-012).
    const identifiers = await page.locator(".mono").evaluateAll((elements) =>
      elements.slice(0, 5).map((element) => ({
        text: (element.textContent ?? "").trim(),
        direction: getComputedStyle(element).direction,
        isolation: getComputedStyle(element).unicodeBidi,
      })),
    );
    expect(identifiers.length).toBeGreaterThan(0);
    for (const identifier of identifiers) {
      expect(identifier.direction).toBe("ltr");
      expect(identifier.isolation).toMatch(/isolate/);
    }
    // And the whole journey still runs: Quick Read is in Persian, over the
    // same record.
    await expect(page.locator("[data-map-quickread]")).toContainText(entity);
  });
});
