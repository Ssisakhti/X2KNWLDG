/**
 * Capture the T-255 Source Map mockups at the review viewport.
 *
 * A standalone Playwright script, NOT a spec: it is not registered with the
 * browser gate, `npm run browser` does not run it, and it asserts nothing of
 * its own. What it does do is **refuse a picture the page itself calls
 * broken** — every mockup runs its acceptance clauses in the page and reports a
 * violation as a console error, and a console error fails the shot here. That
 * is how `T-211` caught four real defects before implementation, and it is the
 * only part of this script that is a gate.
 *
 *   npm --prefix web run mockups:source-capture            # every capture
 *   npm --prefix web run mockups:source-capture focus      # one page's
 *
 * It prints one measurement beside each picture: the share of the field the
 * floating chrome covers, computed by `browser/composition.ts`'s own
 * `coveredShare`, so the reference and the build are measured by one
 * implementation (D-201).
 */
import { chromium, type Browser } from "@playwright/test";
import { coveredShare } from "../browser/composition";
import { fileURLToPath } from "node:url";
import http from "node:http";
import path from "node:path";
import fs from "node:fs/promises";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, "../..");
const MOCKUPS = path.join(ROOT, "docs/mockups/T-255");
const OUT = path.join(MOCKUPS, "captures");

/** The review viewport T-211 was specified against, and this inherits. */
const REVIEW = { width: 2852, height: 1688 };

interface Shot {
  readonly name: string;
  readonly page: string;
  readonly query?: Record<string, string>;
  readonly viewport?: { width: number; height: number };
  readonly colorScheme?: "dark" | "light";
  readonly lang?: "en" | "fa";
  readonly reducedMotion?: "reduce";
}

const DENSE = { data: "dense" };

const SHOTS: readonly Shot[] = [
  // The served field: four sources and one gated relationship. This is what
  // the API actually answers today, and it is deliberately the first picture.
  { name: "explore-served-dark", page: "explore.html", colorScheme: "dark" },
  { name: "explore-served-light", page: "explore.html", colorScheme: "light" },
  // The dense field: ten real sources, thirteen written relationships.
  { name: "explore-dense-dark", page: "explore.html", query: DENSE, colorScheme: "dark" },
  { name: "explore-dense-light", page: "explore.html", query: DENSE, colorScheme: "light" },
  { name: "explore-dense-fa", page: "explore.html", query: DENSE, colorScheme: "dark", lang: "fa" },
  { name: "explore-dense-1440", page: "explore.html", query: DENSE, colorScheme: "dark", viewport: { width: 1440, height: 900 } },

  // Focus on the hub: three incoming, three outgoing, mixed scope, mixed medium.
  { name: "focus-dense-dark", page: "focus.html", query: DENSE, colorScheme: "dark" },
  { name: "focus-dense-light", page: "focus.html", query: DENSE, colorScheme: "light" },
  { name: "focus-dense-fa", page: "focus.html", query: DENSE, colorScheme: "dark", lang: "fa" },
  { name: "focus-dense-1440", page: "focus.html", query: DENSE, colorScheme: "dark", viewport: { width: 1440, height: 900 } },
  { name: "focus-dense-390", page: "focus.html", query: DENSE, colorScheme: "dark", viewport: { width: 390, height: 844 } },
  { name: "focus-dense-reduced-motion", page: "focus.html", query: DENSE, colorScheme: "dark", reducedMotion: "reduce" },

  // The served neighbourhood: one real relationship, PASS, current brief.
  { name: "focus-served-dark", page: "focus.html", colorScheme: "dark" },
  // A PARTIAL brief, and a run that has none at all.
  { name: "focus-partial", page: "focus.html", query: { source: "youtube:fixture-partial" }, colorScheme: "dark" },
  { name: "focus-unavailable", page: "focus.html", query: { source: "youtube:fixture-fail" }, colorScheme: "dark" },
  // A Persian, RTL-labelled source with no brief, in the Persian UI.
  { name: "focus-rtl-label", page: "focus.html", query: { ...DENSE, source: "twitter:2027781710667010262" }, colorScheme: "dark", lang: "fa" },
  // A bounded neighbourhood: the limit binds both directions together.
  { name: "focus-bound", page: "focus.html", query: { ...DENSE, bound: "1" }, colorScheme: "dark" },

  { name: "states-dark", page: "states.html", colorScheme: "dark" },
  { name: "states-fa", page: "states.html", colorScheme: "dark", lang: "fa" },
  { name: "states-light", page: "states.html", colorScheme: "light" },
];

