/**
 * The page `T-255` is approved or refused on.
 *
 * `review_sheet.ts` builds a *comparison* — the running build beside an approved
 * mockup — which is `T-215`'s question. `T-255` has no build to compare against
 * and no approved set yet: its question is "may this be built", so this page is
 * one set, in the order a reviewer should meet it, with what each picture is
 * there to answer written beside it.
 *
 * It is a script and not a spec: it asserts nothing, `npm run browser` does not
 * run it, and it writes into a gitignored file beside gitignored captures, both
 * regenerated from committed sources:
 *
 *   .venv/bin/python docs/mockups/T-255/gen_data.py
 *   npm --prefix web run mockups:source-layout
 *   npm --prefix web run mockups:source-capture
 *   npm --prefix web run mockups:source-review
 */
import { fileURLToPath } from "node:url";
import path from "node:path";
import fs from "node:fs/promises";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const CAPTURES = path.resolve(HERE, "../../docs/mockups/T-255/captures");
const OUT = path.resolve(HERE, "../../docs/mockups/T-255/review.html");

interface Shot {
  readonly name: string;
  readonly note: string;
}

/** The order matters: what the API answers today comes before what was written. */
const ORDER: readonly Shot[] = [
  {
    name: "explore-served-dark",
    note: "What the two endpoints answer today, with nothing added: four sources and one gated relationship. Every later Explore picture is this plus written judgements.",
  },
  {
    name: "focus-served-dark",
    note: "The same, focused. One readable source card carrying a real Persian brief whose every statement names the knowledge units under it; one real relationship with its real basis.",
  },
  {
    name: "explore-dense-dark",
    note: "Ten real sources, thirteen written relationships, disclosed on the face of the picture. One mark per source, one weight per edge — a basis count is a count.",
  },
  {
    name: "focus-dense-dark",
    note: "The Directional Orbit: incoming where reading starts, outgoing opposite, direction read from the focus's own end. The drawer carries one relationship's basis pair by pair.",
  },
  {
    name: "focus-dense-fa",
    note: "Persian. The composition mirrors and the identifiers do not (D-012). The brief is Persian in BOTH locales, because the record is — that is the output-language policy, drawn.",
  },
  {
    name: "explore-dense-fa",
    note: "The field, mirrored, with two Persian-labelled sources beside Latin ids.",
  },
  {
    name: "focus-rtl-label",
    note: "A real committed run whose title is Persian with a ZWNJ, focused in the Persian UI — and it has no brief, which is why an RTL label beside a Persian card had to be built rather than found.",
  },
  { name: "explore-dense-light", note: "The field in light." },
  { name: "focus-dense-light", note: "The orbit in light: the focused card keeps a tinted ground as well as its ring." },
  {
    name: "focus-partial",
    note: "A brief at PARTIAL. A brief may never claim more than the run it was written from, so this is a state to draw rather than a shortfall to hide.",
  },
  {
    name: "focus-unavailable",
    note: "A run that did not pass has no brief, and no relationships. Both absences are stated in words; neither is an error.",
  },
  {
    name: "focus-bound",
    note: "A bounded neighbourhood: `truncated: true`, and the note says the limit bound BOTH directions together in id order (D-272).",
  },
  {
    name: "explore-dense-1440",
    note: "The compact tier's field. The legend and the disclosure fold to their triggers here — un-folded they took 19.2% of the field and left the graph 299px of height.",
  },
  {
    name: "focus-dense-1440",
    note: "The compact tier's orbit: two cards a side, two counted, and the relationship pill moves into the card because there is no clear run of edge to ride.",
  },
  {
    name: "focus-dense-390",
    note: "Below the orbit's floor there is no orbit. Every relationship is a row, six are counted as unplaced, and none is dropped.",
  },
  {
    name: "focus-dense-reduced-motion",
    note: "The same composition under `prefers-reduced-motion`. Nothing here animates, so nothing changes — captured to prove it rather than to assert it.",
  },
  {
    name: "states-dark",
    note: "Twelve honest states, each labelled with the machine-readable state it is drawn from. The no-WebGL row is the Knowledge Map's own shipped string: the whole reading path is DOM.",
  },
  { name: "states-fa", note: "The same states in Persian." },
  { name: "states-light", note: "The same states in light." },
  { name: "explore-served-light", note: "The served field in light, for completeness." },
];

