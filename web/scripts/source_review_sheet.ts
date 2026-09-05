/**
 * The comparison `T-257` is accepted or refused on.
 *
 * Two pages have lived at this path. `T-255`'s asked "may this be built" and
 * showed one set of proposals; this one asks ADR 0006 clause 5's question of the
 * finished surface — *the running build beside the approved compositions, at
 * actual viewports* — and shows two. The earlier page is regenerable from the
 * same committed sources whenever the proposal itself needs re-reading; what a
 * phase gate needs is the pair.
 *
 * The comparing is a person's job. This builds the page they do it on, and it is
 * a script and not a spec: it asserts nothing, `npm run browser` does not run
 * it, and it writes a gitignored file beside gitignored captures, both build
 * products of committed sources (D-191):
 *
 *   .venv/bin/python docs/mockups/T-255/gen_data.py     # the approved set's data
 *   npm --prefix web run mockups:source-layout
 *   npm --prefix web run mockups:source-capture         # the approved captures
 *   npx playwright test browser/sourceVisual.spec.ts    # the build's captures
 *   npm --prefix web run mockups:source-review          # this page
 *
 * **The pairing is deliberately incomplete, and the page says so where it is.**
 * `T-255`'s Focus drew a Directional Orbit; `T-256` built a drawer (D-283). So
 * the Focus rows are a comparison of two different compositions rather than of
 * one composition drawn twice, and a reviewer who is not told that is being
 * invited to read a recorded decision as a regression. The note on each such row
 * carries it.
 */
import { fileURLToPath } from "node:url";
import path from "node:path";
import fs from "node:fs/promises";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const APPROVED = path.resolve(HERE, "../../docs/mockups/T-255/captures");
const BUILDS = path.resolve(HERE, "../../docs/mockups/T-257/captures");
const OUT = path.resolve(HERE, "../../docs/mockups/T-255/review.html");

interface Row {
  /** The build capture, written by `browser/sourceVisual.spec.ts`. */
  readonly build: string;
  /** The approved capture of the same scene, when there is one. */
  readonly approved?: string;
  readonly note: string;
}

