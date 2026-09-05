/**
 * One selected source's neighbourhood, as the Focus composition needs it
 * (`T-256`).
 *
 * `neighbourhood.ts` does this for the Knowledge Map and this is deliberately
 * not folded into it: that module walks a *graph* — a breadth-first frontier,
 * hop counts, a parent chosen deterministically for each hop-2 node — and none
 * of that exists here. `GET /api/source-graph/neighborhood/{source_id}` takes a
 * `limit` and **no `depth`** (D-272), so a source neighbourhood is one ring and
 * the walk has nothing to walk.
 *
 * What this module does instead is smaller and has one rule worth stating:
 *
 * **Direction is read from the response, never derived.** The payload separates
 * `incoming` and `outgoing` precisely so a client does not have to compare
 * `to_source_id` with `center_id` and get it wrong — which is the defect D-193
 * records for the Knowledge Map, where every card landed on the wrong half of
 * the field because direction was read from the neighbour's end of the relation
 * rather than the focus's. Two arrays arrive; two arrays are used.
 *
 * **Every returned relationship survives into the list, drawn or not.** The
 * stage has a card budget and the response has a bound; neither may lose a
 * relationship quietly. `placed` and `omitted` are counted here so the view can
 * state `placed + omitted === returned`, which is the accounting the browser
 * gate asserts for the Knowledge Map's overlay.
 */

import type {
  EntityRef,
  SourceNeighborhoodPayload,
  SourceRelationDetail,
} from "../api/contract";

/** One relationship as the Focus composition places it. */
export interface SourceEdgeView {
  readonly relation: SourceRelationDetail;
  /** Which side of the focus it belongs on, as the response stated it. */
  readonly direction: "incoming" | "outgoing";
  /** The source at the other end, or `null` when the response named no node. */
  readonly other: EntityRef | null;
  /** The other end's two-part id, which is present even when the node is not. */
  readonly otherSourceId: string;
}

/** A selected source, ready to draw. */
export interface SourceNeighbourhoodView {
  readonly centre: EntityRef;
  readonly centreId: string;
  readonly knowledge: SourceNeighborhoodPayload["source_knowledge"];
  readonly incoming: readonly SourceEdgeView[];
  readonly outgoing: readonly SourceEdgeView[];
  /** Both sides in one list, incoming first, for the semantic companion. */
  readonly all: readonly SourceEdgeView[];
  /** Every neighbour's record, by two-part id. */
  readonly neighbours: ReadonlyMap<string, EntityRef>;
  /** True when the response's own bound cut relationships out of this body. */
  readonly truncated: boolean;
}

export function projectSourceNeighbourhood(
  payload: SourceNeighborhoodPayload,
): SourceNeighbourhoodView {
  const neighbours = new Map<string, EntityRef>();
  for (const node of payload.neighbors) {
    // `source_id` is nullable on an `EntityRef` because a library concept has
    // none. A source node always does, and a node that did not would be a
    // record this Map cannot address — skipped rather than keyed by a guess.
    if (typeof node.source_id === "string") neighbours.set(node.source_id, node);
  }

  const centreId = payload.source.source_id ?? "";
  const edge = (
    relation: SourceRelationDetail,
    direction: "incoming" | "outgoing",
  ): SourceEdgeView => {
    // The other end is the one that is not the centre. Read from the record's
    // own fields and from the direction the response stated, so the two can
    // never disagree with each other.
    const otherSourceId =
      direction === "incoming" ? relation.from_source_id : relation.to_source_id;
    const other = otherSourceId === undefined ? null : (neighbours.get(otherSourceId) ?? null);
    return {
      relation,
      direction,
      other,
      otherSourceId,
    };
  };

  const incoming = payload.incoming.map((relation) => edge(relation, "incoming"));
  const outgoing = payload.outgoing.map((relation) => edge(relation, "outgoing"));

  return {
    centre: payload.source,
    centreId,
    knowledge: payload.source_knowledge,
    incoming,
    outgoing,
    all: [...incoming, ...outgoing],
    neighbours,
    truncated: payload.truncated,
  };
}

/**
 * How many relationships fit on the stage at this tier, per side.
 *
 * The budget is per *side* rather than in total, because the composition places
 * a band on each and a total would let a source with six incoming and none
 * outgoing fill one side and leave the other empty — which reads as a source
 * with no outgoing relationships rather than as a stage that ran out of room.
 */
export function stageBudget(perSide: number, view: SourceNeighbourhoodView): {
  readonly incoming: readonly SourceEdgeView[];
  readonly outgoing: readonly SourceEdgeView[];
  readonly omitted: number;
} {
  const incoming = view.incoming.slice(0, perSide);
  const outgoing = view.outgoing.slice(0, perSide);
  return {
    incoming,
    outgoing,
    omitted:
      view.incoming.length - incoming.length + (view.outgoing.length - outgoing.length),
  };
}

/**
 * The brief state of every source this neighbourhood knows about.
 *
 * Only the centre's is stated by the response — a neighbour's `EntityRef` says
 * nothing about whether it has a brief — so this map holds exactly one entry
 * and the style table reads every other source as `unavailable`. That is an
 * honest under-claim rather than a gap: drawing a neighbour as though it had a
 * brief, or as though it certainly had none, would both be claims this response
 * does not make. The field fills in as a reader selects.
 */
export function briefStateOf(
  view: SourceNeighbourhoodView,
): ReadonlyMap<string, SourceNeighborhoodPayload["source_knowledge"]["state"]> {
  return new Map([[view.centre.global_id, view.knowledge.state]]);
}