const escape = (value: string): string =>
  value.replace(/[&<>"]/g, (c) =>
    c === "&" ? "&amp;" : c === "<" ? "&lt;" : c === ">" ? "&gt;" : "&quot;");

async function main(): Promise<void> {
  const present = new Set(
    (await fs.readdir(CAPTURES).catch(() => [] as string[]))
      .filter((name) => name.endsWith(".png"))
      .map((name) => name.replace(/\.png$/, "")),
  );
  if (present.size === 0) {
    throw new Error(`no captures in ${CAPTURES} — run mockups:source-capture first`);
  }

  const listed = new Set(ORDER.map((shot) => shot.name));
  const extra = [...present].filter((name) => !listed.has(name)).sort();
  const missing = ORDER.filter((shot) => !present.has(shot.name)).map((shot) => shot.name);

  const figure = (name: string, note: string): string => {
    const file = path.relative(path.dirname(OUT), path.join(CAPTURES, `${name}.png`));
    return `<section>
  <h2>${escape(name)}</h2>
  <p>${escape(note)}</p>
  <a href="${file}"><img src="${file}" alt="${escape(name)}"></a>
</section>`;
  };

  const body = [
    ...ORDER.filter((shot) => present.has(shot.name)).map((shot) => figure(shot.name, shot.note)),
    ...extra.map((name) => figure(name, "Captured but not in the review order — added since this page was written.")),
  ].join("\n");

  const page = `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>T-255 — Source Explore and Focus, for approval</title>
<style>
  :root { color-scheme: dark light; }
  body { margin: 0; padding: 2rem clamp(1rem, 4vw, 4rem) 6rem;
         font: 15px/1.55 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
         background: #17161a; color: #ece9e4; }
  h1 { font-size: 1.5rem; margin: 0 0 .25rem; }
  .lead { color: #a9a49c; max-inline-size: 92ch; margin: 0 0 2rem; }
  .lead code { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: .85em; }
  section { margin-block-end: 3rem; }
  h2 { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: .9rem;
       color: #82b1e0; margin: 0 0 .25rem; }
  section p { color: #a9a49c; max-inline-size: 92ch; margin: 0 0 .75rem; }
  img { display: block; inline-size: 100%; block-size: auto;
        border: 1px solid #35333a; border-radius: 10px; }
  .warn { border: 1px dashed #e2b95f; color: #e2b95f; border-radius: 8px;
          padding: .75rem 1rem; margin-block-end: 2rem; max-inline-size: 92ch; }
  @media (prefers-color-scheme: light) {
    body { background: #fbfaf8; color: #1c1a17; }
    .lead, section p { color: #5e5851; }
    h2 { color: #2f5d8a; }
    img { border-color: #ded9d2; }
  }
</style>
</head>
<body>
<h1>T-255 — Source Explore and Source Focus</h1>
<p class="lead">
  Every picture below is drawn from the two served source-graph reads. The first two are
  <strong>entirely real</strong> — four sources and the one gated relationship the fixtures hold.
  The dense ones carry ten real source nodes and thirteen relationships that were
  <strong>written for this mockup</strong>, disclosed in the picture itself, because real
  discovery over every committed fixture run proposes three pairs and no cross-medium pair at
  all. The full argument, the measured geometry and the differences from the approved T-211 set
  are in <code>docs/mockups/T-255/SPEC.md</code>.
</p>
${missing.length > 0 ? `<p class="warn">Missing capture(s): ${escape(missing.join(", "))} — re-run <code>mockups:source-capture</code>.</p>` : ""}
${body}
</body>
</html>
`;
  await fs.writeFile(OUT, page, "utf8");
  console.log(`${present.size} capture(s) -> ${OUT}`);
  if (missing.length > 0) console.log(`missing: ${missing.join(", ")}`);
}

main().catch((error: unknown) => {
  console.error(error);
  process.exitCode = 1;
});
