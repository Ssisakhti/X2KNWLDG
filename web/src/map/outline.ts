/**
 * The drawn graph as a list (`T-208`, D-120, D-129).
 *
 * ADR 0005 pairs the WebGL surface with a DOM one, and until now the DOM half
 * of that pair could only be reached through a *query*: the search rail lists
 * what matches, the related list lists a selection's neighbourhood, and both
 * need something typed or something selected first. A reader with no pointer,
 * no WebGL2, or a screen reader therefore had the counts and no way to reach
 * the entities the counts were about -- which is "essential content exists
 * only on the canvas", the one thing `T-208`'s gate forbids outright.
 *
 * This is that missing list, and it is a projection rather than a store: the
 * rows are read from the accumulated graph on demand, the previews are
 * `previewOfEntity`'s (§8.6 allows one card-content formatter), and nothing
 * here accumulates, caches or writes.
 *
 * **The order is the API's, not a ranking.** `forEachNode` walks the graph in
 * insertion order, which is the order the pages arrived, which is the order
 * the server returned. Sorting by how connected a node is would be the
 * invented importance ADR 0005 invariant 15 forbids -- and it would reorder
 * the list under the reader every time another page arrived.
 *
 * **What it does not list, it counts.** A library larger than this Map's
 * first pages can put thousands of nodes in the graph, so the list is bounded
 * and states the bound: rows listed, nodes loaded, and how many are not on
 * this page of the outline. That is the same discipline as the stage's
 * omission report (D-132) -- a bound is allowed to cost legibility and may
 * never cost the reader the knowledge that something is there. Raising the
 * bound is a control in the DOM, so nothing is unreachable.
 *
 * Windowing (`VirtualList`) is deliberately not used. The related list's own
 * README argues the trade and it applies twice over here: a windowed list
 * keeps most rows out of the DOM, and a row that is not in the DOM is a row
 * no screen reader and no in-page search can reach -- which is what this list
 * exists to prevent.
 */

import type { MapGraph } from "./graphProjection";
import { previewOfEntity, type MapPreview } from "./useMapSearch";

/**
 * Rows in one page of the outline.
 *
 * The same number as the search rail's `LOADED_MATCH_LIMIT` and for the same
 * reason -- a list a reader can walk in one pass -- but a separate constant:
 * these bound different lists, and tying them together would make raising one
 * silently raise the other.
 */
export const MAP_OUTLINE_PAGE = 25;

export interface OutlineRow {
  /** The node key, which is the entity's `global_id` (D-124). */
  globalId: string;
  /** The record, in the one preview shape the Map's cards render. */
  preview: MapPreview;
  /**
   * Relations drawn at this mark, in the accumulated graph.
   *
   * A count of *drawn* edges, so it moves as pages arrive and it is smaller
   * than the neighbourhood's own answer whenever the far endpoint has not
   * loaded (D-059). It is never presented as "how connected this entity is":
   * the related list asks the server that question.
   *
   * A relation the pipeline recorded onto the entity itself counts once.
   * `degree` in a directed multigraph counts a loop twice -- in and out --
   * which would report one recorded self-relation as two.
   */
  edgesDrawn: number;
}

export interface MapOutlineState {
  rows: OutlineRow[];
  /** Nodes the Map has drawn. */
  loaded: number;
  /** Rows in this page of the list. */
  listed: number;
  /** Loaded nodes the list did not reach. Never a silent difference. */
  unlisted: number;
}

/**
 * The outline of an accumulated graph, bounded by *limit*.
 *
 * `null` graph and empty graph give the same empty rows and a `loaded` of
 * zero; the two are distinguished by the Map's own state (`describeGraph`),
 * not here, because a list cannot tell "nothing loaded" from "nothing exists"
 * and must not guess.
 */
export function outlineOfGraph(
  graph: MapGraph | null,
  limit: number = MAP_OUTLINE_PAGE,
): MapOutlineState {
  if (graph === null) return { rows: [], loaded: 0, listed: 0, unlisted: 0 };
  const rows: OutlineRow[] = [];
  graph.forEachNode((key, attributes) => {
    if (rows.length >= limit) return;
    rows.push({
      globalId: key,
      preview: previewOfEntity(attributes.record),
      edgesDrawn: graph.degreeWithoutSelfLoops(key) + graph.edges(key, key).length,
    });
  });
  const loaded = graph.order;
  return { rows, loaded, listed: rows.length, unlisted: Math.max(0, loaded - rows.length) };
}
