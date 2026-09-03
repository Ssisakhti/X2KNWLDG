/**
 * Lay out the Explore field for the T-211 mockups using the PRODUCTION code
 * path rather than an imitation of it: the real `seedPosition`, the real
 * graphology graph, and the real `forceAtlas2` with `inferSettings` at
 * `MAP_LAYOUT_ITERATIONS` -- which is exactly what `MapSession.relax()` runs.
 *
 * A hand-rolled force simulation was tried first and produced a field that
 * looked nothing like the renderer's, which would have made the mockup an
 * argument about a picture the Map never draws.
 *
 * Writes positions keyed by `global_id`; gen_data.py folds them into data.js.
 *
 *   npx tsx web/scripts/mockup_layout.ts
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

interface RawNode { id: string; global_id: string }
interface RawEdge { from: string; to: string }

const raw = JSON.parse(
  fs.readFileSync(path.join(ROOT, "output/library/graph.json"), "utf8"),
) as { nodes: RawNode[]; edges: RawEdge[] };

// `multi: true, type: "directed"` matches web/src/map/graphProjection.ts, so a
// pair of nodes joined by two different relations keeps both edges and the
// layout feels their combined pull exactly as the real one does.
const graph = new Graph({ multi: true, type: "directed" });
for (const node of raw.nodes) {
  const { x, y } = seedPosition(node.global_id);
  graph.addNode(node.global_id, { x, y });
}
const byLibraryId = new Map(raw.nodes.map((n) => [n.id, n.global_id]));
for (const edge of raw.edges) {
  const from = byLibraryId.get(edge.from);
  const to = byLibraryId.get(edge.to);
  if (from === undefined || to === undefined) continue;
  graph.addEdge(from, to);
}

forceAtlas2.assign(graph, {
  iterations: MAP_LAYOUT_ITERATIONS,
  settings: forceAtlas2.inferSettings(graph),
});

const out: Record<string, { x: number; y: number }> = {};
graph.forEachNode((key, attrs) => {
  out[key] = { x: attrs.x as number, y: attrs.y as number };
});

const file = path.join(ROOT, "docs/mockups/T-211/layout.json");
fs.writeFileSync(file, `${JSON.stringify(out, null, 1)}\n`);
console.log(`${graph.order} nodes / ${graph.size} edges laid out -> ${file}`);
