/**
 * Capture the T-211 mockups at the review viewport.
 *
 * This is a standalone Playwright script, NOT a spec: it is not registered with
 * the browser gate, it asserts nothing, and `npm run browser` does not run it.
 * T-211 produces pictures for a human to approve; T-215 is where captures grow
 * assertions.
 *
 *   npx tsx web/scripts/capture_mockups.ts            # every capture
 *   npx tsx web/scripts/capture_mockups.ts explore    # one page's captures
 */
import { chromium, type Browser } from "@playwright/test";
import { fileURLToPath } from "node:url";
import http from "node:http";
import path from "node:path";
import fs from "node:fs/promises";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const MOCKUPS = path.resolve(HERE, "../../docs/mockups/T-211");
const OUT = path.join(MOCKUPS, "captures");

/** The review viewport T-211 and T-215 are both specified against. */
const REVIEW = { width: 2852, height: 1688 };

interface Shot {
  readonly name: string;
  readonly page: string;
  readonly viewport?: { width: number; height: number };
  readonly colorScheme?: "dark" | "light";
  readonly lang?: "en" | "fa";
  readonly reducedMotion?: "reduce";
}

const SHOTS: readonly Shot[] = [
  { name: "explore-dark", page: "explore.html", colorScheme: "dark" },
  { name: "explore-light", page: "explore.html", colorScheme: "light" },
  { name: "explore-fa", page: "explore.html", colorScheme: "dark", lang: "fa" },
  { name: "focus-dark", page: "focus.html", colorScheme: "dark" },
  { name: "focus-light", page: "focus.html", colorScheme: "light" },
  { name: "focus-fa", page: "focus.html", colorScheme: "dark", lang: "fa" },
  { name: "states-dark", page: "states.html", colorScheme: "dark" },
  // The breakpoints the Phase 2 browser gate already tests.
  { name: "explore-1440", page: "explore.html", colorScheme: "dark", viewport: { width: 1440, height: 900 } },
  { name: "focus-1440", page: "focus.html", colorScheme: "dark", viewport: { width: 1440, height: 900 } },
  { name: "focus-390", page: "focus.html", colorScheme: "dark", viewport: { width: 390, height: 844 } },
];

/**
 * The mockups are ES modules, and a module cannot be fetched over `file://` --
 * the browser refuses it as a cross-origin request. Serve the directory over
 * loopback instead, which is also what ADR 0001 invariant 9 requires of
 * anything this project binds.
 */
const TYPES: Record<string, string> = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
};

async function serve(root: string): Promise<{ origin: string; close: () => Promise<void> }> {
  const server = http.createServer((request, response) => {
    const name = decodeURIComponent((request.url ?? "/").split("?")[0]);
    const file = path.join(root, path.normalize(name).replace(/^(\.\.[/\\])+/, ""));
    if (!file.startsWith(root)) {
      response.writeHead(403).end();
      return;
    }
    fs.readFile(file).then(
      (body) => {
        response.writeHead(200, { "content-type": TYPES[path.extname(file)] ?? "application/octet-stream" });
        response.end(body);
      },
      () => response.writeHead(404).end(),
    );
  });
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const address = server.address();
  if (address === null || typeof address === "string") throw new Error("no port");
  return {
    origin: `http://127.0.0.1:${address.port}`,
    close: () => new Promise<void>((resolve) => server.close(() => resolve())),
  };
}

async function capture(browser: Browser, shot: Shot, origin: string): Promise<void> {
  const viewport = shot.viewport ?? REVIEW;
  const context = await browser.newContext({
    viewport,
    colorScheme: shot.colorScheme ?? "dark",
    reducedMotion: shot.reducedMotion,
    deviceScaleFactor: 1,
    locale: shot.lang === "fa" ? "fa-IR" : "en-GB",
  });
  const page = await context.newPage();
  const problems: string[] = [];
  page.on("pageerror", (error) => problems.push(String(error)));
  page.on("console", (message) => {
    if (message.type() === "error") problems.push(message.text());
  });

  const query = shot.lang === "fa" ? "?lang=fa" : "";
  await page.goto(`${origin}/${shot.page}${query}`, { waitUntil: "load" });
  // The mockups measure the stage and lay out from it, so give layout a frame
  // to settle before reading pixels.
  await page.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r))));

  const file = path.join(OUT, `${shot.name}.png`);
  await page.screenshot({ path: file, fullPage: false });
  await context.close();

  if (problems.length > 0) {
    throw new Error(`${shot.name} produced console errors:\n  ${problems.join("\n  ")}`);
  }
  console.log(`  ${shot.name.padEnd(16)} ${viewport.width}x${viewport.height}  ${file}`);
}

async function main(): Promise<void> {
  const filter = process.argv[2];
  const wanted = filter ? SHOTS.filter((s) => s.name.startsWith(filter)) : SHOTS;
  if (wanted.length === 0) throw new Error(`no capture matches ${filter}`);

  await fs.mkdir(OUT, { recursive: true });
  const site = await serve(MOCKUPS);
  const browser = await chromium.launch();
  try {
    for (const shot of wanted) await capture(browser, shot, site.origin);
  } finally {
    await browser.close();
    await site.close();
  }
  console.log(`\n${wanted.length} capture(s) written to ${OUT}`);
}

await main();
