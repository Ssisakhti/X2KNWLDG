/**
 * The Source Map (`T-256`), at `#/map?of=sources`.
 *
 * A second composition over the *same* workspace, not a second application:
 * the field, the floats, the one primary drawer, the renderer seam and the URL
 * grammar are `T-204`–`T-216`'s and are reused as they stand. What differs is
 * what is drawn and what a selection means, which is exactly the difference the
 * mode switch names.
 *
 * **What this view will not do**, each because a record does not support it
 * (D-247, D-274, D-277):
 *
 * - No mark is sized and no edge is weighted by anything. `basis_total` reaches
 *   the style table and is not read there; it is a *count*, said in words on
 *   every pill.
 * - Nothing anywhere states whether a relationship is still current. The v1
 *   shapes carry no per-relation staleness, so a freshness pip would be a claim
 *   with no record behind it.
 * - Run status is a badge on the one readable card and never a mark on the
 *   field, because a status is a fact about a *run* and a mark for it reads as
 *   a ranking of the source.
 *
 * **What is drawn is one page, and the page says so.** `/api/source-graph` pages
 * over nodes and returns its relations whole, so this view holds one page rather
 * than an accumulating snapshot — see `useSourceGraph` for why accumulating
 * would double-count. `counts` states returned, omitted and total separately,
 * and this view renders all three rather than adding them into one.
 *
 * **A relationship whose other end is not on this page is counted, not drawn.**
 * `projectSourceGraph` refuses to invent a mark for a node this page has no
 * record of; the count reaches the reader as a sentence and every such
 * relationship is still a row in the list.
 *
 * **The list is the accessible path.** Every source is a row in `SourceOutline`
 * and every returned relationship is a row in `SourceRelationList`, both
 * reachable with no pointer, no WebGL2 and nothing typed. The canvas is an
 * enhancement over that, which is why this view can render its whole journey
 * with no renderer at all.
 */

import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";

import { ApiFailure } from "../api/errors";
import { Disclosure } from "../components/Disclosure";
import { ErrorState } from "../components/ErrorState";
import { MapModeSwitch } from "../components/MapModeSwitch";
import { Bidi, Mono } from "../components/primitives";
import { SourceBriefCard } from "../components/SourceBriefCard";
import { SourceOutline } from "../components/SourceOutline";
import { SourceBasisPanel, SourceRelationList } from "../components/SourceRelations";
import { useI18n } from "../i18n";
import { sourceIdOf } from "../lib/format";
import { describeCanvas, type RendererFault } from "../map/mapState";
import { MapSession, type MapRendererFactory } from "../map/mapSession";
import type { SourceRelationSummary } from "../api/contract";
import { sourceStyle } from "../map/sourceStyle";
import type { BriefState } from "../map/sourceStyle";
import { stageBudget } from "../map/sourceNeighbourhood";
import { useSourceGraph, useSourceNeighbourhood } from "../map/useSourceGraph";
import { useMapFocus } from "../map/useMapFocus";

/** How many relationship cards one side of the stage carries, per tier. */
const PER_SIDE: Record<"full" | "compact" | "stack", number> = {
  full: 3,
  compact: 2,
  stack: 0,
};

/** The tier a measured field can hold, on `constellation.orbitTier`'s terms. */
function tierOf(width: number): "full" | "compact" | "stack" {
  if (width < 900) return "stack";
  return width < 2000 ? "compact" : "full";
}

