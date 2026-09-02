/**
 * Graph records shaped like the ones `/api/graph` really returns.
 *
 * Copied from the real payload rather than invented: a knowledge unit carries
 * an explicit `source_id`, a `canonical_path` and a `label` that is a whole
 * sentence; a canonical concept belongs to no source and states
 * `confidence: null`; and a library-synthetic edge spells its own id as
 * `<from>|<relation>|<to>`. The nulls are written out because the server
 * writes them out, and a test built on a tidier shape would not notice a
 * projection that dropped one.
 */

import type { EntityRef, GraphPayload, IndexedRelation, PageInfo } from "../api/contract";

export const VIDEO = "pqlWNihgdjI";

/** A source-class knowledge unit, as the adapter projects one. */
export function unit(localId: string, overrides: Partial<EntityRef> = {}): EntityRef {
  return {
    schema_version: "1.0",
    global_id: `youtube:${VIDEO}:${localId}`,
    source_type: "youtube",
    external_id: VIDEO,
    local_id: localId,
    library_id: `${VIDEO}:${localId}`,
    source_id: `youtube:${VIDEO}`,
    entity_type: "knowledge_unit",
    provenance_class: "source",
    kind: "claim",
    label: `A statement the transcript actually makes, numbered ${localId}.`,
    confidence: 0.91,
    canonical_path: `output/${VIDEO}/knowledge_units.json`,
    ...overrides,
  };
}

/** A canonical concept: derived, belonging to no source, with no confidence. */
export function concept(localId: string, overrides: Partial<EntityRef> = {}): EntityRef {
  return {
    schema_version: "1.0",
    global_id: `library:concepts:${localId}`,
    source_type: "library",
    external_id: "concepts",
    local_id: localId,
    library_id: `concept:${localId}`,
    source_id: null,
    entity_type: "concept",
    provenance_class: "derived",
    kind: "canonical_concept",
    label: "Autonomy loop: intent -> context -> action -> feedback.",
    confidence: null,
    canonical_path: "output/library/concepts.json",
    ...overrides,
  };
}

/** A canonical edge between two units. */
export function edge(
  from: string,
  to: string,
  relation = "supports",
  overrides: Partial<IndexedRelation> = {},
): IndexedRelation {
  return {
    schema_version: "1.0",
    id: `${from}|${relation}|${to}`,
    from_id: from,
    to_id: to,
    relation,
    relation_vocabulary: "canonical",
    provenance_class: "source",
    confidence: 0.88,
    source_id: `youtube:${VIDEO}`,
    canonical_path: `output/${VIDEO}/relationships.json`,
    ...overrides,
  };
}

/** One of the two library-synthetic edges, which are the commonest in the real data. */
export function expressesConcept(from: string, to: string): IndexedRelation {
  return edge(from, to, "expresses_concept", {
    relation_vocabulary: "library_synthetic",
    provenance_class: "derived",
    confidence: null,
    source_id: null,
    canonical_path: "output/library/graph.json",
  });
}

export function payload(overrides: Partial<GraphPayload> = {}): GraphPayload {
  return { nodes: [], edges: [], truncated: false, ...overrides };
}

export function page(overrides: Partial<PageInfo> = {}): PageInfo {
  return { limit: 500, next_cursor: null, total: null, ...overrides };
}
