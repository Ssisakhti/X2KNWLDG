/**
 * The Map's search: two corpora, one card shape (`T-206`, D-130).
 *
 * The journey D-130 approves starts at Search, and a Map has two honest
 * answers to a query, which are not the same answer:
 *
 * 1. **What is on the Map already.** The accumulated snapshot is in memory, so
 *    a loaded node matching by `label` or by identity is found without a
 *    request, cannot fail, and cannot be stale. It is also the only list that
 *    can promise the node is drawable right now.
 * 2. **What the index holds.** `GET /api/search` reaches the whole library,
 *    including entities no page of the graph has loaded (D-118 leaves a graph
 *    larger than the first page deliberately incomplete). It is a request, so
 *    it can be refused, and it can answer a question that has been replaced.
 *
 * They are kept apart rather than merged into one ranked list. Merging would
 * need a client-side score to order across two incomparable sources, and a
 * score presented as relevance is exactly the invented quantity ADR 0005
 * invariant 15 forbids. Two labelled lists say something true instead: this is
 * here, and this exists.
 *
 * **Stale requests are dropped whole.** The indexed search runs through
 * `usePaged`, which is where D-079's lesson already lives: every request
 * belongs to a generation of the query, the effect's cleanup retires it and
 * aborts what is in flight, and a page that resolves after its question was
 * replaced is discarded rather than partially applied. Typing a second query
 * cannot append the first query's hits, and cannot leave the first query's
 * cursor behind for "More" to paginate a collection nobody is looking at.
 *
 * **Nothing here writes text.** `MapPreview` copies fields out of a record and
 * normalises *nothing else*: an absent confidence stays `null` and is rendered
 * as a visible absence rather than as `0`, a `kind` the pipeline did not state
 * stays `null`, and the statement is the API's own `label`/`content`. There is
 * no summary, no derived title and no fallback text (D-131). Truncation for
 * display happens in the card, visibly, and never here -- a truncated string
 * stored in a data structure is a rewritten record.
 */

import { useCallback, useMemo } from "react";

import { api } from "../api/client";
import type { EntityRef, ProvenanceClass, SearchHit } from "../api/contract";
import { ApiFailure } from "../api/errors";
import type { AsyncStatus } from "../api/useAsync";
import { usePaged } from "../api/usePaged";
import { PROVENANCE_CLASSES } from "../api/vocabulary";
import type { ReaderTab } from "../lib/readerLink";
import type { MapGraph } from "./graphProjection";

/** Hits per page of the indexed search, matching the Library's rail. */
export const MAP_SEARCH_LIMIT = 25;

/** Loaded nodes listed for one query before the list says how many more matched. */
export const LOADED_MATCH_LIMIT = 25;

/** Why a hit has no Map address. `null` means it has one. */
export type Unaddressable = "caption" | "no_global_id";

/**
 * One result, in the only shape the Map's cards render.
 *
 * Every field is copied or `null`. `globalId` is the whole selection question:
 * `null` means this result is not an entity in v1 and must not be selectable,
 * which is the difference between explaining a caption hit and minting an
 * address that resolves to nothing (D-023, D-119).
 */
export interface MapPreview {
  /** Stable React key. Identity where there is one, position where there is not. */
  key: string;
  /** Which corpus answered: the loaded graph, or the index. */
  origin: "graph" | "index";
  /** The entity's existing `global_id`, or `null` when it has none. */
  globalId: string | null;
  /** Why it has none. `null` when it has one. */
  unaddressable: Unaddressable | null;
  /** Whether the Map has this node loaded and drawn right now. */
  loaded: boolean;
  /** The knowledge kind, exactly as stated. */
  kind: string | null;
  /** Provenance, when the value is one of the three the contract defines. */
  provenance: ProvenanceClass | null;
  /** The provenance value as written, for the case where it is not one of them. */
  provenanceRaw: string | null;
  confidence: number | null;
  /** The statement, verbatim: `EntityRef.label`, or a hit's `content`. */
  text: string | null;
  startSec: number | null;
  endSec: number | null;
  sourceId: string | null;
  /** The source's title, when the hit carries one. Never derived from an id. */
  sourceTitle: string | null;
  /** The deep link the server built with `io.timestamp_url`, verbatim. */
  sourceUrl: string | null;
  /** The canonical local id: a knowledge unit id, or a caption's `segment_id`. */
  localId: string | null;
  /** Which Reader tab this result was found in. */
  readerTab: ReaderTab;
}

