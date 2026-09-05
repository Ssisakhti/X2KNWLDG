/**
 * The Source Map, usable by everyone, measured rather than asserted (`T-257`).
 *
 * `access.spec.ts` is the Knowledge Map's half of this and the argument is
 * identical, so what is worth stating is what is *different* about this surface:
 * its reading path is longer. The Knowledge Map's journey ends at a Quick Read;
 * this one ends four levels down — a source, its brief, one of its
 * relationships, and the knowledge units that relationship rests on — and each
 * of those levels is a control someone has to be able to reach.
 *
 * jsdom proved every one of them by role and by event and could prove none of
 * them by *reach*: it has focus but no layout, no tab order of its own, and it
 * measures every element as zero pixels. Those are exactly the three things
 * below.
 *
 * The drawer is the one surface here with a history. `T-256` found by running
 * the build that it did not scroll — a Persian brief, its relationships and a
 * basis panel ran past the foot of the viewport with no way to reach them — and
 * fixed it in CSS. Nothing could fail if it regressed, which is what the last
 * test in this file is for.
 */

import { expect, test } from "@playwright/test";

import {
  cssEscape,
  focusByRow,
  measureSourceComposition,
  openDrawnSourceMap,
  relatedSource,
  servedNeighbourhood,
  servedSourceGraph,
  sourceMapUrl,
} from "./sourceGate";