export function SourceMapView({
  createRenderer,
}: {
  createRenderer?: MapRendererFactory<SourceRelationSummary>;
} = {}) {
  const { t } = useI18n();
  const focus = useMapFocus();
  const stage = useRef<HTMLDivElement | null>(null);
  const session = useRef<MapSession<SourceRelationSummary> | null>(null);
  const [fault, setFault] = useState<RendererFault | null>(null);
  const [drawn, setDrawn] = useState(false);
  const [fieldWidth, setFieldWidth] = useState(0);
  const [selectedRelation, setSelectedRelation] = useState<string | null>(null);

  const field = useSourceGraph();
  // The neighbourhood is asked for by the *two-part* id the endpoint takes,
  // derived from the focused node's three-part one in the one place that
  // derivation lives.
  const focusedSourceId = focus.focus === null ? null : sourceIdOf(focus.focus);
  const hood = useSourceNeighbourhood(focusedSourceId);

  const projection = field.data?.projection ?? null;
  const nodes = useMemo(
    () => (projection === null ? [] : [...projection.bySourceId.values()]),
    [projection],
  );
  const view = hood.data ?? null;

  /*
   * What is known about each source's brief.
   *
   * Exactly one entry, for the source that has been selected: a node's
   * `EntityRef` says nothing about whether it has a brief, and the graph
   * response carries no brief state at all. Every other source therefore reads
   * as `unavailable`, which is an honest under-claim — the alternative is a
   * fourth state meaning "not asked", and inventing a channel to say the API
   * was not asked is not a thing the field should be drawing.
   */
  const briefStates = useMemo<ReadonlyMap<string, BriefState>>(() => {
    const states = new Map<string, BriefState>();
    if (view !== null) states.set(view.centre.global_id, view.knowledge.state);
    return states;
  }, [view]);

  const tier = tierOf(fieldWidth);
  const budget = useMemo(
    () => (view === null ? null : stageBudget(PER_SIDE[tier], view)),
    [view, tier],
  );
  /** Which relationships the stage found room for. The list says so per row. */
  const placed = useMemo(() => {
    const ids = new Set<string>();
    for (const edge of budget?.incoming ?? []) ids.add(edge.relation.id);
    for (const edge of budget?.outgoing ?? []) ids.add(edge.relation.id);
    return ids;
  }, [budget]);

  /*
   * The selected relationship, which is the drawer's subject.
   *
   * Held here rather than in the URL. D-119 froze the Map's grammar at a
   * selection plus its filters, and a relationship is not a second selection: it
   * is a detail *of* the selected source, it changes nothing about what is
   * drawn, and putting it in the URL would push a history entry for reading a
   * panel. The first returned relationship is the default so the drawer is never
   * empty while a source has one.
   */
  // Memoised rather than defaulted inline: `view?.all ?? []` is a new array on
  // every render, which would make the memo below re-run on every render and
  // hand a new `selected` object to the drawer each time.
  const relations = useMemo(() => view?.all ?? [], [view]);
  const selected = useMemo(() => {
    if (relations.length === 0) return null;
    const chosen = relations.find((edge) => edge.relation.id === selectedRelation);
    return chosen ?? relations[0] ?? null;
  }, [relations, selectedRelation]);

  // A new source is a new question: the relationship a reader was reading about
  // belongs to the source they have left.
  useEffect(() => setSelectedRelation(null), [focusedSourceId]);

  const focusSource = useCallback(
    (globalId: string) => {
      focus.focusEntity(globalId === focus.focus ? null : globalId);
    },
    [focus],
  );

  /* ---- the renderer ---------------------------------------------------- */

  useLayoutEffect(() => {
    const container = stage.current;
    if (container === null) return;
    const measure = () => {
      const width = container.getBoundingClientRect().width;
      setFieldWidth(width);
      if (sourceStyle.setField(width)) session.current?.refresh();
      session.current?.resize();
    };
    measure();
    // `ResizeObserver` is not in jsdom, and the fallback is not a test
    // affordance: a browser without it still has to draw, and `MapView` has
    // carried the same pair since `T-204`. The window event is coarser and is
    // the honest second choice rather than a stub.
    if (typeof ResizeObserver === "undefined") {
      window.addEventListener("resize", measure);
      return () => window.removeEventListener("resize", measure);
    }
    const observer = new ResizeObserver(measure);
    observer.observe(container);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const container = stage.current;
    if (container === null || projection === null) return;
    let cancelled = false;

    const attach = async () => {
      const injected = createRenderer;
      const factory: MapRendererFactory<SourceRelationSummary> =
        injected ??
        (await import("../map/sigmaRenderer").then((module) =>
          module.sigmaRendererFor<SourceRelationSummary>(sourceStyle),
        ));
      if (cancelled) return;
      const next = new MapSession<SourceRelationSummary>({
        container,
        createRenderer: factory,
        handlers: {
          // The canvas is a third caller of the same selection, never a second
          // identity: a click on a mark calls what a row calls (`T-207`).
          onSelectNode: (globalId: string) => focusSource(globalId),
        },
      });
      session.current?.kill();
      session.current = next;
      try {
        next.attach(projection.graph);
        setFault(null);
        setDrawn(projection.graph.order > 0);
      } catch (error) {
        setFault({ phase: "create", detail: String(error) });
        setDrawn(false);
      }
    };

    attach().catch((error: unknown) => {
      if (!cancelled) {
        setFault({ phase: "module", detail: String(error) });
        setDrawn(false);
      }
    });

    return () => {
      cancelled = true;
      session.current?.kill();
      session.current = null;
    };
    // `focusSource` is deliberately absent: re-creating the renderer whenever a
    // selection changes would throw the layout away on every click.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projection, createRenderer]);

  // Selection and hover are written into the style table, and the renderer
  // redraws without relaxing the layout — `update()` would, and the picture
  // would jump on every click.
  useEffect(() => {
    const changed = sourceStyle.setView({
      selectedNode: focus.focus,
      neighbourNodes: new Set(
        (view?.all ?? [])
          .map((edge) => edge.other?.global_id)
          .filter((id): id is string => typeof id === "string"),
      ),
      briefStates,
    });
    if (changed) session.current?.refresh();
  }, [focus.focus, view, briefStates]);

  /*
   * The camera goes to the selection (D-146).
   *
   * Without this a reader selects a source from the list, the drawer fills, and
   * the mark they selected is wherever the layout happened to put it — which on
   * a real corpus was off the visible field. `frame` is the renderer's own
   * question, because a camera is addressed in framed coordinates rather than
   * in graph units, and it takes the neighbours so the relationships a reader
   * is about to read are in the picture with their source.
   */
  useEffect(() => {
    if (focus.focus === null || view === null) return;
    const neighbours = view.all
      .map((edge) => edge.other?.global_id)
      .filter((id): id is string => typeof id === "string");
    session.current?.frame(focus.focus, neighbours);
    // `drawn` is in the deps because a URL that arrives *with* a focus runs this
    // before the graph is attached: React runs a render, then its effects, and
    // the attach is one of them. Without it, opening a link to a selected source
    // left the camera wherever the layout started.
  }, [focus.focus, view, drawn]);

  const picture = describeCanvas({
    fault,
    // "A live renderer is holding the graph *now*", which is not the same as
    // "a factory arrived": the render that first sees a page precedes the
    // effect that hands the graph over, and a canvas described as drawing
    // during that render describes something that has not happened (D-207).
    holding: drawn,
    nodes: projection?.graph.order ?? 0,
  });

  const counts = field.data?.counts ?? null;
  const offPage = projection?.offPage.length ?? 0;

  return (
    <div
      className={`map map--sources${focus.focus === null ? "" : " map--focused"}`}
      data-map-of="sources"
      data-map-canvas={picture.kind}
      data-map-tier={tier}
    >
      <h1 className="visually-hidden">{t("source.map.title")}</h1>
      <p className="visually-hidden">{t("source.map.subtitle")}</p>

      {/* The field's top start: the mode, the companion sentence, the list. */}
      <div className="map__float map__float--search stack" data-map-chrome>
        <MapModeSwitch mode={focus.state.mode} onChange={focus.setMode} />

        <p className="faint" data-map-stage-companion>
          {t("source.map.companion")}
        </p>

        {focus.focus === null && (
          <p className="muted" data-source-nothing-focused>
            {t("source.map.nothingFocused")}
          </p>
        )}

        <SourceOutline
          sources={nodes}
          focus={focus.focus}
          onFocus={focusSource}
          briefStates={briefStates}
          // The companion opens itself whenever it is the only view of the
          // graph: no renderer, a refused container, or nothing drawn yet.
          preferOpen={picture.kind !== "drawing"}
        />
      </div>

      {/*
        The counts, before the stage in the DOM (D-129): this is the text that
        survives when the WebGL view cannot be read at all, and a Map whose only
        honest description came after the picture would read as complete to
        anyone who never reaches it.
      */}
      <div className="map__float map__float--status stack" data-map-chrome>
        {counts !== null && (
          <Disclosure
            id="source-counts"
            className="map__state"
            title={t("map.state.title")}
            summary={t("source.counts.summary", {
              sources: counts.sources_returned,
              relations: counts.relations_returned,
            })}
            preferOpen={picture.kind !== "drawing"}
            marks={{
              "data-source-returned": String(counts.sources_returned),
              "data-source-relations-returned": String(counts.relations_returned),
              "data-source-omitted": String(counts.relations_omitted),
              "data-source-total": String(counts.sources_total ?? ""),
              "data-source-offpage": String(offPage),
              "data-source-truncated": String(field.data?.truncated ?? false),
            }}
          >
            <dl className="definitions">
              <dt>{t("source.counts.returned")}</dt>
              <dd>{counts.sources_returned}</dd>
              <dt>{t("source.counts.relations")}</dt>
              <dd>{counts.relations_returned}</dd>
              <dt>{t("source.counts.omitted")}</dt>
              <dd>
                {counts.relations_omitted}
                {counts.relations_omitted > 0 && (
                  <span className="faint"> — {t("source.counts.omittedNote")}</span>
                )}
              </dd>
              <dt>{t("source.counts.total")}</dt>
              <dd>{counts.sources_total ?? t("common.unknownTotal")}</dd>
              <dt>{t("map.state.extent")}</dt>
              <dd>
                {field.data?.truncated === true
                  ? t("map.state.partial")
                  : t("map.state.complete")}
              </dd>
            </dl>
            {offPage > 0 && (
              <p className="faint" data-source-offpage-note>
                {t("source.counts.offPage")}
              </p>
            )}
            <h3 className="section__title">{t("source.refusals.title")}</h3>
            <ul className="refusals">
              <li>{t("source.refusals.rank")}</li>
              <li>{t("source.refusals.freshness")}</li>
            </ul>
          </Disclosure>
        )}
      </div>

      {/* The honest states, centred on the field. */}
      <div className="map__notices">
        {field.error instanceof ApiFailure && (
          <ErrorState error={field.error} onRetry={field.reload} />
        )}
        {field.status === "loading" && <p className="notice muted">{t("map.reading.loading")}</p>}
        {field.status === "ready" && nodes.length === 0 && (
          <p className="notice muted">{t("source.empty")}</p>
        )}
        {picture.kind === "unavailable" && (
          <div className="notice notice--unavailable" role="alert" data-map-renderer-unavailable>
            <strong>{t("map.renderer.unavailable")}</strong>
            <p>{t("map.renderer.unavailableNote")}</p>
            <Bidi as="p" className="faint">
              {picture.detail}
            </Bidi>
          </div>
        )}
        {picture.kind === "refused" && (
          <div className="notice notice--unavailable" role="alert" data-map-renderer-failed>
            <strong>{t("map.renderer.failed")}</strong>
            <p>{t("map.renderer.failedNote")}</p>
            <Bidi as="p" className="faint">
              {picture.detail}
            </Bidi>
          </div>
        )}
      </div>

      <div className="map__canvas">
        <div
          ref={stage}
          className="map__stage"
          role={picture.kind === "drawing" ? "img" : undefined}
          aria-label={picture.kind === "drawing" ? t("source.map.stageLabel") : undefined}
          aria-hidden={picture.kind === "drawing" ? undefined : true}
          data-map-stage
        />
      </div>

      {/* The one primary drawer, on demand: a focus is the demand. */}
      <div className="map__endrail">
        {focus.focus !== null && (
          <div className="map__drawer" data-map-chrome>
            {hood.error instanceof ApiFailure ? (
              <div className="notice" role="alert" data-source-unknown>
                <strong>{t("source.unknown.title")}</strong>
                <p>{t("source.unknown.note")}</p>
                <p className="faint">
                  <Mono>{focusedSourceId ?? focus.focus}</Mono>
                </p>
                <ErrorState error={hood.error} onRetry={hood.reload} />
              </div>
            ) : hood.status === "loading" ? (
              <p className="muted">{t("source.brief.loading")}</p>
            ) : view !== null ? (
              <>
                <SourceBriefCard
                  source={view.centre}
                  knowledge={view.knowledge}
                  compact={tier !== "full"}
                />

                <section className="drawer__section">
                  <h2 className="section__title">
                    {t("source.relations.title")} ·{" "}
                    {t("source.relations.count", {
                      incoming: view.incoming.length,
                      outgoing: view.outgoing.length,
                    })}
                  </h2>

                  {((budget !== null && budget.omitted > 0) || view.truncated) && (
                    <div className="faint">
                      <h3 className="section__title">{t("source.bound.title")}</h3>
                      {budget !== null && budget.omitted > 0 && (
                        <p data-source-stage-omitted={String(budget.omitted)}>
                          {t("source.bound.stage", { count: budget.omitted })}
                        </p>
                      )}
                      {view.truncated && (
                        <p data-source-neighbourhood-truncated>
                          {t("source.bound.bothDirections")}
                        </p>
                      )}
                    </div>
                  )}

                  <SourceRelationList
                    edges={relations}
                    selected={selected?.relation.id ?? null}
                    onSelect={setSelectedRelation}
                    onFocusSource={focusSource}
                    placed={placed}
                  />
                </section>

                {selected !== null && <SourceBasisPanel relation={selected.relation} />}
              </>
            ) : null}
          </div>
        )}

        {/*
          The camera's controls, as the rail's last child rather than a float in
          the same corner — SPEC §8's *Focus Not Obscured* reading, which the
          Knowledge Map already follows: a drawer painted over the zoom buttons
          is a reader who cannot zoom the graph they are reading about.
          Measuring the running build is what found these missing here at all.
        */}
        <div className="map__zoom row" role="group" aria-label={t("map.controls")} data-map-chrome>
          <button
            type="button"
            className="button"
            onClick={() => session.current?.zoomIn()}
            disabled={picture.kind !== "drawing"}
          >
            {t("map.zoomIn")}
          </button>
          <button
            type="button"
            className="button"
            onClick={() => session.current?.zoomOut()}
            disabled={picture.kind !== "drawing"}
          >
            {t("map.zoomOut")}
          </button>
          <button
            type="button"
            className="button"
            onClick={() => session.current?.resetView()}
            disabled={picture.kind !== "drawing"}
          >
            {t("map.resetView")}
          </button>
        </div>
      </div>
    </div>
  );
}
