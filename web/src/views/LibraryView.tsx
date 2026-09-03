/**
 * The Library (`T-111`): sources in a list or a compact grid, search, and the
 * five filters.
 *
 * Where each filter is served from, because the split is a contract fact:
 *
 * | Filter          | Endpoint                        | Parameter          |
 * |-----------------|---------------------------------|--------------------|
 * | source type     | `/api/sources`                  | `source_type`      |
 * | validation      | `/api/sources`                  | `status`           |
 * | kind            | `/api/sources/{id}/entities`    | `kind`             |
 * | source class    | `/api/sources/{id}/entities`    | `provenance_class` |
 * | confidence      | `/api/sources/{id}/entities`    | `min_confidence`   |
 *
 * The first two describe a source, the last three describe a knowledge unit,
 * so the view has two modes rather than one filter bar that silently means
 * different things. No filter is applied client-side: a page filtered in the
 * browser would report a count the server never produced.
 *
 * The index panel is rendered before anything else, and an `index_unavailable`
 * refusal is rendered as itself. An unbuilt index must never be shown as an
 * empty library.
 */

import { useMemo, useState } from "react";

import { api } from "../api/client";
import type { RunStatus, Source } from "../api/contract";
import { useAsync } from "../api/useAsync";
import { usePaged } from "../api/usePaged";
import { KNOWLEDGE_KINDS, PROVENANCE_CLASSES, RUN_STATUSES } from "../api/vocabulary";
import { ErrorState } from "../components/ErrorState";
import { PagedList } from "../components/PagedList";
import { IndexStatusPanel } from "../components/IndexStatus";
import { SearchResults } from "../components/SearchResults";
import { SourceCard } from "../components/SourceCard";
import { UnitsBrowser, type UnitFilters } from "../components/UnitsBrowser";
import { useI18n } from "../i18n";
import { withFocusRescue } from "../lib/focusRescue";

type Mode = "sources" | "units";
type Layout = "list" | "grid";

const PAGE = 50;