/** Every pair, in the order a reviewer should meet them. */
const ORDER: readonly Row[] = [
  {
    build: "source-explore-dark",
    approved: "explore-served-dark",
    note:
      "Explore at the review viewport, over the served library on both sides — the approved " +
      "capture and the build are drawing the same four sources and the same one relationship, " +
      "so this row is a like-for-like comparison and is the right one to start on.",
  },
  {
    build: "source-explore-light",
    approved: "explore-served-light",
    note: "The same overview in light.",
  },
  {
    build: "source-explore-fa",
    approved: "explore-dense-fa",
    note:
      "Persian: the composition mirrors and the identifiers do not (D-012). The approved " +
      "capture is the dense synthetic field, so compare the mirroring rather than the graph.",
  },
  {
    build: "source-focus-dark",
    approved: "focus-served-dark",
    note:
      "Focus. **The compositions differ by decision, not by defect (D-283):** the approved " +
      "picture seats neighbour cards and relation pills on the field; the build carries the " +
      "readable card, the relationship list and the basis in one drawer. What to judge is " +
      "whether the drawer reads as well as the orbit would have — the brief with a knowledge-" +
      "unit chip on every statement, direction and scope in words, and the grounds beneath.",
  },
  {
    build: "source-focus-light",
    note: "The same reading in light; no approved counterpart at this scene.",
  },
  {
    build: "source-focus-fa",
    approved: "focus-rtl-label",
    note:
      "A Persian brief beside Latin identifiers, mirrored. This is the row the output-language " +
      "policy is visible on: the chrome is Persian here and the brief is Persian in both " +
      "locales, because the record is.",
  },
  {
    build: "source-explore-1440",
    approved: "explore-dense-1440",
    note: "The compact tier's overview: the legend and disclosures fold to their triggers.",
  },
  {
    build: "source-focus-1440",
    approved: "focus-dense-1440",
    note: "The compact tier's reading.",
  },
  {
    build: "source-focus-1280",
    note: "The compact tier at the gate's own default viewport; no approved counterpart.",
  },
  {
    build: "source-focus-390",
    approved: "focus-dense-390",
    note:
      "A phone. Below the compact minimum the route is its own document and scrolls (D-153), " +
      "and every returned relationship is still a row — none is dropped for want of room.",
  },
  {
    build: "source-focus-reduced-motion",
    note:
      "The same composition for a reader who asked for less motion. It must be " +
      "indistinguishable from source-focus-dark: the preference removes the camera's easing, " +
      "never anything the picture says.",
  },
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

/** `**bold**` in a note, because two of them carry the load-bearing caveat. */
function emphasise(text: string): string {
  return escape(text).replace(/\*\*(.+?)\*\*/gu, "<strong>$1</strong>");
}

function figure(caption: string, file: string | null, alt: string): string {
  if (file === null) {
    return `<figure><figcaption>${escape(caption)}</figcaption><p class=missing>not captured</p></figure>`;
  }
  const href = path.relative(path.dirname(OUT), file);
  return `<figure><figcaption>${escape(caption)}</figcaption><a href="${href}"><img src="${href}" alt="${escape(alt)}"></a></figure>`;
}

async function main(): Promise<void> {
  const sections: string[] = [];
  let paired = 0;
  for (const row of ORDER) {
    const build = path.join(BUILDS, `${row.build}.png`);
    const approved = row.approved === undefined ? null : path.join(APPROVED, `${row.approved}.png`);
    const haveBuild = await exists(build);
    const haveApproved = approved !== null && (await exists(approved));
    if (!haveBuild && !haveApproved) continue;
    if (haveBuild && haveApproved) paired += 1;
    sections.push(`<section>
  <h2>${escape(row.build)}</h2>
  <p>${emphasise(row.note)}</p>
  <div class="pair">
    ${figure(
      row.approved === undefined
        ? "Approved composition (T-255) — none for this scene"
        : `Approved composition (T-255) — ${row.approved}`,
      haveApproved ? approved : null,
      `${row.approved ?? row.build} approved`,
    )}
    ${figure("Running build (T-257)", haveBuild ? build : null, `${row.build} build`)}
  </div>
</section>`);
  }

  const page = `<!doctype html>
<html lang="en">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>T-257 — the Source Map beside the compositions it was approved from</title>
<style>
  :root { color-scheme: dark; }
  body { margin: 0 auto; padding: 2rem; max-width: 1800px; background: #14161a; color: #e6e8ec;
         font: 15px/1.55 ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif; }
  h1 { font-size: 1.4rem; }
  h2 { font-size: 1rem; letter-spacing: .08em; text-transform: uppercase; color: #9aa3b2; margin-bottom: .2rem; }
  p { color: #b9c0cc; margin: .2rem 0 1rem; max-width: 100ch; }
  section { margin: 2.5rem 0; border-top: 1px solid #262a31; padding-top: 1.2rem; }
  .pair { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }
  figure { margin: 0; }
  figcaption { font-size: .8rem; color: #8a93a2; margin-bottom: .35rem; }
  img { width: 100%; height: auto; border: 1px solid #2b3038; border-radius: 6px; display: block; }
  .missing { color: #d08b6a; }
  .lead { max-width: 80ch; }
  code { background: #1d2026; padding: .1em .35em; border-radius: 4px; }
  strong { color: #e8d5a8; }
</style>
<h1>T-257 — the Source Map beside the compositions it was approved from</h1>
<p class="lead">Left is what was approved in <code>T-255</code> (D-277); right is what the
browser drew, captured by <code>browser/sourceVisual.spec.ts</code> over the fixture corpus
the gate serves. That gate asserts the geometry — tier, direction, no two floating surfaces
over one pixel, the chrome's share of the field, the document not scrolling, and a drawer
that can be read to its foot. What this page is for is the judgement it cannot make.</p>
<p class="lead"><strong>Read the Focus rows knowing they compare two compositions, not one
drawn twice.</strong> The approved Focus is a Directional Orbit; the built one is a drawer
(D-283). The gate asserts that no orbit is drawn, so a build that grew one would fail rather
than pass quietly — the difference is a recorded decision and this is where it is put to a
reviewer.</p>
${sections.join("\n")}
</html>
`;

  await fs.mkdir(path.dirname(OUT), { recursive: true });
  await fs.writeFile(OUT, page, "utf8");
  console.log(`${sections.length} scene(s), ${paired} paired, written to ${OUT}`);
}

await main();
