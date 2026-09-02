/**
 * The Map's search rail: the first step of D-130's journey (`T-206`).
 *
 * Search -> Preview/Peek -> Focus, all of it inside `#/map`. The rail is DOM,
 * not canvas, on purpose (D-120): searching, judging a result and selecting it
 * are keyboard-operable here, so none of the three depends on hit-testing a
 * WebGL surface. Every control below is a real `<button>`, `<input>` or
 * `<a>` -- activation is the platform's, which is what makes "pointer and
 * keyboard resolve the same `global_id`" a property of the markup rather than
 * a pair of handlers that must agree (W3C G202).
 *
 * **Two lists, labelled, never merged.** What the Map has loaded and what the
 * index holds are different claims, and `useMapSearch` explains at length why
 * ranking them into one list would require an invented score. The rail states
 * both counts instead: how many loaded nodes matched out of how many are
 * loaded, and how many hits the server counted -- or that it did not count,
 * which is never rendered as zero.
 *
 * **Selection has one entry point.** Every Focus button calls `onFocus` with
 * an existing `global_id`, which `MapView` wires to `useMapFocus.focusEntity`
 * -- the same function a Sigma `clickNode` handler must call. There is no
 * second path that could resolve a different identity.
 *
 * **Peek is the binding's, not the rail's** -- and since `T-208` it is not
 * *rendered* here either. `useMapPeek` is created above this component so that
 * the canvas and this list share one Peek (invariant 13); the rail spreads its
 * handlers onto the results it knows are loaded, so a pointer *or* a keyboard
 * focus over a result previews the same node, and a result the Map has not
 * loaded gets no handlers, because there is no record to show and one would
 * have to be invented.
 *
 * The card itself moved to the route, because this panel now folds: a Peek
 * opened by a pointer on the canvas while the rail was collapsed rendered
 * inside a closed `<details>`, which is a card nobody can see. Moving it to a
 * better surface was always allowed; rendering it twice was never (invariant
 * 13).
 */

import { useState } from "react";

import { Disclosure } from "./Disclosure";
import { ErrorState } from "./ErrorState";
import { useI18n } from "../i18n";
import type { MapGraph } from "../map/graphProjection";
import type { MapPeekBinding } from "../map/useMapPeek";
import { useMapSearch } from "../map/useMapSearch";
import { MapResultCard } from "./MapResultCard";
import { Mono } from "./primitives";

export function MapSearchRail({
  graph,
  revision,
  focus,
  onFocus,
  peek,
  sourceScope = null,
}: {
  /** The accumulated snapshot. `null` before the first page arrives. */
  graph: MapGraph | null;
  /** `snapshotId` or `pagesApplied`: the graph is mutated in place, so it needs one. */
  revision: number;
  /** The focused `global_id`, from `useMapFocus`. */
  focus: string | null;
  /** Focus an entity, or clear the focus with `null`. Writes Map history. */
  onFocus: (globalId: string | null) => void;
  /** The one Peek binding, shared with the canvas. */
  peek: MapPeekBinding;
  /** The Map's source scope, so the indexed search asks the same question the graph does. */
  sourceScope?: string | null;
}) {
  const { t } = useI18n();
  const [draft, setDraft] = useState("");
  const [query, setQuery] = useState("");
  const [includeTranscript, setIncludeTranscript] = useState(false);

  const search = useMapSearch({ query, graph, revision, includeTranscript, sourceId: sourceScope });
  const focusLoaded = focus !== null && graph !== null && graph.hasNode(focus);

  return (
    <Disclosure
      id="search"
      className="map__search"
      title={t("map.search.title")}
      // A folded rail still says what it found: `T-208` collapses the three
      // panels that compete for one screen, and a disclosure whose summary
      // reads only "Search this Map" hides the answer along with the form.
      summary={
        search.query === ""
          ? t("map.search.noQuery")
          : t("map.search.matched", { count: search.loaded.matched })
      }
      // Searching is the step D-130's journey is on while nothing is
      // selected; once something is, Quick Read and the related list are.
      // A preference, not a lock -- the reader may reopen it.
      preferOpen={focus === null}
      // Escape dismisses the Peek for the keyboard path, where there is no
      // "leave" event to end it.
      onKeyDown={(event) => {
        if (event.key === "Escape") peek.close();
      }}
    >
      <p className="faint">{t("map.search.hint")}</p>

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
            onClick={() => {
              setDraft("");
              setQuery("");
            }}
          >
            {t("search.clear")}
          </button>
        )}
      </form>

      {includeTranscript && <p className="faint">{t("map.search.transcriptNote")}</p>}

      <div className="row" data-map-focus={focus ?? ""}>
        <strong>{t("map.focus.title")}</strong>
        {focus === null ? (
          <span className="muted">{t("map.focus.none")}</span>
        ) : (
          <>
            <Mono>{focus}</Mono>
            {!focusLoaded && <span className="faint">{t("map.focus.notLoaded")}</span>}
            <button type="button" className="button" onClick={() => onFocus(null)}>
              {t("map.focus.clear")}
            </button>
          </>
        )}
      </div>

      {query !== "" && (
        <>
          <section className="stack" aria-label={t("map.search.loaded.title")}>
            <h3>{t("map.search.loaded.title")}</h3>
            <p className="faint" data-map-loaded-matches={search.loaded.matched}>
              {search.loaded.searched === 0
                ? t("map.search.loaded.none")
                : t("map.search.loaded.count", {
                    shown: search.loaded.items.length,
                    matched: search.loaded.matched,
                    searched: search.loaded.searched,
                  })}
            </p>
            {search.loaded.searched > 0 && search.loaded.matched === 0 && (
              <p className="muted">{t("map.search.loaded.empty")}</p>
            )}
            {search.loaded.items.map((preview) => (
              <MapResultCard
                key={preview.key}
                preview={preview}
                focused={preview.globalId === focus}
                onFocus={onFocus}
                peek={preview.globalId === null ? undefined : peek.handlers(preview.globalId)}
              />
            ))}
          </section>

          <section className="stack" aria-label={t("map.search.index.title")}>
            <h3>{t("map.search.index.title")}</h3>
            {sourceScope !== null && (
              <p className="faint">
                {t("map.search.index.scope", { source: sourceScope })}
              </p>
            )}
            {search.error !== null ? (
              <ErrorState error={search.error} onRetry={search.reload} />
            ) : search.status === "loading" ? (
              <p className="muted">{t("common.loading")}</p>
            ) : (
              <>
                <p className="faint">
                  {search.total === null
                    ? t("common.unknownTotal")
                    : t("common.total", { count: search.total })}
                </p>
                {search.indexed.length === 0 ? (
                  <p className="muted">{t("search.empty")}</p>
                ) : (
                  search.indexed.map((preview) => (
                    <MapResultCard
                      key={preview.key}
                      preview={preview}
                      focused={preview.globalId === focus}
                      onFocus={onFocus}
                      peek={
                        preview.loaded && preview.globalId !== null
                          ? peek.handlers(preview.globalId)
                          : undefined
                      }
                    />
                  ))
                )}
                {search.hasMore && (
                  <button
                    type="button"
                    className="button"
                    onClick={search.loadMore}
                    disabled={search.loadingMore}
                    data-map-search-more
                  >
                    {t("common.more")}
                  </button>
                )}
              </>
            )}
          </section>
        </>
      )}
    </Disclosure>
  );
}
