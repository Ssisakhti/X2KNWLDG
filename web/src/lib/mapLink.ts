/**
 * The Map's addressable state, in one grammar (`T-206`, D-119):
 *
 *     #/map?of=<mode>&focus=<global_id>&source_id=<id>&provenance_class=<class>&relation_vocabulary=<vocab>
 *
 * **`of` is the Map's mode, and it is addressable for the reason the rest of
 * this grammar is** (`T-256`): a Source Map that could not be linked to, opened
 * cold or reloaded would be a panel rather than a Map. `of=sources` is the only
 * value written; the Knowledge Map is the absence of the parameter rather than
 * `of=knowledge`, because this grammar spells no defaults.
 *
 * **`focus` stays a `global_id` in both modes.** A source node *is* an
 * `EntityRef` with `entity_type: "source"` and a three-part id, so the one
 * selection identity holds across the switch and `parseFocus` needs no second
 * rule. The two-part `SourceId` the neighbourhood endpoint takes is derived
 * from it by `format.sourceIdOf` — which already existed for the Reader's
 * links — rather than carried as a sixth parameter or re-derived here. One
 * identity in the URL, one derivation, and no second spelling of a source.
 *
 * One module, for the reason `readerLink` already proved: a URL *built* in one
 * place and *read* in another is two implementations of one rule, and the pair
 * drifts. Everything that writes a Map link calls `mapPath`; the Map itself
 * calls `parseMapState` on what arrives. `readerLink` is the precedent this
 * follows line for line, including the part that matters most -- an unreadable
 * value is **ignored**, never coerced. Reading `provenance_class=derivd` as
 * `derived` would filter a graph the user never asked to filter, which is the
 * same class of error as reading `t=x` as second `0`.
 *
 * **Three of the four parameters are the API's own.** `GET /api/graph` accepts
 * `source_id`, `provenance_class` and `relation_vocabulary` and nothing else
 * that filters (ADR 0005 invariant 7), so the URL spells them exactly as the
 * request does. A shorter alias would be a second vocabulary for one set of
 * filters, and a control named here but absent from
 * `Endpoints["getGraph"]["query"]` would be a filter the server never receives.
 * `graphFiltersOf` is the only translation, and it is an identity.
 *
 * **`focus` is ours, and it is an identity, not a position.** The selected
 * entity is named by its existing three-part `global_id` (D-011, ADR 0005
 * invariant 2) -- never by a label, an index into a page, or a synthesised
 * key. A search hit that states no `global_id` therefore has no Map address at
 * all: v1 emits no caption entities (D-023), and a caption hit given a made-up
 * id would be an address that resolves to nothing. `mapPath` cannot be made to
 * write one, because it re-reads every value through the same parser the Map
 * reads a URL with.
 *
 * **What is deliberately *not* in this grammar.** The search query is not:
 * D-119 names selection, source scope, provenance and relation vocabulary, and
 * a query in the URL would either write a history entry per keystroke or need
 * a second rule about when it does not. Peek is not, and must never be
 * (D-133): a hover that pushed history would fill the back stack with
 * positions the user never chose. Zoom, camera and layout are not: they are
 * the renderer's, and nothing in them is an identity the API can resolve.
 */

import type { IndexedRelation, ProvenanceClass } from "../api/contract";
import { PROVENANCE_CLASSES, RELATION_VOCABULARIES } from "../api/vocabulary";
import type { GraphFilters } from "../map/graphSnapshot";
import { splitGlobalId } from "./format";

/** The Map's route, as `App.tsx` declares it. */
export const MAP_PATH = "/map";

export type RelationVocabulary = IndexedRelation["relation_vocabulary"];

/**
 * The four parameter names, in the order `mapPath` writes them.
 *
 * Exported because a test that spelled them again would be testing its own
 * copy, and because `T-207` reads this grammar rather than re-deriving it.
 */
export const MAP_PARAMS = {
  mode: "of",
  focus: "focus",
  source: "source_id",
  provenance: "provenance_class",
  vocabulary: "relation_vocabulary",
} as const;

