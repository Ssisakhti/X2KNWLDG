/**
 * Lay out the T-255 Source Explore fields through the PRODUCTION path.
 *
 * The same argument `mockup_layout.ts` makes for `T-211`: the real
 * `seedPosition`, the real graphology graph and the real `forceAtlas2` with
 * `inferSettings` at `MAP_LAYOUT_ITERATIONS`, which is what `MapSession.relax()`
 * runs. A hand-rolled simulation would make the mockup an argument about a
 * picture the Map never draws.
 *
 * One deliberate difference from `mockup_layout.ts`, and it is the difference
 * that made this a second file rather than a parameter: that script reads
 * `output/library/graph.json`, so it lays out whatever library the machine
 * happens to hold. This one reads `docs/mockups/T-255/layout_input.json`, which
 * `gen_data.py` writes from committed fixtures -- so the field reproduces in a
 * clone, and re-running it cannot silently relay out the approved pictures
 * against a library that has moved.
 *
 *   npm --prefix web run mockups:source-layout
 */
import Graph from "graphology";
import forceAtlas2 from "graphology-layout-forceatlas2";
import { fileURLToPath } from "node:url";
import path from "node:path";
import fs from "node:fs";
import { seedPosition } from "../src/map/seedPositions";

/** web/src/map/mapSession.ts MAP_LAYOUT_ITERATIONS. */
const MAP_LAYOUT_ITERATIONS = 200;

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, "../..");
const MOCKUPS = path.join(ROOT, "docs/mockups/T-255");

interface Field {
  readonly nodes: string[];
  readonly edges: [string, string][];
}

const input = JSON.parse(
  fs.readFileSync(path.join(MOCKUPS, "layout_input.json"), "utf8"),
) as Record<string, Field>;

const out: Record<string, Record<string, { x: number; y: number }>> = {};

for (const [name, field] of Object.entries(input)) {
  // `multi: true, type: "directed"` matches web/src/map/graphProjection.ts, so
  // two sources joined by two relations keep both edges and the layout feels
  // their combined pull exactly as the real one does.
  const graph = new Graph({ multi: true, type: "directed" });
  for (const node of field.nodes) {
    const { x, y } = seedPosition(node);
    graph.addNode(node, { x, y });
  }
  for (const [from, to] of field.edges) {
    if (!graph.hasNode(from) || !graph.hasNode(to)) continue;
    graph.addEdge(from, to);
  }
  forceAtlas2.assign(graph, {
    iterations: MAP_LAYOUT_ITERATIONS,
    settings: forceAtlas2.inferSettings(graph),
  });
  const positions: Record<string, { x: number; y: number }> = {};
  graph.forEachNode((key, attrs) => {
    positions[key] = { x: attrs.x as number, y: attrs.y as number };
  });
  out[name] = positions;
  console.log(`${name}: ${graph.order} nodes / ${graph.size} edges`);
}

const file = path.join(MOCKUPS, "layout.json");
fs.writeFileSync(file, `${JSON.stringify(out, null, 1)}\n`);
console.log(`-> ${file}`);
