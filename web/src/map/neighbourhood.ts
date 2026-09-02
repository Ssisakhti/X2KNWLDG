/**
 * The bounded neighbourhood of one selection, and the complete related list
 * (`T-207`, D-132).
 *
 * `GET /api/graph/neighborhood/{entity_id}` answers a different question from
 * `GET /api/graph`: not "a page of the graph these filters describe" but "what
 * is within `depth` hops of *this* entity". Both answers are records, so both
 * go through `T-203`'s projection -- `nodeAttributes`, `edgeAttributes` and
 * `recordDifference` are reused verbatim here, including the refusal, so a
 * response that states one identity twice with two different records is a
 * `GraphConflictError` rather than a merge nobody requested (D-125).
 *
 * **This is not a second graph store** (§8.6). `GraphSnapshot` accumulates
 * *pages* into the one graph the Map draws, and nothing here touches it: a
 * neighbourhood is one response, projected whole, replaced whole when the
 * selection or the depth changes, and thrown away when the focus is cleared.
 * It answers questions about *relatedness* -- who is a neighbour, by which
 * relation, in which direction, how many hops out -- and the picture on the
 * canvas is still `GraphSnapshot`'s.
 *
 * A `MultiDirectedGraph` is used for that, and only for that: hop distance is
 * a walk over the edges the response returned, and re-implementing adjacency
 * over two arrays would be a worse copy of the structure this project already
 * depends on. Note that the neighbourhood's graph is *deliberately not* handed
 * to a renderer. If it were, the Map would draw nodes that the filters in the
 * URL do not describe, and the honest counts beside the canvas -- loaded
 * against the total the server counted -- would stop being comparable to
 * anything (ADR 0005 invariants 4 and 5).
 *
 * **Every returned neighbour is in `related`, always.** That is R20's whole
 * mitigation and the acceptance criterion `T-207` is judged on: the stage can
 * only place the cards that fit, so the list that cannot omit anything is the
 * one that carries completeness. Nothing here is filtered, ranked or scored.
 *
 * **The order is a sort key, not a relevance score** (D-133, invariant 15).
 * Hops from the centre, then the relation as the record spells it, then the
 * `global_id`: three stated facts, compared in a fixed order, so the list is
 * identical on every run and on every machine and says nothing about
 * importance. `localeCompare` is deliberately not used -- it is locale
 * dependent, and the Map's order must not change when the UI language does.
 */

import type { EntityRef, IndexedRelation, NeighborhoodPayload } from "../api/contract";
import {
  GraphConflictError,
  type MapGraph,
  createMapGraph,
  edgeAttributes,
  nodeAttributes,
  recordDifference,
} from "./graphProjection";

/** The depth bounds `GET /api/graph/neighborhood/{entity_id}` declares. */
export const MAP_DEPTH_MIN = 1;
export const MAP_DEPTH_MAX = 3;

/**
 * The depth a selection is opened at.
 *
 * One hop: the relations the entity itself states. Deeper is a deliberate act,
 * for the same reason a continuation page is (D-118) -- depth 3 over a
 * well-connected node is most of the library, and the reader asked to see one
 * statement's neighbours.
 */
export const MAP_DEFAULT_DEPTH = MAP_DEPTH_MIN;

export type MapDepth = 1 | 2 | 3;

/** Every depth the contract accepts, in the order the control offers them. */
export const MAP_DEPTHS: readonly MapDepth[] = [1, 2, 3];

/**
 * The depth a value asks for, or `null`.
 *
 * Ignored rather than clamped, exactly as `mapLink` ignores a filter it cannot
 * read: the server refuses `depth=4` instead of answering `depth=3`, because
 * the response echoes `depth` back and a clamped value would tell the client a
 * bound it never set. A client that clamped would be making the same mistake
 * one layer earlier.
 */
export function parseDepth(value: unknown): MapDepth | null {
  return (MAP_DEPTHS as readonly unknown[]).includes(value) ? (value as MapDepth) : null;
}

/**
 * How a relation runs, seen from one of its two endpoints.
 *
 * Direction is the record's, never the reader's: `from_id -> to_id` is what
 * the index stored, and "outgoing" means this entity is `from_id`. A
 * `self` edge is the pipeline's `intentional_self_loop` design rather than an
 * error, so it is named rather than dropped.
 */
