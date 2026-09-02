/**
 * The typed conversion from what `/api/graph` returns into what Sigma draws
 * (`T-203`).
 *
 * One rule governs this module: **a projected record is the API's record.**
 * A node attribute set carries the `EntityRef` it came from, an edge attribute
 * set carries its `IndexedRelation`, and neither is flattened, renamed,
 * summarised or filled in. Nothing here computes a label, a size or a colour --
 * `T-205` owns the style matrix and D-122 forbids drawing the raw `label`
 * anyway, since a knowledge unit's label is its whole `normalized_statement`.
 * A missing `confidence` stays `null` rather than becoming `0`, a `kind` stays
 * absent rather than becoming `"unknown"`, and a `canonical_path` is the path
 * the index recorded. The Map can then be read as evidence of what the index
 * holds, which is the only reason to draw it at all.
 *
 * The two positional attributes are the exception, and they are not invention:
 * Sigma renders a node from `x`/`y` and ForceAtlas2 refines positions it is
 * *given*. They are seeded from the node's own `global_id` by `seedPosition`,
 * at insertion rather than in a later pass -- `graphology-layout-forceatlas2`
 * reads `attr.x` straight into a `Float32Array`, so a node inserted without one
 * becomes `NaN`, raises nothing, and is simply never drawn (ADR 0005, finding
 * 3).
 *
 * Identity is the API's too: node keys are `global_id`, edge keys are the
 * relation's own `id`. Neither is synthesised from labels or endpoints (ADR
 * 0005 invariant 2), which is what lets a count on the canvas be compared with
 * a count from the API, and what makes the same record arriving on two pages
 * recognisable as one record rather than as two.
 *
 * `MultiDirectedGraph`, because the real data needs every part of that name:
 * the edges are directed, two entities may be joined by more than one relation,
 * and a canonical self-loop is a design the pipeline marks with
 * `intentional_self_loop` rather than an error to filter out here.
 */

import { MultiDirectedGraph } from "graphology";

import type { EntityRef, IndexedRelation } from "../api/contract";
import { seedPosition } from "./seedPositions";

/**
 * What a drawn node carries: a starting position, and the record verbatim.
 *
 * `record` is the object the API returned. Presentation attributes are added
 * by the renderer's reducers (`T-205`), not stored here, so nothing in the
 * graph can be mistaken for something the index said.
 */
export interface MapNodeAttributes {
  x: number;
  y: number;
  record: EntityRef;
}

/** What a drawn edge carries: its relation record, verbatim. */
export interface MapEdgeAttributes {
  record: IndexedRelation;
}

export type MapGraph = MultiDirectedGraph<MapNodeAttributes, MapEdgeAttributes>;

export function createMapGraph(): MapGraph {
  return new MultiDirectedGraph<MapNodeAttributes, MapEdgeAttributes>();
}

/** A node's attributes: its seed, and the record it was projected from. */
export function nodeAttributes(record: EntityRef): MapNodeAttributes {
  const { x, y } = seedPosition(record.global_id);
  return { x, y, record };
}

/** An edge's attributes: the record it was projected from. */
export function edgeAttributes(record: IndexedRelation): MapEdgeAttributes {
  return { record };
}

/**
 * The first field two versions of one record disagree about, or `null`.
 *
 * Used to decide whether a repeated identity is the *same* record arriving
 * again -- which D-059 guarantees will happen, because an edge that straddles
 * two pages is returned on both -- or two different records claiming one id,
 * which is a conflict and never a merge (ADR 0005 invariant 2).
 *
 * **Absent and `null` are the same statement here.** Every optional field in
 * the contract is spelled `field?: T | null`, so a field that is not stated
 * may legitimately arrive either way, and calling that a conflict would refuse
 * a graph over a difference of spelling. Any other difference is reported:
 * `confidence: 0.9` against `confidence: null` is two claims about the same
 * edge, and one of them is wrong.
 *
 * Keys are visited in sorted order so the field named in a refusal is the same
 * one on every run, whatever order the two objects happen to spell their
 * members in.
 */
export function recordDifference(left: unknown, right: unknown, path = ""): string | null {
  const here = path === "" ? "the record" : path;
  const a = left ?? null;
  const b = right ?? null;
  if (a === null || b === null) return a === b ? null : here;

  if (Array.isArray(a) || Array.isArray(b)) {
    if (!Array.isArray(a) || !Array.isArray(b)) return here;
    if (a.length !== b.length) return here;
    for (let index = 0; index < a.length; index += 1) {
      const difference = recordDifference(a[index], b[index], `${here}[${index}]`);
      if (difference !== null) return difference;
    }
    return null;
  }

  if (typeof a === "object" || typeof b === "object") {
    if (typeof a !== "object" || typeof b !== "object") return here;
    const left_ = a as Record<string, unknown>;
    const right_ = b as Record<string, unknown>;
    const names = [...new Set([...Object.keys(left_), ...Object.keys(right_)])].sort();
    for (const name of names) {
      const child = path === "" ? name : `${here}.${name}`;
      const difference = recordDifference(left_[name], right_[name], child);
      if (difference !== null) return difference;
    }
    return null;
  }

  return a === b ? null : here;
}

/** Whether two versions of one record are the same record. */
export function sameRecord(left: unknown, right: unknown): boolean {
  return recordDifference(left, right) === null;
}

/**
 * Two pages claimed one identity and disagreed about what it is.
 *
 * Raised rather than merged. A merge would have to choose which page to
 * believe, and the Map would then draw a record that no request ever returned
 * -- the one thing a view of canonical evidence may not do. The walk stops,
 * keeps what it had already accumulated, and states the refusal (D-118).
 */
export class GraphConflictError extends Error {
  readonly kind: "node" | "edge";
  readonly id: string;
  readonly field: string;

  constructor(kind: "node" | "edge", id: string, field: string) {
    super(`Two graph pages disagree about ${kind} ${id}: ${field} differs.`);
    this.name = "GraphConflictError";
    this.kind = kind;
    this.id = id;
    this.field = field;
  }
}