function provenanceOf(value: string | null | undefined): ProvenanceClass | null {
  return typeof value === "string" && (PROVENANCE_CLASSES as readonly string[]).includes(value)
    ? (value as ProvenanceClass)
    : null;
}

function timeRangeOf(entity: EntityRef): { start: number | null; end: number | null } {
  const locator = entity.locator;
  if (locator == null || locator.type !== "time_range") return { start: null, end: null };
  return { start: locator.start_sec ?? null, end: locator.end_sec ?? null };
}

/**
 * An entity record as a preview. Always addressable: an entity *is* its
 * `global_id`.
 *
 * The `options` are `T-207`'s, and they exist so that the bounded
 * neighbourhood can use this formatter rather than write a second one (§8.6
 * allows one card-content formatter). A record that arrived from
 * `/api/graph/neighborhood/{id}` came from the *index*, and whether the Map
 * has it drawn is a separate fact read from the accumulated graph -- so both
 * are parameters here instead of the two constants that were right when the
 * only caller was the loaded snapshot. The defaults are those constants, so
 * every existing call means exactly what it meant.
 */
export function previewOfEntity(
  entity: EntityRef,
  options: { origin?: MapPreview["origin"]; loaded?: boolean } = {},
): MapPreview {
  const { start, end } = timeRangeOf(entity);
  const origin = options.origin ?? "graph";
  return {
    key: `${origin}|${entity.global_id}`,
    origin,
    globalId: entity.global_id,
    unaddressable: null,
    loaded: options.loaded ?? true,
    kind: entity.kind ?? null,
    provenance: provenanceOf(entity.provenance_class),
    provenanceRaw: entity.provenance_class,
    confidence: entity.confidence ?? null,
    text: entity.label ?? null,
    startSec: start,
    endSec: end,
    sourceId: entity.source_id ?? null,
    sourceTitle: null,
    sourceUrl: null,
    localId: entity.local_id,
    readerTab: "units",
  };
}

/**
 * One `/api/search` hit as a preview.
 *
 * The two hit shapes stay distinguishable exactly where it matters. A
 * `transcript_caption` carries no `global_id` because v1 emits no caption
 * entities, and a `knowledge_unit` whose canonical metadata states no
 * `video_id` carries `global_id: null` by design -- "a fabricated id would be
 * worse than none", as the contract itself puts it. Both become
 * `globalId: null` with a stated reason, and the card refuses to make either
 * selectable.
 */
export function previewOfHit(hit: SearchHit, index: number, loaded: boolean): MapPreview {
  if (hit.type === "transcript_caption") {
    return {
      key: `index|caption|${hit.video_id ?? ""}|${hit.caption_id ?? ""}|${index}`,
      origin: "index",
      globalId: null,
      unaddressable: "caption",
      loaded: false,
      kind: null,
      provenance: null,
      provenanceRaw: null,
      confidence: null,
      text: hit.content,
      startSec: hit.start_sec ?? null,
      endSec: hit.end_sec ?? null,
      sourceId: hit.source_id,
      sourceTitle: hit.title,
      sourceUrl: hit.source_url,
      localId: hit.caption_id,
      readerTab: "transcript",
    };
  }
  return {
    key: `index|unit|${hit.global_id ?? hit.video_id ?? ""}|${hit.id ?? ""}|${index}`,
    origin: "index",
    globalId: hit.global_id,
    unaddressable: hit.global_id === null ? "no_global_id" : null,
    loaded,
    kind: hit.kind,
    provenance: provenanceOf(hit.source_class),
    provenanceRaw: hit.source_class,
    confidence: hit.confidence,
    text: hit.content,
    startSec: hit.start_sec ?? null,
    endSec: null,
    sourceId: hit.source_id,
    sourceTitle: hit.title,
    sourceUrl: hit.source_url ?? null,
    localId: hit.id,
    readerTab: "units",
  };
}

/**
 * The loaded record for a `global_id`, or `null`.
 *
 * The one way anything in `T-206` reads the accumulated graph. `MapView` hands
 * it to `useMapPeek`, so a Peek can only ever show a record the Map really
 * holds.
 */
export function recordLookup(graph: MapGraph | null): (globalId: string) => EntityRef | null {
  return (globalId: string) => {
    if (graph === null || !graph.hasNode(globalId)) return null;
    return graph.getNodeAttribute(globalId, "record");
  };
}

