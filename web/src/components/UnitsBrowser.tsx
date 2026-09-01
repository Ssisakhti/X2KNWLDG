/**
 * Knowledge units across the listed sources, filtered by the server.
 *
 * A note on shape, because it is a contract fact and not a design whim: the
 * frozen surface filters knowledge units **per source**
 * (`/api/sources/{source_id}/entities` takes `provenance_class`, `kind` and
 * `min_confidence`). There is no cross-source entity list that accepts those
 * filters -- `/api/graph` takes `provenance_class` but neither `kind` nor
 * `min_confidence` -- so a library-wide filtered list is assembled here by
 * asking each source the same question and reporting each answer separately.
 *
 * That is why every group carries its own `total` and its own "more beyond
 * this page" note, and why no aggregate count is shown. Adding the numbers
 * would produce a total the server never computed, and a partial one at that.
 * Widening this is `openapi.json`'s business, not the frontend's.
 */

import { useMemo } from "react";

import { api } from "../api/client";
import type { EntityRef, KnowledgeKind, ProvenanceClass, Source } from "../api/contract";
import { useAsync } from "../api/useAsync";
import { ApiFailure } from "../api/errors";
import { useI18n } from "../i18n";
import { EntityCard } from "./EntityCard";
import { ErrorState } from "./ErrorState";

export interface UnitFilters {
  kind: KnowledgeKind | "";
  provenance: ProvenanceClass | "";
  minConfidence: string;
}

interface Group {
  source: Source;
  entities: EntityRef[];
  total: number | null;
  hasMore: boolean;
  error: ApiFailure | null;
}

const PAGE = 50;

async function loadGroup(
  source: Source,
  filters: UnitFilters,
  signal: AbortSignal,
): Promise<Group> {
  const query: {
    limit: number;
    provenance_class?: ProvenanceClass;
    kind?: KnowledgeKind;
    min_confidence?: number;
  } = { limit: PAGE };
  if (filters.provenance !== "") query.provenance_class = filters.provenance;
  if (filters.kind !== "") query.kind = filters.kind;
  const floor = Number.parseFloat(filters.minConfidence);
  if (filters.minConfidence !== "" && Number.isFinite(floor)) query.min_confidence = floor;

  try {
    const response = await api.call("listSourceEntities", {
      params: { source_id: source.id },
      query,
      signal,
    });
    return {
      source,
      entities: response.data,
      total: response.page.total ?? null,
      hasMore: response.page.next_cursor !== null,
      error: null,
    };
  } catch (cause) {
    if (cause instanceof DOMException && cause.name === "AbortError") throw cause;
    return {
      source,
      entities: [],
      total: null,
      hasMore: false,
      error:
        cause instanceof ApiFailure
          ? cause
          : new ApiFailure("internal", cause instanceof Error ? cause.message : String(cause)),
    };
  }
}

export function UnitsBrowser({
  sources,
  filters,
}: {
  sources: readonly Source[];
  filters: UnitFilters;
}) {
  const { t } = useI18n();
  const key = useMemo(() => sources.map((source) => source.id).join("|"), [sources]);

  const state = useAsync<Group[]>(
    async (signal) => {
      const groups: Group[] = [];
      for (const source of sources) {
        groups.push(await loadGroup(source, filters, signal));
      }
      return groups;
    },
    [key, filters.kind, filters.provenance, filters.minConfidence],
  );

  if (state.status === "loading") return <p className="muted">{t("common.loading")}</p>;
  if (state.error !== null) return <ErrorState error={state.error} onRetry={state.reload} />;

  const groups = state.data ?? [];
  const populated = groups.filter((group) => group.entities.length > 0 || group.error !== null);

  return (
    <div className="stack">
      <p className="faint">{t("library.unitsScopeNote")}</p>
      {populated.length === 0 && <p className="muted">{t("library.unitsEmpty")}</p>}
      {populated.map((group) => (
        <section key={group.source.id} className="stack">
          <h2 dir="auto">{group.source.title ?? group.source.id}</h2>
          {group.error !== null ? (
            <ErrorState error={group.error} />
          ) : (
            <>
              <p className="faint">
                {group.total === null
                  ? t("common.unknownTotal")
                  : t("common.total", { count: group.total })}
                {group.hasMore ? ` · ${t("common.more")}` : ""}
              </p>
              {group.entities.map((entity) => (
                <EntityCard key={entity.global_id} entity={entity} sourceUrl={group.source.url} />
              ))}
            </>
          )}
        </section>
      ))}
    </div>
  );
}
