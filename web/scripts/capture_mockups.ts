/**
 * Capture the T-211 mockups at the review viewport.
 *
 * This is a standalone Playwright script, NOT a spec: it is not registered with
 * the browser gate, it asserts nothing, and `npm run browser` does not run it.
 * T-211 produces pictures for a human to approve; T-215 is where captures grow
 * assertions.
 *
 *   npm --prefix web run mockups:capture            # every capture
 *   npm --prefix web run mockups:capture explore    # one page's captures
 *
 * It prints one measurement beside each picture, and that measurement is the
 * source of a number the browser gate asserts (`T-216`): the share of the
 * field the approved composition's floating chrome covers. The bound the gate
 * holds the build to is read off these captures rather than chosen, so it has
 * to be re-readable from the committed mockups -- and it is read with
 * `browser/composition.ts`'s own `coveredShare`, so the reference and the
 * build are measured by one implementation.
 */
import { chromium, type Browser } from "@playwright/test";
import { coveredShare } from "../browser/composition";
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
    // `split` can yield `undefined` under `noUncheckedIndexedAccess`, and a
    // `path.join(root, undefined)` throws inside the request handler — an
    // unhandled rejection that takes the capture run down with no output.
    // Found by `scripts/tsconfig.json`, which is the first program to type-check
    // this file at all (D-203).
    const name = decodeURIComponent((request.url ?? "/").split("?")[0] ?? "/");
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

  // The mockups' own chrome, named by the classes they use for it: `.float`
  // for every corner surface and `.drawer` for the one primary drawer. The
  // production route marks the same thing with `data-map-chrome`; the two
  // selectors differ because the two documents do, and the arithmetic that
  // turns them into a share is the one both read.
  //
  // Written without a named helper for the rectangle, deliberately: `tsx`
  // compiles this file with esbuild's `keepNames`, which wraps every function
  // bound to a name in a `__name` call that does not exist in the page, and
  // the evaluation then dies with a `ReferenceError` about `__name`.
  // `browser/composition.ts` records the same trap for the same reason.
  const measured = await page.evaluate(() => {
    const stage = document.getElementById("stage");
    const stageBox = stage === null ? null : stage.getBoundingClientRect();
    return {
      field:
        stageBox === null
          ? null
          : {
              left: stageBox.left,
              top: stageBox.top,
              right: stageBox.right,
              bottom: stageBox.bottom,
              width: stageBox.width,
              height: stageBox.height,
            },
      chrome: [...document.querySelectorAll(".float, .drawer")].map((node) => {
        const box = node.getBoundingClientRect();
        return {
          name: node.className,
          rect: {
            left: box.left,
            top: box.top,
            right: box.right,
            bottom: box.bottom,
            width: box.width,
            height: box.height,
          },
        };
      }),
    };
  });
  await context.close();

  if (problems.length > 0) {
    throw new Error(`${shot.name} produced console errors:\n  ${problems.join("\n  ")}`);
  }
  const share = coveredShare(
    measured.field,
    measured.chrome.map((control) => control.rect),
  );
  const field = measured.field;
  console.log(
    `  ${shot.name.padEnd(16)} ${viewport.width}x${viewport.height}` +
      `  field ${field === null ? "?" : `${Math.round(field.width)}x${Math.round(field.height)}`}` +
      `  chrome ${(share * 100).toFixed(1)}% of it` +
      `  (${measured.chrome.length} surfaces)  ${file}`,
  );
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