export type RelationDirection = "outgoing" | "incoming" | "self";

/** One relation, as it looks from the entity it is listed under. */
export interface ActiveRelation {
  /** The relation record, verbatim. */
  record: IndexedRelation;
  direction: RelationDirection;
  /** The other endpoint's `global_id`; this entity's own, for a self-loop. */
  otherId: string;
}

/** One neighbour the API returned, with everything the list may state about it. */
export interface RelatedEntity {
  globalId: string;
  /** The record the neighbourhood returned, verbatim. */
  record: EntityRef;
  /** Hops from the centre over the edges this response returned. */
  hops: number;
  /**
   * The relations that join this entity directly to the centre.
   *
   * Empty for an entity that is only reachable through another one, which is
   * why `hops` is stated as well: at depth 2 a neighbour's connection to the
   * centre is a path, and naming a relation it does not have would be an
   * invented edge.
   */
  toCentre: readonly ActiveRelation[];
  /** Every relation this entity has *inside the returned neighbourhood*. */
  relations: readonly ActiveRelation[];
}

/**
 * One selection's neighbourhood: what the API returned, arranged.
 *
 * Every count is of records the response carried. Nothing is inferred from a
 * count, and `truncated` is the server's own statement that `limit` cut the
 * walk short -- not a guess from the length of an array.
 */
export interface Neighbourhood {
  /** The centre the *response* echoed back, never the id the client asked with. */
  centreId: string;
  /** The depth the response states it answered at. */
  depth: number;
  /** The centre's record as this response returned it, or `null` if it did not. */
  centre: EntityRef | null;
  /** The centre's own direct relations, in the same order as `related`'s keys. */
  active: readonly ActiveRelation[];
  /** Every neighbour returned, deterministically ordered. Never filtered. */
  related: readonly RelatedEntity[];
  /** `limit` cut the walk short: more neighbours exist than were returned. */
  truncated: boolean;
  /** Distinct node identities the response carried, the centre included. */
  nodesReturned: number;
  /** Edges joined: both endpoints were among the returned nodes. */
  edgesReturned: number;
  /**
   * Edges the response carried whose endpoints it did not both return.
   *
   * Zero against both repository implementations -- `neighborhood()`
   * guarantees every edge runs between nodes it returned -- and counted rather
   * than assumed, because the alternative to counting is inventing the missing
   * endpoint, which is the one thing D-059 taught this Map not to do.
   */
  edgesUnjoinable: number;
  /**
   * Returned nodes with no path to the centre over the returned edges.
   *
   * Zero against both repository implementations, which is why it is reported
   * rather than asserted: it is the one number that would show a bounded walk
   * returning a node it cannot explain, and an unexplained node is still
   * listed -- with `hops: 0` and no relation -- rather than dropped.
   */
  unreachable: number;
}

/** An empty neighbourhood for a centre, so "nothing yet" needs no null checks. */
export function noNeighbourhood(centreId: string, depth: number): Neighbourhood {
  return {
    centreId,
    depth,
    centre: null,
    active: [],
    related: [],
    truncated: false,
    nodesReturned: 0,
    edgesReturned: 0,
    edgesUnjoinable: 0,
    unreachable: 0,
  };
}

function directionOf(record: IndexedRelation, self: string): RelationDirection {
  if (record.from_id === self && record.to_id === self) return "self";
  return record.from_id === self ? "outgoing" : "incoming";
}

function otherEndpoint(record: IndexedRelation, self: string): string {
  if (record.from_id === self && record.to_id === self) return self;
  return record.from_id === self ? record.to_id : record.from_id;
}

/** Ordinary string order, and the same order on every machine. */
function compareText(left: string, right: string): number {
  if (left === right) return 0;
  return left < right ? -1 : 1;
}

/**
 * The relations of one entity, ordered the same way the list is.
 *
 * Sorted so that a card and a list row naming the same connection name it in
 * the same order, and so that two runs over one response agree.
 */
function relationsOf(
  graph: MapGraph,
  globalId: string,
  restrictTo?: string,
): ActiveRelation[] {
  const found: ActiveRelation[] = [];
  graph.forEachEdge(globalId, (_key, attributes) => {
    const record = attributes.record;
    const other = otherEndpoint(record, globalId);
    if (restrictTo !== undefined && other !== restrictTo) return;
    found.push({ record, direction: directionOf(record, globalId), otherId: other });
  });
  found.sort(
    (left, right) =>
      compareText(left.record.relation, right.record.relation) ||
      compareText(left.otherId, right.otherId) ||
      compareText(left.record.id, right.record.id),
  );
  return found;
}