function Toggle<T extends string>({
  value,
  options,
  onChange,
  label,
}: {
  value: T;
  options: readonly { value: T; label: string }[];
  onChange: (value: T) => void;
  label: string;
}) {
  return (
    <div className="row" role="group" aria-label={label}>
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          className="button"
          aria-pressed={option.value === value}
          onClick={() => onChange(option.value)}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}

export function LibraryView() {
  const { t } = useI18n();

  const [mode, setMode] = useState<Mode>("sources");
  const [layout, setLayout] = useState<Layout>("list");
  const [sourceType, setSourceType] = useState("");
  const [runStatus, setRunStatus] = useState<RunStatus | "">("");
  const [draft, setDraft] = useState("");
  const [query, setQuery] = useState("");
  const [includeTranscript, setIncludeTranscript] = useState(true);
  const [unitFilters, setUnitFilters] = useState<UnitFilters>({
    kind: "",
    provenance: "",
    minConfidence: "",
  });

  const indexStatus = useAsync((signal) => api.call("getStatus", { signal }), []);

  /*
   * The `source_type` vocabulary, from the status payload already on the wire
   * (D-203).
   *
   * This used to be a second, unfiltered `listSources` at `limit: 500` on
   * every mount — five hundred records fetched, parsed and thrown away to
   * populate one `<select>`, beside the paged request that answers the page.
   *
   * `/api/status` carries `adapters`, and `adapters[].name` **is** the
   * `source_type`: `adapt_project` builds that list from each adapter's own
   * `source_type`, and `sourceType`'s schema is the same
   * `common.schema.json#/$defs/sourceType`. So the vocabulary was already
   * being fetched, twice a mount, and only one of the two requests had to
   * exist.
   *
   * It keeps the original reason for not hard-coding a list — the set is open
   * by design and a new adapter must not silently fall out of it. What changes
   * is that the answer now comes from the *registered* adapters rather than
   * from whichever types the first five hundred records happened to include:
   * strictly more honest, because a filter offered for a type with no indexed
   * sources says "0 total" while a type missing from a truncated page said
   * nothing at all.
   */
  const sourceTypes = useMemo(() => {
    const seen = new Set<string>();
    for (const adapter of indexStatus.data?.data.adapters ?? []) seen.add(adapter.name);
    return [...seen].sort();
  }, [indexStatus.data]);

  const sources = usePaged<Source>(
    async (cursor, signal) => {
      const response = await api.call("listSources", {
        query: {
          limit: PAGE,
          ...(sourceType === "" ? {} : { source_type: sourceType }),
          ...(runStatus === "" ? {} : { status: runStatus }),
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
    [sourceType, runStatus],
  );

  return (
    <div className="stack">
      <h1>{t("library.title")}</h1>
      <p className="muted">{t("app.subtitle")}</p>

      {indexStatus.error !== null ? (
        <ErrorState error={indexStatus.error} onRetry={indexStatus.reload} />
      ) : (
        indexStatus.data !== null && <IndexStatusPanel status={indexStatus.data.data} />
      )}

      <form
        className="row"
        role="search"
        onSubmit={(event) => {
          event.preventDefault();
          setQuery(draft.trim());
        }}
      >
        <label className="field">
          <span className="visually-hidden">{t("search.label")}</span>
          <input
            type="search"
            dir="auto"
            value={draft}
            placeholder={t("search.placeholder")}
            aria-label={t("search.label")}
            onChange={(event) => setDraft(event.currentTarget.value)}
          />
        </label>
        <button type="submit" className="button">
          {t("search.submit")}
        </button>
        <label className="row">
          <input
            type="checkbox"
            checked={includeTranscript}
            onChange={(event) => setIncludeTranscript(event.currentTarget.checked)}
          />
          {t("search.includeTranscript")}
        </label>
        {query !== "" && (
          <button
            type="button"
            className="button"
            onClick={withFocusRescue(() => {
              setDraft("");
              setQuery("");
            })}
          >
            {t("search.clear")}
          </button>
        )}
      </form>

      {query !== "" ? (
        <SearchResults query={query} includeTranscript={includeTranscript} />
      ) : (
        <>
          <div className="filters">
            <Toggle<Mode>
              value={mode}
              onChange={setMode}
              label={t("library.group.mode")}
              options={[
                { value: "sources", label: t("library.mode.sources") },
                { value: "units", label: t("library.mode.units") },
              ]}
            />
            {mode === "sources" && (
              <Toggle<Layout>
                value={layout}
                onChange={setLayout}
                label={t("library.group.layout")}
                options={[
                  { value: "list", label: t("library.view.list") },
                  { value: "grid", label: t("library.view.grid") },
                ]}
              />
            )}

            <label className="field">
              {t("library.filter.sourceType")}
              <select
                value={sourceType}
                onChange={(event) => setSourceType(event.currentTarget.value)}
              >
                <option value="">{t("common.any")}</option>
                {sourceTypes.map((value) => (
                  <option key={value} value={value}>
                    {value}
                  </option>
                ))}
              </select>
            </label>

            <label className="field">
              {t("library.filter.status")}
              <select
                value={runStatus}
                onChange={(event) => setRunStatus(event.currentTarget.value as RunStatus | "")}
              >
                <option value="">{t("common.any")}</option>
                {RUN_STATUSES.map((value) => (
                  <option key={value} value={value}>
                    {value}
                  </option>
                ))}
              </select>
            </label>

            {mode === "units" && (
              <>
                <label className="field">
                  {t("library.filter.kind")}
                  <select
                    value={unitFilters.kind}
                    onChange={(event) =>
                      setUnitFilters((current) => ({
                        ...current,
                        kind: event.currentTarget.value as UnitFilters["kind"],
                      }))
                    }
                  >
                    <option value="">{t("common.any")}</option>
                    {KNOWLEDGE_KINDS.map((value) => (
                      <option key={value} value={value}>
                        {value}
                      </option>
                    ))}
                  </select>
                </label>

                <label className="field">
                  {t("library.filter.sourceClass")}
                  <select
                    value={unitFilters.provenance}
                    onChange={(event) =>
                      setUnitFilters((current) => ({
                        ...current,
                        provenance: event.currentTarget.value as UnitFilters["provenance"],
                      }))
                    }
                  >
                    <option value="">{t("common.any")}</option>
                    {PROVENANCE_CLASSES.map((value) => (
                      <option key={value} value={value}>
                        {value}
                      </option>
                    ))}
                  </select>
                </label>

                <label className="field">
                  {t("library.filter.minConfidence")}
                  <input
                    type="number"
                    min={0}
                    max={1}
                    step={0.05}
                    value={unitFilters.minConfidence}
                    onChange={(event) =>
                      setUnitFilters((current) => ({
                        ...current,
                        minConfidence: event.currentTarget.value,
                      }))
                    }
                  />
                </label>
              </>
            )}
          </div>

          {/*
            Units mode is a different view of the same walk rather than a
            different ladder: `UnitsBrowser` takes the loaded sources and does
            its own fetching, so it replaces the item area and keeps its own
            statuses. Everything else goes through the one ladder (D-203).
          */}
          {mode === "units" ? (
            sources.error !== null ? (
              <ErrorState error={sources.error} onRetry={sources.reload} />
            ) : sources.status === "loading" ? (
              <p className="muted" role="status">
                {t("common.loadingNamed", { name: t("library.title") })}
              </p>
            ) : (
              <UnitsBrowser sources={sources.items} filters={unitFilters} />
            )
          ) : (
            <PagedList
              state={sources}
              label={t("library.title")}
              empty={t("library.empty")}
            >
              {(loaded) => (
                <div className={layout === "grid" ? "library__grid" : "library__list"}>
                  {loaded.map((source) => (
                    <SourceCard key={source.id} source={source} compact={layout === "grid"} />
                  ))}
                </div>
              )}
            </PagedList>
          )}
        </>
      )}
    </div>
  );
}
