/**
 * Measure the Directional Orbit on the running build (`T-213`, `T-215`).
 *
 * `T-212` re-measured `SPEC.md` §1's table to show that the workspace had
 * replaced the document; this measures the composition inside it. The numbers
 * it prints are the ones the task rows and the decision ledger quote, and they
 * are read off a real browser rather than estimated -- which is the whole
 * reason ADR 0006 exists: a green component suite said nothing about any of
 * the defects the browser found in `T-212`.
 *
 * What it reports, per viewport:
 *
 * - the tier the route says it drew, and the field it measured;
 * - cards placed against neighbours returned, and every omission by its
 *   stated reason, so `placed + counted === returned` can be read rather
 *   than trusted;
 * - the geometry clauses, as *lists of violations*: a card over another
 *   card, a card or pill under a floating control, anything outside the
 *   field, and any pill that found no clear seat on its path;
 * - the document's own height, which must stay the viewport's (D-153);
 * - what the browser laid each card out at, which is what the reserved boxes
 *   have to be an upper bound over (`T-209`'s discipline).
 *
 * `T-215` moved the measuring itself into `browser/composition.ts`, so this
 * script and the gate's per-scenario assertions read the same numbers off the
 * same probe rather than two implementations that can drift. What stays here
 * is the part that is a *script*: three viewports, one focus, and a line of
 * output per viewport for a human to read.
 *
 * Needs the real API and the built bundle already served, because the
 * renderer is a lazily imported chunk that only exists in a build (D-127):
 *
 *   ../.venv/bin/python scripts/dev_api.py --project-root .. --port 8955
 *   X2KNWLDG_API_BASE=http://127.0.0.1:8955 npm run build
 *   X2KNWLDG_API_BASE=http://127.0.0.1:8955 npx vite preview --port 4199
 *   npm run measure:orbit
 */
import { chromium } from "@playwright/test";

import { measureComposition, summarise } from "../browser/composition";

const BASE = process.env.X2KNWLDG_ORBIT_URL ?? "http://127.0.0.1:4199";
/** The review viewport, and the breakpoint `T-212` left a number to beat at. */
const VIEWPORTS = [
  { name: "2852x1688", width: 2852, height: 1688 },
  { name: "1440x900", width: 1440, height: 900 },
  { name: "1280x720", width: 1280, height: 720 },
] as const;
/** The busiest entity in the committed library: the hardest fan-out to place. */
const FOCUS = "youtube:pqlWNihgdjI:KU-000028";

const browser = await chromium.launch();

for (const viewport of VIEWPORTS) {
  const context = await browser.newContext({
    viewport: { width: viewport.width, height: viewport.height },
    colorScheme: "dark",
    deviceScaleFactor: 1,
  });
  const page = await context.newPage();
  await page.goto(`${BASE}/#/map?focus=${encodeURIComponent(FOCUS)}`, { waitUntil: "load" });
  await page.waitForSelector("[data-map-stage]", { timeout: 30_000 });
  await page
    .waitForFunction(
      () => document.querySelector("[data-map-nodes]")?.getAttribute("data-map-nodes") !== "0",
      undefined,
      { timeout: 30_000 },
    )
    .catch(() => undefined);
  await page.waitForTimeout(2000);

  const report = await measureComposition(page);
  const boxes = report.cards.map(
    (card) =>
      `${card.primary ? "primary" : card.hops}:${Math.round(card.rect.width)}x${Math.round(
        card.rect.height,
      )}`,
  );
  const chrome = report.chrome.map(
    (control) =>
      `${control.name}:${Math.round(control.rect.left)},${Math.round(
        control.rect.top,
      )} ${Math.round(control.rect.width)}x${Math.round(control.rect.height)}`,
  );
  console.log(`${viewport.name}: ${summarise(report)}`);
  console.log(`  boxes  ${JSON.stringify(boxes)}`);
  console.log(`  chrome ${JSON.stringify(chrome)}`);
  await context.close();
}

await browser.close();