/**
 * Everything the Map's URL can state. Every field is `null` for "the URL says
 * nothing about this" -- which is not the same as a default, and is never
 * spelled out as one.
 */
/**
 * What a Map is a map *of*.
 *
 * Two modes over one field, not two routes: the workspace, the renderer seam,
 * the selection identity and the URL are shared, and what differs is which
 * records are drawn and what a selection means (D-244, D-277).
 */
export type MapMode = "knowledge" | "sources";

/** Every mode this Map understands, in the order the switch offers them. */
export const MAP_MODES: readonly MapMode[] = ["knowledge", "sources"];

/** The mode a URL that says nothing about it means. */
export const DEFAULT_MAP_MODE: MapMode = "knowledge";

export interface MapState {
  /**
   * Which Map this is. `null` is "the URL says nothing", which `modeOf` reads
   * as the Knowledge Map — a default applied at the point of use rather than
   * written into the state, exactly as the four filters are.
   */
  mode: MapMode | null;
  /** The focused entity's existing `global_id`, in either mode. */
  focus: string | null;
  /** Source scope, as `GET /api/graph`'s `source_id`. */
  source: string | null;
  /** Provenance filter, as `GET /api/graph`'s `provenance_class`. */
  provenance: ProvenanceClass | null;
  /** Relation-vocabulary filter, as `GET /api/graph`'s `relation_vocabulary`. */
  vocabulary: RelationVocabulary | null;
}

/** The Map at `#/map` with no parameters: nothing selected, nothing filtered. */
export const NO_MAP_STATE: MapState = {
  mode: null,
  focus: null,
  source: null,
  provenance: null,
  vocabulary: null,
};

/**
 * The mode a URL asks for, or `null` when it does not ask.
 *
 * An unreadable value is ignored rather than repaired, which is this grammar's
 * rule everywhere: reading `of=source` as `sources` would switch a reader to a
 * Map they did not ask for, and reading it as an error would refuse a link over
 * a parameter that is not load-bearing. Ignored means the Knowledge Map, which
 * is what a URL with no `of` at all means.
 */
export function parseMapMode(value: string | null | undefined): MapMode | null {
  return typeof value === "string" && (MAP_MODES as readonly string[]).includes(value)
    ? (value as MapMode)
    : null;
}

/** The mode a state means, with the default applied. */
export function modeOf(state: MapState): MapMode {
  return state.mode ?? DEFAULT_MAP_MODE;
}

/**
 * The focused `global_id` a URL asks for, or `null`.
 *
 * A value that is not a three-part identifier is ignored rather than repaired:
 * there is no honest way to turn `youtube:abc` into an entity id, and guessing
 * a third part would mint an address for a record that may not exist. Internal
 * whitespace is refused for the same reason -- no `IdPart` contains any, so a
 * value carrying it is not this id with a typo, it is not this id.
 *
 * What is *not* checked here is whether the entity exists. That is the
 * server's `404 not_found` to state, and a client that pre-judged it would
 * either need the whole index or would drop a valid link to an entity that has
 * not been loaded yet.
 */
export function parseFocus(value: string | null | undefined): string | null {
  if (typeof value !== "string" || value === "") return null;
  if (/\s/.test(value)) return null;
  return splitGlobalId(value) === null ? null : value;
}

/**
 * The source scope a URL asks for, or `null`.
 *
 * A `SourceId` is `<source-type>:<external-id>` (D-011) -- two parts, both
 * present. A three-part value here is a global id in the wrong parameter, and
 * truncating it to its first two parts would silently scope the Map to a
 * source the URL did not name.
 */
export function parseSourceScope(value: string | null | undefined): string | null {
  if (typeof value !== "string" || value === "") return null;
  if (/\s/.test(value)) return null;
  const parts = value.split(":");
  if (parts.length !== 2) return null;
  return parts[0] === "" || parts[1] === "" ? null : value;
}