/** What a query matches among the loaded nodes, and how much of it is listed. */
export interface LoadedMatches {
  items: MapPreview[];
  /** How many loaded nodes matched in total. `items` may be shorter. */
  matched: number;
  /** Loaded nodes searched, so "0 of 0" and "0 of 86" stay distinguishable. */
  searched: number;
}

/**
 * Loaded nodes matching *query* by statement or by identity.
 *
 * Case-insensitive substring, over the record's own `label`, `global_id`,
 * `local_id` and `library_id` -- the four strings a person actually has in
 * front of them. There is no ranking: the order is the graph's own insertion
 * order, which is the order the API returned, so the list is reproducible and
 * says nothing about importance (invariant 15).
 */
export function searchLoadedNodes(
  graph: MapGraph | null,
  query: string,
  limit: number = LOADED_MATCH_LIMIT,
): LoadedMatches {
  const needle = query.trim().toLocaleLowerCase();
  if (graph === null || needle === "") return { items: [], matched: 0, searched: graph?.order ?? 0 };
  const items: MapPreview[] = [];
  let matched = 0;
  graph.forEachNode((_key, attributes) => {
    const record = attributes.record;
    const haystacks = [record.label, record.global_id, record.local_id, record.library_id];
    const hit = haystacks.some(
      (value) => typeof value === "string" && value.toLocaleLowerCase().includes(needle),
    );
    if (!hit) return;
    matched += 1;
    if (items.length < limit) items.push(previewOfEntity(record));
  });
  return { items, matched, searched: graph.order };
}

export interface MapSearchBinding {
  /** The query as asked. Empty means no question was asked. */
  query: string;
  /** What the loaded graph answers, with no request. */
  loaded: LoadedMatches;
  /** What the index answers. */
  indexed: MapPreview[];
  status: AsyncStatus;
  error: ApiFailure | null;
  /** Hits the server counted; `null` is "did not count", never zero. */
  total: number | null;
  hasMore: boolean;
  loadingMore: boolean;
  loadMore: () => void;
  reload: () => void;
}

/**
 * @param graph the accumulated snapshot, mutated in place -- so `revision`
 * (`snapshotId` or `pagesApplied`) is what tells this hook it changed. Passing
 * the graph alone would memoise against an object identity that never varies.
 */
export function useMapSearch(options: {
  query: string;
  graph: MapGraph | null;
  revision: number;
  /** `GET /api/search`'s own `include_transcript`. Off by default: a caption is not an entity. */
  includeTranscript?: boolean;
  /** `GET /api/search`'s own `source_id`, so the rail can honour the Map's source scope. */
  sourceId?: string | null;
}): MapSearchBinding {
  const { graph, revision } = options;
  const query = options.query.trim();
  const includeTranscript = options.includeTranscript ?? false;
  const sourceId = options.sourceId ?? null;

  const loaded = useMemo(
    () => searchLoadedNodes(graph, query),
    // The graph is mutated in place (D-118), so its identity is not the
    // dependency -- the revision is.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [graph, revision, query],
  );

  const load = useCallback(
    async (cursor: string | undefined, signal: AbortSignal) => {
      const response = await api.call("search", {
        query: {
          q: query,
          limit: MAP_SEARCH_LIMIT,
          include_transcript: includeTranscript,
          ...(sourceId === null ? {} : { source_id: sourceId }),
          ...(cursor === undefined ? {} : { cursor }),
        },
        signal,
      });
      return {
        items: response.data,
        next: response.page.next_cursor,
        total: response.page.total ?? null,
      };
    },
    [query, includeTranscript, sourceId],
  );

  const paged = usePaged<SearchHit>(load, [query, includeTranscript, sourceId], {
    enabled: query !== "",
  });

  const isLoaded = useMemo(
    () => recordLookup(graph),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [graph, revision],
  );

  const indexed = useMemo(
    () =>
      paged.items.map((hit, index) => {
        // "Already on the Map" is a fact about the loaded graph, so it is read
        // from the graph rather than assumed from the hit. A caption never has
        // a node to be loaded as.
        const drawn =
          hit.type === "knowledge_unit" &&
          hit.global_id !== null &&
          isLoaded(hit.global_id) !== null;
        return previewOfHit(hit, index, drawn);
      }),
    [paged.items, isLoaded],
  );

  return {
    query,
    loaded,
    indexed,
    status: paged.status,
    error: paged.error,
    total: paged.total,
    hasMore: paged.hasMore,
    loadingMore: paged.loadingMore,
    loadMore: paged.loadMore,
    reload: paged.reload,
  };
}
