/**
 * Measure the Directional Orbit on the running build (`T-213`).
 *
 * `T-212` re-measured `SPEC.md` §1's table to show that the workspace had
 * replaced the document; this measures the composition inside it. The numbers
 * it prints are the ones the task row and the decision ledger quote, and they
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
 * - the geometry clauses, as *counts of violations*: a card over another
 *   card, a card or pill under a floating control, anything outside the
 *   field, and any pill that found no clear seat on its path;
 * - the document's own height, which must stay the viewport's (D-153).
 *
 * Needs the real API and the built bundle already served, because the
 * renderer is a lazily imported chunk that only exists in a build (D-127):
 *
 *   ../.venv/bin/python scripts/dev_api.py --project-root .. --port 8955
 *   X2KNWLDG_API_BASE=http://127.0.0.1:8955 npm run build
 *   X2KNWLDG_API_BASE=http://127.0.0.1:8955 npx vite preview --port 4199
 *   npx tsx scripts/measure_orbit.ts
 */
import { chromium } from "@playwright/test";

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

  const measured = await page.evaluate(() => {
    // No named helper in here, deliberately: `tsx` compiles this callback with
    // esbuild's `keepNames`, which wraps a function bound to a name in a
    // `__name` call the page has never heard of, and the evaluation dies with
    // a ReferenceError that says nothing about geometry. So the overlap test
    // is written out at each of its two use sites.

    const route = document.querySelector(".map");
    const stage = document.querySelector("[data-map-stage]");
    const field = stage?.getBoundingClientRect() ?? null;
    const cards = [...document.querySelectorAll("[data-map-card]")];
    const pills = [...document.querySelectorAll("[data-orbit-pill]")];
    const chrome = [...document.querySelectorAll("[data-map-chrome]")];
    const marks = [...cards, ...pills];

    const clipped: string[] = [];
    const collided: string[] = [];
    const covered: string[] = [];
    if (field !== null) {
      for (const node of marks) {
        const box = node.getBoundingClientRect();
        const id =
          node.getAttribute("data-map-card") ?? node.getAttribute("data-orbit-pill") ?? "?";
        if (
          box.left < field.left - 0.5 ||
          box.top < field.top - 0.5 ||
          box.right > field.right + 0.5 ||
          box.bottom > field.bottom + 0.5
        ) {
          clipped.push(id);
        }
        for (const control of chrome) {
          const zone = control.getBoundingClientRect();
          if (
            zone.width > 0 &&
            zone.height > 0 &&
            box.left < zone.right &&
            zone.left < box.right &&
            box.top < zone.bottom &&
            zone.top < box.bottom
          ) {
            covered.push(`${id} under ${control.className}`);
          }
        }
      }
      for (let i = 0; i < marks.length; i += 1) {
        for (let j = i + 1; j < marks.length; j += 1) {
          const a = marks[i];
          const b = marks[j];
          if (a === undefined || b === undefined) continue;
          const one = a.getBoundingClientRect();
          const two = b.getBoundingClientRect();
          if (
            one.left < two.right &&
            two.left < one.right &&
            one.top < two.bottom &&
            two.top < one.bottom
          ) {
            collided.push(
              `${a.getAttribute("data-map-card") ?? a.getAttribute("data-orbit-pill")} / ` +
                `${b.getAttribute("data-map-card") ?? b.getAttribute("data-orbit-pill")}`,
            );
          }
        }
      }
    }

    const omissions: Record<string, number> = {};
    for (const node of document.querySelectorAll("[data-map-stage-omission]")) {
      const reason = node.getAttribute("data-map-stage-omission") ?? "?";
      omissions[reason] = Number((node.textContent ?? "").trim().split(/\s+/u)[0] ?? 0);
    }

    return {
      tier: route?.getAttribute("data-map-tier") ?? null,
      field: field === null ? null : `${Math.round(field.width)}x${Math.round(field.height)}`,
      documentHeight: document.documentElement.scrollHeight,
      returned: Number(
        document.querySelector("[data-map-related]")?.getAttribute("data-map-related") ?? 0,
      ),
      placed: cards.length - 1,
      omittedTotal: Number(
        document.querySelector("[data-map-stage-omitted]")?.getAttribute("data-map-stage-omitted") ??
          0,
      ),
      omissions,
      // What the browser actually laid the cards out at, which is what the
      // reserved boxes have to be an upper bound over (`T-209`'s discipline).
      boxes: cards.map((node) => {
        const box = node.getBoundingClientRect();
        return `${node.getAttribute("data-map-card-primary") === "true" ? "primary" : node.getAttribute("data-map-card-hops")}:${Math.round(box.width)}x${Math.round(box.height)}`;
      }),
      chrome: chrome.map((node) => {
        const box = node.getBoundingClientRect();
        return `${node.className}:${Math.round(box.left)},${Math.round(box.top)} ${Math.round(box.width)}x${Math.round(box.height)}`;
      }),
      pills: pills.length,
      crowdedPills: pills.filter(
        (pill) => pill.getAttribute("data-orbit-pill-crowded") === "true",
      ).length,
      clipped,
      collided,
      covered,
    };
  });

  const accounted = measured.placed + measured.omittedTotal === measured.returned;
  console.log(`${viewport.name}: ${JSON.stringify({ ...measured, accounted })}`);
  await context.close();
}

await browser.close();