/** The provenance filter a URL asks for, or `null`. Case-sensitive, like the API. */
export function parseProvenance(value: string | null | undefined): ProvenanceClass | null {
  return typeof value === "string" && (PROVENANCE_CLASSES as readonly string[]).includes(value)
    ? (value as ProvenanceClass)
    : null;
}

/** The relation-vocabulary filter a URL asks for, or `null`. */
export function parseVocabulary(value: string | null | undefined): RelationVocabulary | null {
  return typeof value === "string" && (RELATION_VOCABULARIES as readonly string[]).includes(value)
    ? (value as RelationVocabulary)
    : null;
}

/**
 * Read a whole Map URL.
 *
 * Each parameter is read independently, so one malformed value costs only
 * itself: `?focus=nonsense&provenance_class=derived` still filters by
 * provenance, and still selects nothing. A URL that states nothing this Map
 * understands parses to `NO_MAP_STATE` -- no selection, no filter, no
 * invention.
 */
export function parseMapState(query: URLSearchParams | string): MapState {
  const params = typeof query === "string" ? new URLSearchParams(query) : query;
  return {
    mode: parseMapMode(params.get(MAP_PARAMS.mode)),
    focus: parseFocus(params.get(MAP_PARAMS.focus)),
    source: parseSourceScope(params.get(MAP_PARAMS.source)),
    provenance: parseProvenance(params.get(MAP_PARAMS.provenance)),
    vocabulary: parseVocabulary(params.get(MAP_PARAMS.vocabulary)),
  };
}

/**
 * A Map URL. Omitted parameters are absent, never spelled as defaults.
 *
 * Every value goes back through the parser that reads it, so this function
 * cannot write a link its own reader would ignore: an unusable `focus` is
 * dropped here rather than becoming a selection that survives one navigation
 * and disappears on reload. That is what makes the round trip a property of
 * the grammar rather than a habit of its callers.
 */
export function mapPath(state: Partial<MapState> = {}): string {
  const query = new URLSearchParams();
  // `of=knowledge` is never written: the Knowledge Map is what a URL with no
  // mode means, and spelling a default is what this grammar does not do.
  const mode = parseMapMode(state.mode);
  if (mode !== null && mode !== DEFAULT_MAP_MODE) query.set(MAP_PARAMS.mode, mode);
  const focus = parseFocus(state.focus);
  if (focus !== null) query.set(MAP_PARAMS.focus, focus);
  const source = parseSourceScope(state.source);
  if (source !== null) query.set(MAP_PARAMS.source, source);
  const provenance = parseProvenance(state.provenance);
  if (provenance !== null) query.set(MAP_PARAMS.provenance, provenance);
  const vocabulary = parseVocabulary(state.vocabulary);
  if (vocabulary !== null) query.set(MAP_PARAMS.vocabulary, vocabulary);
  const search = query.toString();
  return search === "" ? MAP_PATH : `${MAP_PATH}?${search}`;
}

/**
 * The three filters this state asks `GET /api/graph` for.
 *
 * An identity, not a mapping: the URL spells the API's own parameter names, so
 * this only drops the `null`s -- a parameter the URL did not state is a
 * parameter the request does not carry, which is not the same as one carrying
 * an empty value. `focus` is absent on purpose: selection is not a graph
 * filter, and sending it as one would return a different graph for a selection
 * that is meant to change nothing about what is drawn.
 */
export function graphFiltersOf(state: MapState): GraphFilters {
  const filters: GraphFilters = {};
  if (state.source !== null) filters.source_id = state.source;
  if (state.provenance !== null) filters.provenance_class = state.provenance;
  if (state.vocabulary !== null) filters.relation_vocabulary = state.vocabulary;
  return filters;
}

/** Whether two Map states say the same thing. Used to avoid a pointless history entry. */
export function sameMapState(left: MapState, right: MapState): boolean {
  return (
    modeOf(left) === modeOf(right) &&
    left.focus === right.focus &&
    left.source === right.source &&
    left.provenance === right.provenance &&
    left.vocabulary === right.vocabulary
  );
}
