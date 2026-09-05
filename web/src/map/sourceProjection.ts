/**
 * `GET /api/source-graph`'s body, as the thing Sigma draws (`T-256`).
 *
 * `graphProjection`'s one rule holds here unchanged: **a projected record is
 * the API's record.** A node carries the `EntityRef` it came from and an edge
 * carries its `SourceRelationSummary`, neither flattened, renamed nor filled
 * in. The only computed values are the seed positions, which are presentation
 * and are seeded at insertion for the reason that module states — a node
 * inserted without one becomes `NaN` in ForceAtlas2's `Float32Array`, silently.
 *
 * Two things are this module's own, and both are about what a page of a graph
 * may claim.
 *
 * **A relation whose endpoint is not on this page is not drawn.** The
 * neighbourhood response carries an `EntityRef` for every endpoint it names, but
 * the *graph* pages over nodes: a relation set is returned whole while the node
 * list is cut, so a page can hold a relation naming a source that is on a later
 * page. Drawing it would need a mark for a node this page has no record of, and
 * inventing one is the failure ADR 0002 is emphatic about. It is skipped and
 * **counted**, and the count is the reason `offPage` exists rather than the
 * relation being dropped in silence.
 *
 * **`relations_omitted` is not the same number.** That one is the server's —
 * the bound's cut, or an endpoint the index does not hold — and it arrives in
 * `counts`. `offPage` is this client's, about this page. Two numbers because
 * they answer two questions, and adding them would produce a third that answers
 * neither.
 */

import { MultiDirectedGraph } from "graphology";

import type { EntityRef, SourceGraphPayload, SourceRelationSummary } from "../api/contract";
import { type MapEdgeAttributes, type MapNodeAttributes, nodeAttributes } from "./graphProjection";

export type SourceMapGraph = MultiDirectedGraph<
  MapNodeAttributes,
  MapEdgeAttributes<SourceRelationSummary>
>;

export function createSourceMapGraph(): SourceMapGraph {
  return new MultiDirectedGraph<MapNodeAttributes, MapEdgeAttributes<SourceRelationSummary>>();
}

/** What one page of the source graph became. */
export interface SourceProjection {
  readonly graph: SourceMapGraph;
  /** Every returned node, by its two-part `source_id`. */
  readonly bySourceId: ReadonlyMap<string, EntityRef>;
  /** Relations this page could not draw because an endpoint is not on it. */
  readonly offPage: readonly SourceRelationSummary[];
}

/**
 * Project one `SourceGraphPayload`.
 *
 * A whole page at a time rather than record by record, because the source graph
 * is *not* a progressive snapshot the way the Knowledge Map's is: it pages over
 * nodes and returns its relations whole, so accumulating pages into one graph
 * would keep relations from the first page whose endpoints the second page
 * re-states. One page, one picture, and `page.next_cursor` says whether there is
 * another.
 */
export function projectSourceGraph(payload: SourceGraphPayload): SourceProjection {
  const graph = createSourceMapGraph();
  const bySourceId = new Map<string, EntityRef>();

  for (const node of payload.nodes) {
    // A duplicate id in one page is the server contradicting itself. The first
    // wins and the second is ignored rather than merged: merging two records
    // under one id would produce a third record neither of them is.
    if (graph.hasNode(node.global_id)) continue;
    graph.addNode(node.global_id, nodeAttributes(node));
    if (typeof node.source_id === "string") bySourceId.set(node.source_id, node);
  }

  const offPage: SourceRelationSummary[] = [];
  for (const relation of payload.relations) {
    const from =
      relation.from_source_id === undefined ? undefined : bySourceId.get(relation.from_source_id);
    const to =
      relation.to_source_id === undefined ? undefined : bySourceId.get(relation.to_source_id);
    if (from === undefined || to === undefined) {
      offPage.push(relation);
      continue;
    }
    // Keyed by the relation's own id (ADR 0005 invariant 2), never synthesised
    // from its endpoints: two sources may stand in more than one relationship,
    // and a key built from the pair would silently keep one of them.
    if (graph.hasEdge(relation.id)) continue;
    graph.addDirectedEdgeWithKey(relation.id, from.global_id, to.global_id, {
      record: relation,
    });
  }

  return { graph, bySourceId, offPage };
}

/** Every source id this projection drew a node for, in the page's own order. */
export function drawnSourceIds(projection: SourceProjection): readonly string[] {
  return [...projection.bySourceId.keys()];
}
