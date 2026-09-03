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

import { useEffect, useMemo, useState } from "react";

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

/**
 * How long a filter has to hold still before the fan-out below runs.
 *
 * Long enough that typing "0.85" is one pass rather than four, short enough
 * that it reads as immediate.
 */
const FILTER_SETTLE_MS = 250;

/** How many of the fan-out's requests are allowed to be in flight at once. */
const UNITS_CONCURRENCY = 6;

/** *filters*, but only once they have held still for {@link FILTER_SETTLE_MS}. */
function useSettledFilters(filters: UnitFilters): UnitFilters {
  const [settled, setSettled] = useState(filters);
  const { kind, provenance, minConfidence } = filters;
  useEffect(() => {
    const timer = setTimeout(
      () => setSettled({ kind, provenance, minConfidence }),
      FILTER_SETTLE_MS,
    );
    return () => clearTimeout(timer);
  }, [kind, provenance, minConfidence]);
  return settled;
}

/**
 * Every source's units, in the sources' own order, a few requests at a time.
 *
 * This was `for (const source of sources) groups.push(await loadGroup(...))`:
 * fifty strictly serial round trips with nothing rendered until the last
 * landed. Bounded rather than unbounded parallelism — fifty at once is a
 * thundering herd at a single-threaded local server, and the point is to stop
 * waiting for each answer before asking the next question, not to ask them all
 * at once. The results keep the sources' order whatever order they arrive in,
 * because that order is the Library's.
 */
async function loadGroups(
  sources: readonly Source[],
  filters: UnitFilters,
  signal: AbortSignal,
): Promise<Group[]> {
  const groups: Group[] = new Array<Group>(sources.length);
  let next = 0;
  const worker = async (): Promise<void> => {
    for (;;) {
      const index = next;
      next += 1;
      const source = sources[index];
      if (source === undefined) return;
      groups[index] = await loadGroup(source, filters, signal);
    }
  };
  await Promise.all(
    Array.from({ length: Math.min(UNITS_CONCURRENCY, sources.length) }, worker),
  );
  return groups;
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

  /*
   * The filters, one beat behind the keyboard (D-203).
   *
   * `minConfidence` is an unthrottled `onChange` on a number input, so every
   * keypress used to restart the whole fan-out below — fifty round trips per
   * character typed, each one aborted by the next. Settled here rather than at
   * the control, because it is *this* fan-out that makes a keystroke
   * expensive: the same filters drive nothing else that costs a request.
   */
  const settled = useSettledFilters(filters);

  const state = useAsync<Group[]>(
    (signal) => loadGroups(sources, settled, signal),
    [key, settled.kind, settled.provenance, settled.minConfidence],
  );

  if (state.status === "loading") {
    // Announced, not merely shown (D-203): a bare `<p class="muted">` says
    // nothing to a reader who cannot see it.
    return (
      <p className="muted" role="status">
        {t("common.loadingNamed", { name: t("library.mode.units") })}
      </p>
    );
  }
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