/**
 * Hops from the centre to every returned node, over the returned edges.
 *
 * Breadth-first and **undirected**: a relation is a connection whichever way
 * the index stored it, and a reader following `supports` backwards has still
 * reached the same neighbour. Direction is not lost -- it is stated per
 * relation, where it belongs, rather than deciding reachability here.
 */
function hopsFrom(graph: MapGraph, centreId: string): Map<string, number> {
  const hops = new Map<string, number>();
  if (!graph.hasNode(centreId)) return hops;
  hops.set(centreId, 0);
  let frontier = [centreId];
  while (frontier.length > 0) {
    const next: string[] = [];
    for (const node of frontier) {
      const distance = hops.get(node) ?? 0;
      graph.forEachNeighbor(node, (neighbour: string) => {
        if (hops.has(neighbour)) return;
        hops.set(neighbour, distance + 1);
        next.push(neighbour);
      });
    }
    frontier = next;
  }
  return hops;
}

/**
 * Project one neighbourhood response.
 *
 * Checked whole before anything is built, like a graph page: a conflicting
 * response is refused rather than half-applied, so what the reader sees is
 * either this response or the previous one, never a blend of the two.
 *
 * The centre is *the response's* `center_id`. The client asked with an id and
 * the server echoes one back precisely so that a batched or late answer cannot
 * be mis-attributed (the contract says so in as many words), and honouring the
 * echo is what makes that guarantee worth anything.
 */
export function projectNeighbourhood(payload: NeighborhoodPayload): Neighbourhood {
  const graph = createMapGraph();

  // Nodes first, so an edge can never invent an endpoint. The neighbourhood
  // endpoint states that every edge it returns runs between nodes it returned;
  // an edge that disagrees is dropped and counted rather than trusted, because
  // drawing it would require a node no request returned (D-059's lesson, one
  // scale down).
  for (const record of payload.nodes) {
    if (graph.hasNode(record.global_id)) {
      const field = recordDifference(graph.getNodeAttribute(record.global_id, "record"), record);
      if (field !== null) throw new GraphConflictError("node", record.global_id, field);
      continue;
    }
    graph.addNode(record.global_id, nodeAttributes(record));
  }

  let edgesUnjoinable = 0;
  for (const record of payload.edges) {
    if (graph.hasEdge(record.id)) {
      const field = recordDifference(graph.getEdgeAttribute(record.id, "record"), record);
      if (field !== null) throw new GraphConflictError("edge", record.id, field);
      continue;
    }
    if (!graph.hasNode(record.from_id) || !graph.hasNode(record.to_id)) {
      edgesUnjoinable += 1;
      continue;
    }
    graph.addDirectedEdgeWithKey(record.id, record.from_id, record.to_id, edgeAttributes(record));
  }

  const centreId = payload.center_id;
  const centre = graph.hasNode(centreId) ? graph.getNodeAttribute(centreId, "record") : null;
  const hops = hopsFrom(graph, centreId);

  const related: RelatedEntity[] = [];
  let unreachable = 0;
  graph.forEachNode((globalId, attributes) => {
    if (globalId === centreId) return;
    const distance = hops.get(globalId);
    if (distance === undefined) unreachable += 1;
    related.push({
      globalId,
      record: attributes.record,
      hops: distance ?? 0,
      toCentre: relationsOf(graph, globalId, centreId),
      relations: relationsOf(graph, globalId),
    });
  });

  related.sort(
    (left, right) =>
      left.hops - right.hops ||
      compareText(
        left.toCentre[0]?.record.relation ?? "",
        right.toCentre[0]?.record.relation ?? "",
      ) ||
      compareText(left.globalId, right.globalId),
  );

  return {
    centreId,
    depth: payload.depth,
    centre,
    active: centre === null ? [] : relationsOf(graph, centreId),
    related,
    truncated: payload.truncated,
    nodesReturned: graph.order,
    edgesReturned: graph.size,
    edgesUnjoinable,
    unreachable,
  };
}
