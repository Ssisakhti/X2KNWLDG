/**
 * The smallest honest conversion from one `/api/graph` page into a graphology
 * graph -- for the `T-202` compatibility gate only.
 *
 * **This is not the `T-203` projection and must not grow into it.** `T-203`
 * owns the typed, tested conversion: preserved `global_id`s and edge ids,
 * direction, parallel edges, intentional self-loops, nulls, canonical paths,
 * page accumulation, conflict refusal, and holding an edge off-canvas until
 * both endpoints have arrived. This module exists to answer one narrower
 * question -- does the pinned renderer draw and tear down the real graph -- and
 * it answers it over a single page.
 *
 * What it does carry over from that specification, because the gate would
 * otherwise report a false result:
 *
 * - `MultiDirectedGraph`, so the 118 real edges include parallel ones without
 *   silently collapsing to one.
 * - Nodes keyed by `global_id` and edges by their own `id`, so a count on the
 *   canvas can be compared with a count from the API.
 * - An edge whose endpoint is not on this page is **counted and skipped**, not
 *   dropped quietly and not given an invented far node (D-059).
 * - Every node is seeded at insertion, because a node with no position becomes
 *   `NaN` inside ForceAtlas2 with no error raised (see `seedPositions`).
 */

import { MultiDirectedGraph } from "graphology";

import type { EntityRef, GraphPayload, IndexedRelation } from "../../api/contract";
import { seedPosition } from "../seedPositions";

/**
 * Sigma's default styles bind `size` to the node attribute of that name with a
 * default of 10. The gate sets it explicitly at insertion so the update and
 * selection passes have a stated value to move away from and back to, rather
 * than toggling against a default held inside the renderer.
 */
export const GATE_NODE_SIZE = 10;

export interface GateNodeAttributes {
  label: string;
  x: number;
  y: number;
  size: number;
  entity_type: EntityRef["entity_type"];
  provenance_class: EntityRef["provenance_class"];
  kind: string | null;
}

export interface GateEdgeAttributes {
  relation: string;
  relation_vocabulary: IndexedRelation["relation_vocabulary"];
  provenance_class: IndexedRelation["provenance_class"];
}

export type GateGraph = MultiDirectedGraph<GateNodeAttributes, GateEdgeAttributes>;

/** What the page states about the graph it actually drew. */
export interface GateGraphReport {
  nodesReturned: number;
  edgesReturned: number;
  nodesDrawn: number;
  edgesDrawn: number;
  /** Edges whose `from_id` or `to_id` is not a node on this page (D-059). */
  edgesWithMissingEndpoint: number;
  /** Repeated identities, which a single page should not contain at all. */
  duplicateNodeIds: number;
  duplicateEdgeIds: number;
  selfLoops: number;
  truncated: boolean;
}

/**
 * A node's display text, or its `local_id` when the API states no label.
 *
 * Never a summary and never an id dressed up as prose: `library.py` already
 * chose the label, and a node the index has no label for says so by falling
 * back to the identifier it does have.
 */
export function gateLabel(node: EntityRef): string {
  const label = node.label ?? null;
  return label !== null && label.trim() !== "" ? label : node.local_id;
}

export function buildGateGraph(payload: GraphPayload): {
  graph: GateGraph;
  report: GateGraphReport;
} {
  const graph: GateGraph = new MultiDirectedGraph<GateNodeAttributes, GateEdgeAttributes>();
  let duplicateNodeIds = 0;
  let duplicateEdgeIds = 0;
  let edgesWithMissingEndpoint = 0;
  let selfLoops = 0;

  for (const node of payload.nodes) {
    if (graph.hasNode(node.global_id)) {
      duplicateNodeIds += 1;
      continue;
    }
    const { x, y } = seedPosition(node.global_id);
    graph.addNode(node.global_id, {
      label: gateLabel(node),
      x,
      y,
      size: GATE_NODE_SIZE,
      entity_type: node.entity_type,
      provenance_class: node.provenance_class,
      kind: node.kind ?? null,
    });
  }

  for (const edge of payload.edges) {
    if (graph.hasEdge(edge.id)) {
      duplicateEdgeIds += 1;
      continue;
    }
    if (!graph.hasNode(edge.from_id) || !graph.hasNode(edge.to_id)) {
      edgesWithMissingEndpoint += 1;
      continue;
    }
    if (edge.from_id === edge.to_id) selfLoops += 1;
    graph.addDirectedEdgeWithKey(edge.id, edge.from_id, edge.to_id, {
      relation: edge.relation,
      relation_vocabulary: edge.relation_vocabulary,
      provenance_class: edge.provenance_class,
    });
  }

  return {
    graph,
    report: {
      nodesReturned: payload.nodes.length,
      edgesReturned: payload.edges.length,
      nodesDrawn: graph.order,
      edgesDrawn: graph.size,
      edgesWithMissingEndpoint,
      duplicateNodeIds,
      duplicateEdgeIds,
      selfLoops,
      truncated: payload.truncated,
    },
  };
}
