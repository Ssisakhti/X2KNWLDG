/**
 * The three filters `GET /api/graph` actually accepts (`T-205`).
 *
 * ADR 0005 invariant 7: a control described as server-backed must exist in the
 * generated `Endpoints["getGraph"]["query"]` type. That type has five members
 * -- `limit`, `cursor`, `source_id`, `provenance_class` and
 * `relation_vocabulary` -- and the first two are the walk's, not the user's.
 * So this component offers exactly three controls and its value is typed
 * `GraphFilters`, which is that query type with the paging removed. A fourth
 * control could not be added here without the compiler asking which query
 * parameter it was supposed to be.
 *
 * **There is no `kind` filter, and its absence is the point.** `kind` is the
 * most obviously useful thing to filter a knowledge graph by, and the frozen
 * operation does not accept one: a `kind` control here would either filter in
 * the browser -- presenting a page the server never produced as though it had
 * -- or send a parameter the server ignores while the UI claims the graph was
 * filtered. Widening it is an OpenAPI decision first. Kind is styled and named
 * in `MapLegend` instead, which is what the alternatives table in ADR 0005
 * says it is for.
 *
 * **Changing a filter is a new question, not a redraw.** The component's only
 * job is to produce the value; `useGraphWalk`'s `deps` do the rest, and the
 * walk answers by cancelling the request in flight and building a new snapshot
 * with its own graph, so two filter sets can never share one drawing (D-118,
 * invariant 5).
 *
 * The source list is the one thing here that has to be fetched, because a
 * filter that cannot enumerate its options is not a filter. It is fetched
 * defensively: a refusal disables that one control and states itself, while
 * the other two keep working, because the graph is still perfectly filterable
 * by provenance and vocabulary when `/api/sources` is unavailable.
 *
 * **Strings are local to this file.** The shared catalogue is the integrator's
 * (§8.6); the labels that already exist there -- `provenance.*`,
 * `vocabulary.*`, `common.any` -- are reused through `t` rather than restated.
 */

import { api } from "../api/client";
import type { ProvenanceClass, Source } from "../api/contract";
import { ApiFailure } from "../api/errors";
import { useAsync } from "../api/useAsync";
import { PROVENANCE_CLASSES, RELATION_VOCABULARIES } from "../api/vocabulary";
import { useI18n } from "../i18n";
import type { GraphFilters } from "../map/graphSnapshot";
import type { RelationVocabulary } from "../map/mapStyle";

/**
 * How many sources the filter asks for in one request.
 *
 * One page, deliberately: this control is a filter, not a browser of sources,
 * and a walk here would be a second pagination rule for a list the Library
 * already pages properly. When the response says there are more, the control
 * says so (`map.filters.moreSources`) rather than presenting the page it got
 * as the set of sources that exist -- the same rule the Map applies to a
 * partial graph (D-123).
 */
export const MAP_FILTER_SOURCE_LIMIT = 200;

/**
 * A filter value with only the filters that are actually set.
 *
 * An unset control contributes no key at all rather than an `undefined` one,
 * so `Object.keys(value)` is the honest answer to "what is this snapshot
 * filtered by" -- which is the question `MapView` has to be able to answer
 * beside its counts.
 */
export function graphFilters(
  sourceId: string,
  provenance: string,
  vocabulary: string,
): GraphFilters {
  const filters: GraphFilters = {};
  if (sourceId !== "") filters.source_id = sourceId;
  if (provenance !== "") filters.provenance_class = provenance as ProvenanceClass;
  if (vocabulary !== "") filters.relation_vocabulary = vocabulary as RelationVocabulary;
  return filters;
}

export function MapFilters({
  value,
  onChange,
  sources,
}: {
  value: GraphFilters;
  onChange: (filters: GraphFilters) => void;
  /** Supplied by a view that already holds the list; fetched here otherwise. */
  sources?: readonly Source[];
}) {
  const { t } = useI18n();

  const fetched = useAsync(
    (signal) => api.call("listSources", { query: { limit: MAP_FILTER_SOURCE_LIMIT }, signal }),
    [],
    { enabled: sources === undefined },
  );

  const options: readonly Source[] = sources ?? fetched.data?.data ?? [];
  const moreSources =
    sources === undefined && fetched.data !== null && fetched.data.page.next_cursor !== null;
  const sourcesFailed = sources === undefined && fetched.error instanceof ApiFailure;

  const sourceId = value.source_id ?? "";
  const provenance = value.provenance_class ?? "";
  const vocabulary = value.relation_vocabulary ?? "";

  return (
    <div className="stack" data-map-filters>
      <div className="filters" role="group" aria-label={t("map.filters.group")}>
        <label className="field">
          {t("map.filters.source")}
          <select
            value={sourceId}
            data-map-filter="source_id"
            disabled={options.length === 0}
            onChange={(event) => onChange(graphFilters(event.target.value, provenance, vocabulary))}
          >
            <option value="">{t("common.any")}</option>
            {options.map((source) => (
              <option key={source.id} value={source.id}>
                {source.title ?? source.id}
              </option>
            ))}
          </select>
        </label>

        <label className="field">
          {t("library.filter.sourceClass")}
          <select
            value={provenance}
            data-map-filter="provenance_class"
            onChange={(event) => onChange(graphFilters(sourceId, event.target.value, vocabulary))}
          >
            <option value="">{t("common.any")}</option>
            {PROVENANCE_CLASSES.map((option) => (
              <option key={option} value={option}>
                {t(`provenance.${option}`)}
              </option>
            ))}
          </select>
        </label>

        <label className="field">
          {t("map.filters.vocabulary")}
          <select
            value={vocabulary}
            data-map-filter="relation_vocabulary"
            onChange={(event) => onChange(graphFilters(sourceId, provenance, event.target.value))}
          >
            <option value="">{t("common.any")}</option>
            {RELATION_VOCABULARIES.map((option) => (
              <option key={option} value={option}>
                {t(`vocabulary.${option}`)}
              </option>
            ))}
          </select>
        </label>
      </div>

      <p className="faint">{t("map.filters.note")}</p>
      {moreSources && <p className="faint">{t("map.filters.moreSources")}</p>}
      {sourcesFailed && (
        <p className="faint" data-map-filter-sources-failed={fetched.error?.code}>
          {t("map.filters.sourcesFailed")}
        </p>
      )}
    </div>
  );
}
