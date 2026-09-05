/**
 * The Source Map's fixtures (`T-256`).
 *
 * Shaped like the real payloads and built from the same corpus the API's own
 * tests use, so a frontend assertion and a backend one are about the same
 * records: `youtube:fixture-pass` has a Persian brief at `PASS`,
 * `youtube:fixture-partial` has one at `PARTIAL`, `youtube:fixture-fail` has
 * none, and the one gated relationship runs from the X post to the passing
 * video.
 *
 * The Persian strings are the fixtures' own. They are here rather than replaced
 * with Latin placeholders because half of what these tests are for is that a
 * Persian brief renders beside Latin identifiers without either reordering the
 * other — a placeholder would pass a test the real record fails.
 */

import type {
  EntityRef,
  SourceGraphPayload,
  SourceKnowledgeAvailability,
  SourceNeighborhoodPayload,
  SourceRelationDetail,
  SourceRelationSummary,
} from "../api/contract";

export const PASS = "youtube:fixture-pass";
export const PARTIAL = "youtube:fixture-partial";
export const FAIL = "youtube:fixture-fail";
export const POST = "twitter:2094039408081068233";
export const RELATION = "SR-f596992c42435c40";

/** One source node, as the API returns one. */
export function sourceNode(sourceId: string, overrides: Partial<EntityRef> = {}): EntityRef {
  const [sourceType = "youtube", externalId = ""] = sourceId.split(":");
  return {
    schema_version: "1.0",
    global_id: `${sourceId}:source`,
    source_type: sourceType,
    external_id: externalId,
    local_id: "source",
    source_id: sourceId,
    entity_type: "source",
    provenance_class: "source",
    kind: null,
    label: `TEST FIXTURE (${externalId}) — synthetic, not real evidence`,
    canonical_path: `output/${externalId}/metadata.json`,
    ...overrides,
  } as EntityRef;
}

export function summary(
  from: string,
  to: string,
  overrides: Partial<SourceRelationSummary> = {},
): SourceRelationSummary {
  return {
    id: RELATION,
    from_source_id: from,
    to_source_id: to,
    relation_type: "critiques",
    scope: "partial",
    provenance_class: "derived",
    basis_total: 1,
    ...overrides,
  } as SourceRelationSummary;
}

export function detail(
  from: string,
  to: string,
  overrides: Partial<SourceRelationDetail> = {},
): SourceRelationDetail {
  return {
    id: RELATION,
    from_source_id: from,
    to_source_id: to,
    relation_type: "critiques",
    scope: "partial",
    provenance_class: "derived",
    rationale:
      "این پستِ آزمایشی یکی از ادعاهای مشخصِ آن ویدیوی آزمایشی را نقد می‌کند؛ گسترهٔ نسبت جزئی است.",
    basis: [{ from_ku_id: "KU-000001", to_ku_id: "KU-000001", relation_type: "contradicts" }],
    basis_total: 1,
    basis_returned: 1,
    ...overrides,
  } as SourceRelationDetail;
}

/** A brief, in the language the record is written in. */
export function brief(
  status: "PASS" | "PARTIAL" = "PASS",
  sourceId: string = PASS,
): SourceKnowledgeAvailability {
  return {
    state: "available",
    reason: null,
    brief: {
      schema_version: "1.0",
      source_id: sourceId,
      status,
      thesis: {
        content:
          "این منبعِ آزمایشی نشان می‌دهد که هر واحد دانش باید شواهدی را که بر آن تکیه دارد همراه خود بیاورد.",
        based_on: ["KU-000001"],
      },
      key_points: [
        {
          id: "SP-001",
          content: "ادعای بدون شاهدِ زمان‌دار، دانشِ برگرفته از منبع نیست.",
          based_on: ["KU-000001"],
        },
        {
          id: "SP-002",
          content: "پوشش پنجره‌به‌پنجره ممیزی می‌شود، نه یک‌جا برای کل منبع.",
          based_on: ["KU-000001"],
        },
      ],
      limitations_or_tensions: [],
      generated_from: {
        knowledge_units_sha256: "d".repeat(64),
        relationships_sha256: "9".repeat(64),
        coverage_sha256: "3".repeat(64),
      },
      generated_at: "2026-01-01T00:00:00+00:00",
    },
  } as SourceKnowledgeAvailability;
}

/** No brief at all, which is what a run that did not pass has. */
export const NO_BRIEF: SourceKnowledgeAvailability = {
  state: "unavailable",
  brief: null,
  reason: "no source_knowledge.json",
};

/** A brief whose inputs have moved, carried with its state saying so. */
export function staleBrief(): SourceKnowledgeAvailability {
  return {
    ...brief(),
    state: "stale",
    reason: "generated from inputs that have since changed: knowledge_units_sha256",
  } as SourceKnowledgeAvailability;
}

export function graphPayload(
  nodes: EntityRef[],
  relations: SourceRelationSummary[],
  overrides: Partial<SourceGraphPayload["counts"]> = {},
): SourceGraphPayload {
  return {
    nodes,
    relations,
    truncated: false,
    counts: {
      sources_returned: nodes.length,
      relations_returned: relations.length,
      relations_omitted: 0,
      sources_total: nodes.length,
      ...overrides,
    },
  };
}

export function neighbourhoodPayload(
  centre: EntityRef,
  options: {
    knowledge?: SourceKnowledgeAvailability;
    incoming?: SourceRelationDetail[];
    outgoing?: SourceRelationDetail[];
    neighbors?: EntityRef[];
    truncated?: boolean;
  } = {},
): SourceNeighborhoodPayload {
  return {
    center_id: centre.global_id,
    source: centre,
    source_knowledge: options.knowledge ?? NO_BRIEF,
    incoming: options.incoming ?? [],
    outgoing: options.outgoing ?? [],
    neighbors: options.neighbors ?? [],
    truncated: options.truncated ?? false,
  };
}

export const graphResponse = (data: SourceGraphPayload, next: string | null = null) => ({
  api_version: "v1",
  schema_version: "1.0",
  data,
  page: { limit: 50, next_cursor: next, total: data.counts.sources_total },
});

export const neighbourhoodResponse = (data: SourceNeighborhoodPayload) => ({
  api_version: "v1",
  schema_version: "1.0",
  data,
});