test.describe("the keyboard, with no pointer at all", () => {
  test("reaches the mode, a source, its brief, a relationship and its grounds", async ({
    page,
  }) => {
    const graph = await servedSourceGraph(page);
    const chosen = relatedSource(graph);
    const served = await servedNeighbourhood(page, chosen);

    // From the Knowledge Map, because that is where a reader starts: the whole
    // journey below begins with no URL typed and no pointer moved.
    await page.goto("/#/map");
    await expect(page.locator('.map[data-map-canvas="drawing"]')).toBeVisible();

    // Tab until the mode switch's own option has focus, then press it. The
    // budget is generous and the assertion is that it was reached at all.
    const reach = async (selector: string, budget = 40): Promise<void> => {
      for (let press = 0; press < budget; press += 1) {
        const there = await page.evaluate(
          (query) => document.activeElement?.matches(query) ?? false,
          selector,
        );
        if (there) return;
        await page.keyboard.press("Tab");
      }
      throw new Error(`${budget} presses of Tab never reached ${selector}`);
    };

    // A `radiogroup` is **one** tab stop, not two: only the checked option is
    // in the tab order and the arrow keys move between the values. So the walk
    // tabs to the mode this Map currently is, and presses Right — which is the
    // widget's own contract, and a test that tabbed to the unchecked option
    // would be asserting that the control is built wrong.
    await reach('[data-map-mode-option="knowledge"]');
    expect(
      await page.locator('[data-map-mode-option="sources"]').getAttribute("tabindex"),
      "both options are tabbable, so the radiogroup is two stops",
    ).toBe("-1");
    await page.keyboard.press("ArrowRight");
    // Waited for the *picture*, not merely for the route, and that is not
    // politeness: `SourceOutline` opens itself whenever it is the only view of
    // the graph, so during the moment between arriving and drawing it is open
    // and afterwards it is not. Reading its state mid-transition and then
    // pressing Enter on the summary is how a walk *closes* the list it meant to
    // open — which is what this test did until it was measured.
    await expect(
      page.locator('.map[data-map-of="sources"][data-map-canvas="drawing"]'),
    ).toBeVisible();

    // The list of sources, and the row for the one this walk is about. A
    // `<details>` opens with Enter on its summary, which is the widget's own
    // behaviour rather than a handler this application wrote.
    const outline = page.locator('[data-map-panel="source-outline"]');
    if ((await outline.getAttribute("data-map-panel-open")) !== "true") {
      // A descendant, not a child: `data-map-panel` is on `Disclosure`'s own
      // `<section>` and the `<details>` is inside it.
      await reach('[data-map-panel="source-outline"] summary');
      await page.keyboard.press("Enter");
    }
    await expect(outline).toHaveAttribute("data-map-panel-open", "true");

    await reach(`[data-source-row="${chosen}"] button`, 60);
    await page.keyboard.press("Enter");

    // The brief, reached and readable.
    const card = page.locator(`[data-source-card="${cssEscape(chosen)}"]`);
    await expect(card).toBeVisible();
    await expect(card).toContainText(served.source_knowledge.brief?.thesis.content ?? "");

    // A relationship, selected with the keyboard, and its grounds opened by
    // that selection.
    const relation = [...served.incoming, ...served.outgoing][0];
    expect(relation, "the chosen source stands in no relationship").toBeDefined();
    await reach(`[data-source-relation-row="${cssEscape(relation!.id)}"] button`, 60);
    await page.keyboard.press("Enter");
    const basis = page.locator(`[data-source-basis="${cssEscape(relation!.id)}"]`);
    await expect(basis).toBeVisible();
    await expect(basis).toContainText(relation!.rationale);

    // And out of the Map into the records: the last link in the journey is
    // reachable by the same key, and it addresses the Reader in the grammar the
    // application already has — `#/sources/<id>?tab=units` — rather than a route
    // this surface minted for itself.
    await reach("[data-source-unit-link]", 60);
    const address = await page.evaluate(
      () => document.activeElement?.getAttribute("href") ?? "",
    );
    expect(address).toContain(encodeURIComponent(relation!.from_source_id));
    expect(address).toContain("tab=units");
  });

  test("keeps every focused control visible rather than under the drawer", async ({ page }) => {
    // WCAG 2.2 AA *Focus Not Obscured*, which on this surface is a real risk
    // and not a formality: the drawer is a floating column over the field, so a
    // control behind it can hold focus and be invisible.
    await openDrawnSourceMap(page);
    const graph = await servedSourceGraph(page);
    await focusByRow(page, relatedSource(graph));

    /*
     * Measured against the control's **clipped** rectangle, and that distinction
     * is the whole test rather than a detail of it.
     *
     * The workspace does not scroll the document (D-153); its floats scroll
     * themselves, and at this viewport the search float is a 173 px scroll box
     * holding a list of every source. So most of that list is outside its own
     * scrollport at any moment — which is normal, is what a reader scrolls, and
     * is *not* obscuring. A probe that asked `elementFromPoint` at each
     * control's own centre reported five of them "under `div.sigma-mouse`" for
     * exactly that reason: the point was clipped away, so the canvas behind it
     * answered.
     *
     * What is asked instead is the question the clause is about: intersect the
     * control with every ancestor that clips it, and if anything is left on
     * screen, ask what is painted at the middle of *that*.
     */
    const obscured = await page.evaluate(() => {
      const out: string[] = [];
      for (const control of document.querySelectorAll("button, a[href], summary, select")) {
        const box = control.getBoundingClientRect();
        if (box.width === 0 || box.height === 0) continue;

        let left = box.left;
        let top = box.top;
        let right = box.right;
        let bottom = box.bottom;
        for (
          let ancestor = control.parentElement;
          ancestor !== null;
          ancestor = ancestor.parentElement
        ) {
          const style = getComputedStyle(ancestor);
          if (style.overflow === "visible" && style.overflowY === "visible") continue;
          const clip = ancestor.getBoundingClientRect();
          left = Math.max(left, clip.left);
          top = Math.max(top, clip.top);
          right = Math.min(right, clip.right);
          bottom = Math.min(bottom, clip.bottom);
        }
        left = Math.max(left, 0);
        top = Math.max(top, 0);
        right = Math.min(right, window.innerWidth);
        bottom = Math.min(bottom, window.innerHeight);
        // Nothing of it is on screen: a reader scrolls to it, and it is not
        // being covered by anything.
        if (right - left < 2 || bottom - top < 2) continue;

        const at = document.elementFromPoint(
          Math.round((left + right) / 2),
          Math.round((top + bottom) / 2),
        );
        if (at === null) continue;
        if (control.contains(at) || at.contains(control)) continue;
        out.push(
          `${control.tagName.toLowerCase()} "${(control.textContent ?? "")
            .replace(/\s+/gu, " ")
            .trim()
            .slice(0, 30)}" is under ${at.tagName.toLowerCase()}.${String(at.className)}`,
        );
      }
      return out;
    });
    expect(obscured).toEqual([]);
  });
});