/**
 * The mockups are ES modules, and a module cannot be fetched over `file://`.
 * Serve over loopback instead, which is also what ADR 0001 invariant 9 requires
 * of anything this project binds. The root is `docs/mockups/` rather than this
 * task's own directory, because T-255's stylesheet imports T-211's approved one
 * by relative path rather than copying it.
 */
const TYPES: Record<string, string> = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8",
};

async function serve(root: string): Promise<{ origin: string; close: () => Promise<void> }> {
  const server = http.createServer((request, response) => {
    const name = decodeURIComponent((request.url ?? "/").split("?")[0] ?? "/");
    const file = path.join(root, path.normalize(name).replace(/^(\.\.[/\\])+/, ""));
    if (!file.startsWith(root)) {
      response.writeHead(403).end();
      return;
    }
    fs.readFile(file).then(
      (bytes) => {
        response.writeHead(200, {
          "content-type": TYPES[path.extname(file)] ?? "application/octet-stream",
        });
        response.end(bytes);
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

  const params = new URLSearchParams({ ...(shot.query ?? {}) });
  if (shot.lang === "fa") params.set("lang", "fa");
  const query = params.toString() === "" ? "" : `?${params.toString()}`;
  await page.goto(`${origin}/T-255/${shot.page}${query}`, { waitUntil: "load" });
  await page.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r))));

  const file = path.join(OUT, `${shot.name}.png`);
  await page.screenshot({ path: file, fullPage: shot.page === "states.html" });

  // Written without a named helper for the rectangle, deliberately: `tsx`
  // compiles this file with esbuild's `keepNames`, which wraps every named
  // function in a `__name` call that does not exist in the page.
  const measured = await page.evaluate(() => {
    const stage = document.getElementById("stage");
    const stageBox = stage === null ? null : stage.getBoundingClientRect();
    const geometry = (window as unknown as { __geometry?: unknown }).__geometry ?? null;
    return {
      geometry,
      field:
        stageBox === null
          ? null
          : {
              left: stageBox.left, top: stageBox.top,
              right: stageBox.right, bottom: stageBox.bottom,
              width: stageBox.width, height: stageBox.height,
            },
      chrome: [...document.querySelectorAll(".float, .drawer")].map((node) => {
        const box = node.getBoundingClientRect();
        return {
          rect: {
            left: box.left, top: box.top, right: box.right,
            bottom: box.bottom, width: box.width, height: box.height,
          },
        };
      }),
    };
  });
  await context.close();

  if (problems.length > 0) {
    throw new Error(`${shot.name} produced console errors:\n  ${problems.join("\n  ")}`);
  }
  const share = coveredShare(measured.field, measured.chrome.map((control) => control.rect));
  const field = measured.field;
  const counts = measured.geometry as Record<string, unknown> | null;
  const summary =
    counts === null
      ? ""
      : `  ${Object.entries(counts)
          .filter(([key]) => key !== "problems")
          .map(([key, value]) => `${key}=${String(value)}`)
          .join(" ")}`;
  console.log(
    `  ${shot.name.padEnd(26)} ${viewport.width}x${viewport.height}` +
      `  field ${field === null ? "?" : `${Math.round(field.width)}x${Math.round(field.height)}`}` +
      `  chrome ${(share * 100).toFixed(1)}%${summary}`,
  );
}

async function main(): Promise<void> {
  const filter = process.argv[2];
  const wanted = filter ? SHOTS.filter((s) => s.name.startsWith(filter)) : SHOTS;
  if (wanted.length === 0) throw new Error(`no capture matches ${filter}`);

  await fs.mkdir(OUT, { recursive: true });
  const site = await serve(path.join(ROOT, "docs/mockups"));
  const browser = await chromium.launch();
  try {
    for (const shot of wanted) await capture(browser, shot, site.origin);
  } finally {
    await browser.close();
    await site.close();
  }
  console.log(`\n${wanted.length} capture(s) written to ${OUT}`);
}

main().catch((error: unknown) => {
  console.error(error);
  process.exitCode = 1;
});
