/**
 * The comparison `T-215` is accepted or refused on.
 *
 * ADR 0006 clause 5 asks for "real browser captures compared with the approved
 * mockups at actual viewports". The comparing is a person's job; this builds
 * the page they do it on -- every capture the gate produced, beside the
 * approved source of the same name, at the same scale, in one scroll.
 *
 * It is a script and not a spec: it asserts nothing, `npm run browser` does not
 * run it, and it writes into a gitignored directory. Both sets of pictures are
 * build products of committed sources (D-191), so the page is regenerated
 * rather than kept:
 *
 *   npx tsx web/scripts/capture_mockups.ts                 # the approved set
 *   X2KNWLDG_BROWSER_PROJECT_ROOT=.. npx playwright test visual.spec.ts
 *   npx tsx web/scripts/review_sheet.ts                    # this page
 *
 * The second command is pointed at the real library on purpose: the mockups
 * compose `KU-000028` out of the 86-node graph, and a capture of the committed
 * seven-node fixtures would be a picture of a different graph -- green, and
 * useless as a comparison.
 */
import { fileURLToPath } from "node:url";
import path from "node:path";
import fs from "node:fs/promises";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const MOCKUPS = path.resolve(HERE, "../../docs/mockups/T-211/captures");
const BUILDS = path.resolve(HERE, "../../docs/mockups/T-215/captures");
const OUT = path.resolve(HERE, "../../docs/mockups/T-215/review.html");

/** What each pair is for, in the order a reviewer should meet them. */
const ORDER: readonly { name: string; note: string }[] = [
  { name: "explore-dark", note: "The quiet overview at the review viewport (ADR 0006 clause 3)." },
  { name: "focus-dark", note: "The Directional Orbit: incoming start, outgoing end, hops as radius." },
  { name: "focus-light", note: "The same hierarchy in light." },
  { name: "explore-light", note: "The overview in light." },
  { name: "focus-fa", note: "Persian: the composition mirrors, the identifiers do not (D-012)." },
  { name: "explore-fa", note: "The overview, mirrored." },
  { name: "explore-1440", note: "The compact tier's overview." },
  { name: "focus-1440", note: "The compact tier: two cards a side, the rest counted." },
  {
    name: "focus-390",
    note: "Below the orbit's floor: every relation as a row, none dropped — captured on a coarse pointer.",
  },
  { name: "states-dark", note: "The honest states." },
];

/** A build capture with no approved counterpart is still worth looking at. */
const EXTRA: readonly { name: string; note: string }[] = [
  { name: "focus-search", note: "Searching while focused: the rail grows and one card is refused and counted." },
  { name: "focus-reduced-motion", note: "The same composition for a reader who asked for less motion." },
  { name: "focus-keyboard", note: "Reached with no pointer at all." },
  { name: "focus-1280", note: "The compact tier at the gate's own default viewport." },
  { name: "states-unavailable", note: "A browser that cannot draw: still a workspace." },
  { name: "states-partial", note: "A graph one page in." },
];

async function exists(file: string): Promise<boolean> {
  try {
    await fs.access(file);
    return true;
  } catch {
    return false;
  }
}

function escape(text: string): string {
  return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

async function main(): Promise<void> {
  const rows: string[] = [];
  for (const { name, note } of ORDER) {
    const mockup = path.join(MOCKUPS, `${name}.png`);
    const build = path.join(BUILDS, `${name}.png`);
    const haveMockup = await exists(mockup);
    const haveBuild = await exists(build);
    if (!haveMockup && !haveBuild) continue;
    rows.push(`<section>
  <h2>${escape(name)}</h2>
  <p>${escape(note)}</p>
  <div class="pair">
    <figure><figcaption>Approved mockup (T-211)</figcaption>${
      haveMockup
        ? `<a href="${path.relative(path.dirname(OUT), mockup)}"><img src="${path.relative(path.dirname(OUT), mockup)}" alt="${escape(name)} mockup"></a>`
        : "<p class=missing>not captured — run capture_mockups.ts</p>"
    }</figure>
    <figure><figcaption>Running build (T-215)</figcaption>${
      haveBuild
        ? `<a href="${path.relative(path.dirname(OUT), build)}"><img src="${path.relative(path.dirname(OUT), build)}" alt="${escape(name)} build"></a>`
        : "<p class=missing>not captured — run the visual gate</p>"
    }</figure>
  </div>
</section>`);
  }

  const extras: string[] = [];
  for (const { name, note } of EXTRA) {
    const build = path.join(BUILDS, `${name}.png`);
    if (!(await exists(build))) continue;
    extras.push(`<section>
  <h2>${escape(name)}</h2>
  <p>${escape(note)}</p>
  <figure><figcaption>Running build (T-215) — no approved counterpart</figcaption><a href="${path.relative(path.dirname(OUT), build)}"><img src="${path.relative(path.dirname(OUT), build)}" alt="${escape(name)} build"></a></figure>
</section>`);
  }

  const page = `<!doctype html>
<html lang="en">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>T-215 — the build beside the approved compositions</title>
<style>
  :root { color-scheme: dark; }
  body { margin: 0 auto; padding: 2rem; max-width: 1800px; background: #14161a; color: #e6e8ec;
         font: 15px/1.55 ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif; }
  h1 { font-size: 1.4rem; }
  h2 { font-size: 1rem; letter-spacing: .08em; text-transform: uppercase; color: #9aa3b2; margin-bottom: .2rem; }
  p { color: #b9c0cc; margin: .2rem 0 1rem; }
  section { margin: 2.5rem 0; border-top: 1px solid #262a31; padding-top: 1.2rem; }
  .pair { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }
  figure { margin: 0; }
  figcaption { font-size: .8rem; color: #8a93a2; margin-bottom: .35rem; }
  img { width: 100%; height: auto; border: 1px solid #2b3038; border-radius: 6px; display: block; }
  .missing { color: #d08b6a; }
  .lead { max-width: 70ch; }
  code { background: #1d2026; padding: .1em .35em; border-radius: 4px; }
</style>
<h1>T-215 — the running build beside the approved compositions</h1>
<p class="lead">Left is what was approved in <code>T-211</code> (D-191); right is what the
browser drew, captured by <code>browser/visual.spec.ts</code> over the real library. The
geometry clauses are asserted by that gate; what this page is for is the judgement it cannot
make — whether the build materially matches the hierarchy, polish and legibility of the
reference set. Click a picture for it at full size.</p>
${rows.join("\n")}
<h1>Scenarios the mockups do not cover</h1>
${extras.join("\n")}
</html>
`;

  await fs.mkdir(path.dirname(OUT), { recursive: true });
  await fs.writeFile(OUT, page, "utf8");
  console.log(`${rows.length} pair(s) and ${extras.length} extra(s) written to ${OUT}`);
}

await main();
