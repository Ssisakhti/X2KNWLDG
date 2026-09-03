/**
 * Capture the CURRENT Map at the review viewport, as the comparison baseline
 * for T-211. This is what the visual review rejected; the mockups argue against
 * these two pictures rather than against a memory of them.
 *
 * Needs the real API and the built bundle already served, because the renderer
 * is a lazily imported chunk that only exists in a build (D-127):
 *
 *   ../.venv/bin/python scripts/dev_api.py --project-root .. --port 8955
 *   X2KNWLDG_API_BASE=http://127.0.0.1:8955 npm run build
 *   X2KNWLDG_API_BASE=http://127.0.0.1:8955 npx vite preview --port 4199
 *   npx tsx scripts/capture_baseline.ts
 */
import { chromium } from "@playwright/test";
import { fileURLToPath } from "node:url";
import path from "node:path";
import fs from "node:fs/promises";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const OUT = path.resolve(HERE, "../../docs/mockups/T-211/captures");
const BASE = process.env.X2KNWLDG_BASELINE_URL ?? "http://127.0.0.1:4199";
const REVIEW = { width: 2852, height: 1688 };
const FOCUS = "youtube:pqlWNihgdjI:KU-000028";

const browser = await chromium.launch();
const context = await browser.newContext({ viewport: REVIEW, colorScheme: "dark", deviceScaleFactor: 1 });
const page = await context.newPage();
await fs.mkdir(OUT, { recursive: true });

for (const [name, hash] of [
  ["baseline-explore", "#/map"],
  ["baseline-focus", `#/map?focus=${encodeURIComponent(FOCUS)}`],
] as const) {
  await page.goto(`${BASE}/${hash}`, { waitUntil: "load" });
  // The stage settles after the camera eases and MAP_STAGE_SETTLE_MS elapses.
  await page.waitForSelector("[data-map-stage]", { timeout: 30_000 });
  await page.waitForFunction(
    () => document.querySelector("[data-map-nodes]")?.getAttribute("data-map-nodes") !== "0",
    undefined,
    { timeout: 30_000 },
  ).catch(() => undefined);
  await page.waitForTimeout(2500);

  // fullPage, because the whole point of the baseline is how far down the
  // document the stage begins. A viewport-only shot would hide the finding.
  const file = path.join(OUT, `${name}.png`);
  await page.screenshot({ path: file, fullPage: true });
  const metrics = await page.evaluate(() => {
    const stage = document.querySelector("[data-map-stage]");
    const box = stage?.getBoundingClientRect();
    return {
      documentHeight: document.documentElement.scrollHeight,
      stageTop: box ? Math.round(box.top + window.scrollY) : null,
      stageHeight: box ? Math.round(box.height) : null,
      nodes: document.querySelector("[data-map-nodes]")?.getAttribute("data-map-nodes") ?? null,
      main: Math.round(document.querySelector(".shell__main")?.getBoundingClientRect().width ?? 0),
    };
  });
  console.log(`${name}: ${JSON.stringify(metrics)}`);
}

await context.close();
await browser.close();