test.describe("touch, motion and direction", () => {
  test("gives every control a 44 px target on a coarse pointer", async ({ browser }) => {
    const context = await browser.newContext({
      viewport: { width: 390, height: 844 },
      hasTouch: true,
    });
    const page = await context.newPage();
    const graph = await servedSourceGraph(page);
    const chosen = relatedSource(graph);

    // A selection, so the drawer's controls exist to be measured: the card's
    // two links, the relationship rows and every unit link in the basis.
    await page.goto(sourceMapUrl({ focus: `${chosen}:source` }));
    await expect(page.locator(`[data-source-card="${cssEscape(chosen)}"]`)).toBeVisible();
    const outline = page.locator('[data-map-panel="source-outline"]');
    if ((await outline.getAttribute("data-map-panel-open")) !== "true") {
      await outline.locator("summary").tap();
    }

    expect(await page.evaluate(() => matchMedia("(pointer: coarse)").matches)).toBe(true);
    const small = await page.evaluate(() => {
      const MINIMUM = 44;
      const out: string[] = [];
      for (const element of document.querySelectorAll("button, summary, select, a, input")) {
        const box = element.getBoundingClientRect();
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

  test("completes the journey by tap, with no hover anywhere in it", async ({ browser }) => {
    // A touch device fires no `mouseenter`, so "hover is never required" is a
    // claim about *this* walk — and it matters more here than on the Knowledge
    // Map, because this Map has no hover surface at all to fall back on.
    const context = await browser.newContext({
      viewport: { width: 390, height: 844 },
      hasTouch: true,
    });
    const page = await context.newPage();
    const graph = await servedSourceGraph(page);
    const chosen = relatedSource(graph);
    const served = await servedNeighbourhood(page, chosen);

    await page.goto(sourceMapUrl());
    // Settled before its state is read, for the reason the keyboard walk above
    // records: the list opens itself while there is no picture, so a toggle
    // decided mid-transition closes the list it meant to open.
    await expect(
      page.locator('.map[data-map-of="sources"][data-map-canvas="drawing"]'),
    ).toBeVisible();

    const outline = page.locator('[data-map-panel="source-outline"]');
    if ((await outline.getAttribute("data-map-panel-open")) !== "true") {
      await outline.locator("summary").tap();
    }
    await expect(outline).toHaveAttribute("data-map-panel-open", "true");
    await page.locator(`[data-source-row="${cssEscape(chosen)}"] button`).tap();

    const card = page.locator(`[data-source-card="${cssEscape(chosen)}"]`);
    await expect(card).toBeVisible();
    await expect(page).toHaveURL(new RegExp(`focus=${encodeURIComponent(`${chosen}:source`)}`));

    const relation = [...served.incoming, ...served.outgoing][0]!;
    await page.locator(`[data-source-relation-row="${cssEscape(relation.id)}"] button`).first().tap();
    await expect(page.locator(`[data-source-basis="${cssEscape(relation.id)}"]`)).toBeVisible();

    // The other end of the relationship, then Back: history is the same on a
    // phone, and the selection it returns to is the one that was left.
    const other =
      relation.from_source_id === chosen ? relation.to_source_id : relation.from_source_id;
    await page.locator(".relationlist__other").first().tap();
    await expect(page.locator(`[data-source-card="${cssEscape(other)}"]`)).toBeVisible();
    await page.goBack();
    await expect(page.locator(`[data-source-card="${cssEscape(chosen)}"]`)).toBeVisible();
    await context.close();
  });

  test("arrives immediately when the reader asks for less motion", async ({ browser }) => {
    // The camera frames a selection on this Map too (D-146), so the same claim
    // has to be made about it: with the preference set, the first frame after
    // the gesture is the final one. Measured in frames on a real canvas,
    // because that is the only place `{ duration: 0 }` becomes observable.
    const measure = async (motion: "no-preference" | "reduce") => {
      const context = await browser.newContext({
        reducedMotion: motion,
        viewport: { width: 1440, height: 900 },
      });
      const page = await context.newPage();
      await openDrawnSourceMap(page);
      const stage = page.locator("[data-map-stage]");
      await stage.scrollIntoViewIfNeeded();
      const before = await stage.screenshot();

      await page.getByRole("button", { name: "Zoom in" }).click();
      type Shot = Awaited<ReturnType<typeof stage.screenshot>>;
      const frames: Shot[] = [];
      for (let shot = 0; shot < 6; shot += 1) frames.push(await stage.screenshot());
      await page.waitForTimeout(900);
      const settled = await stage.screenshot();
      await context.close();
      return {
        moved: !before.equals(settled),
        immediate: frames[0]?.equals(settled) ?? false,
        midFlight: frames.filter((frame) => !frame.equals(settled) && !frame.equals(before)).length,
      };
    };

    const eased = await measure("no-preference");
    const reduced = await measure("reduce");
    test.info().annotations.push({
      type: "camera frames",
      description: `eased ${JSON.stringify(eased)} reduced ${JSON.stringify(reduced)}`,
    });

    expect(eased.moved).toBe(true);
    expect(reduced.moved).toBe(true);
    expect(reduced.immediate).toBe(true);
    expect(reduced.midFlight).toBe(0);
    expect(eased.midFlight).toBeGreaterThanOrEqual(reduced.midFlight);
  });

  test("mirrors in Persian while identifiers stay left to right", async ({ page }) => {
    const graph = await servedSourceGraph(page);
    const chosen = relatedSource(graph);
    const served = await servedNeighbourhood(page, chosen);
    await openDrawnSourceMap(page, { focus: `${chosen}:source` });

    await page.locator("header select, .shell select").first().selectOption({ label: "فارسی" });
    await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
    await expect(page.locator('.map[data-map-canvas="drawing"]')).toBeVisible();

    // The brief is Persian in *both* locales, because the record is: the
    // output-language policy governs the records and not the chrome, and this
    // is that consequence asserted rather than described.
    const card = page.locator(`[data-source-card="${cssEscape(chosen)}"]`);
    await expect(card).toContainText(served.source_knowledge.brief?.thesis.content ?? "");

    // Every identifier inside mirrored text is isolated left to right (D-012):
    // a source id, a `KU-` chip and a relation id all sit inside Persian prose
    // here, which is the case the isolation exists for.
    const identifiers = await page.locator(".mono").evaluateAll((elements) =>
      elements.slice(0, 8).map((element) => ({
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

    // The composition mirrors rather than breaking: the drawer is on the other
    // side of the field, and nothing sits on top of anything else.
    const report = await measureSourceComposition(page);
    expect(report.direction).toBe("rtl");
    expect(report.collided).toEqual([]);
  });
});

test.describe("the drawer", () => {
  test("can be read to its foot at a viewport a brief does not fit", async ({ browser }) => {
    /*
     * `T-256`'s own finding, turned into something that can fail.
     *
     * The column holds a card, a relationship list and a basis panel, and a
     * brief is exactly as long as the record is. At a short viewport its foot
     * was below the fold with no way to reach it — found by running the build,
     * because every test that could have caught it measures a document that
     * scrolls, and this one does not (D-153).
     *
     * The assertion is not "the CSS says `overflow-y: auto`", which would pass
     * against a column that had no room to need it. It is that the drawer's
     * content is *taller than its box* at this viewport — so scrolling is
     * genuinely required — and that scrolling it really moves it.
     */
    const context = await browser.newContext({ viewport: { width: 1280, height: 620 } });
    const page = await context.newPage();
    const graph = await servedSourceGraph(page);
    const chosen = relatedSource(graph);
    await page.goto(sourceMapUrl({ focus: `${chosen}:source` }));
    await expect(page.locator(`[data-source-card="${cssEscape(chosen)}"]`)).toBeVisible();

    const report = await measureSourceComposition(page);
    expect(report.drawer, "the drawer is not on the page").not.toBeNull();
    expect(report.drawer!.overflowY).toMatch(/auto|scroll/);
    expect(
      report.drawer!.scrollHeight,
      "the drawer fits at this viewport, so this test proves nothing — shorten it",
    ).toBeGreaterThan(report.drawer!.clientHeight);
    // The drawer stays inside the viewport rather than running past its foot.
    expect(report.drawer!.bottom).toBeLessThanOrEqual(report.viewport.height + 1);

    // And it really scrolls: the last thing in the column can be brought into
    // view, which is what a reader needs and what was missing.
    const moved = await page.evaluate(() => {
      const drawer = document.querySelector(".map__drawer");
      if (drawer === null) return null;
      const before = drawer.scrollTop;
      drawer.scrollTop = drawer.scrollHeight;
      return { before, after: drawer.scrollTop };
    });
    expect(moved).not.toBeNull();
    expect(moved!.after).toBeGreaterThan(moved!.before);
    await context.close();
  });
});
