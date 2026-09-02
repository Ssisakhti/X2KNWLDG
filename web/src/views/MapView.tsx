/**
 * The Knowledge Map at `#/map` (`T-204`).
 *
 * The first task that puts a graph on screen, and deliberately the *shell*: it
 * owns the address, the renderer's life and death, the container's size, the
 * camera, and the honest statement of what the snapshot holds. The provenance
 * and kind style matrix is `T-205`'s, the URL grammar and search are `T-206`'s,
 * and selection, neighbourhood and the inspector are `T-207`'s. None of them is
 * begun here, so none of them is begun twice.
 *
 * **What the drawing is allowed to claim.** A graph page is not a graph
 * (D-059), and the last page of a paged walk still reports `truncated`
 * (D-123), so the counts beside the canvas are read from `GraphSnapshot.state`
 * rather than recomputed: nodes loaded against the total the server counted,
 * edges drawn, edges held until their far endpoint arrives, and whether the
 * accumulated graph is the whole one. The real 86-node/118-edge sample fits a
 * single request at the contract maximum and says so; a larger library stays
 * visibly partial until someone loads the rest.
 *
 * That statement is rendered *before* the canvas on purpose. It is the text
 * that survives when the WebGL view cannot be read at all -- by a screen
 * reader, or in a browser with no WebGL2 -- and a Map whose only honest
 * description came after the picture would be a Map that reads as complete to
 * anyone who never reaches the picture. The full semantic companion, the
 * keyboard walk and the bidi rules are `T-208`'s.
 *
 * **The renderer is injected, and loaded on demand.** `createRenderer` is
 * replaced by a fake in the tests, because jsdom has no WebGL: the sequence
 * that matters -- a replacement kills its predecessor, unmount kills the last
 * one, and nothing outlives the route -- is only assertable against a fake,
 * and the real renderer is walked in a browser where the question can be
 * answered (ADR 0005 invariant 10, and `T-202`'s recorded walk).
 *
 * When nothing is injected, Sigma is reached through a dynamic `import` rather
 * than a static one. That is not a preference: `sigma` touches
 * `WebGL2RenderingContext` while its module body evaluates, so a static import
 * anywhere in the application's graph throws a `ReferenceError` on load in
 * jsdom -- which would take the Library's and the Reader's own test suites
 * down with it, none of which has anything to do with the Map. Loading it
 * where it is used also keeps the renderer out of the initial bundle for the
 * two routes that never draw a graph.
 */

import { useCallback, useEffect, useRef, useState } from "react";

import { api } from "../api/client";
import { ApiFailure } from "../api/errors";
import { ErrorState } from "../components/ErrorState";
import { useI18n } from "../i18n";
import { GraphConflictError } from "../map/graphProjection";
import type { GraphFilters } from "../map/graphSnapshot";
import { apiGraphPages } from "../map/graphWalk";
import { MapSession, type MapRendererFactory } from "../map/mapSession";
import { useGraphWalk } from "../map/useGraphWalk";

/**
 * One unfiltered question.
 *
 * `T-205` owns the three filters `GET /api/graph` actually accepts, and
 * `GraphFilters` is taken from the generated contract, so a control this view
 * does not have cannot be smuggled in as a query parameter the server ignores
 * (ADR 0005 invariant 7).
 */
const NO_FILTERS: GraphFilters = {};

/** The typed loader over the frozen operation, built once rather than per render. */
const loadGraphPage = apiGraphPages(api);

export function MapView({ createRenderer }: { createRenderer?: MapRendererFactory } = {}) {
  const { t } = useI18n();
  const walk = useGraphWalk(loadGraphPage, NO_FILTERS, []);

  const stage = useRef<HTMLDivElement | null>(null);
  const session = useRef<MapSession | null>(null);
  /** Which snapshot the live renderer was created for; `0` is none. */
  const attached = useRef(0);
  const [rendererError, setRendererError] = useState<string | null>(null);
  // Both the initialiser and every setter are wrapped: `useState` *calls* a
  // function it is handed, so storing a factory unwrapped would construct a
  // renderer during render, before the container exists.
  const [factory, setFactory] = useState<MapRendererFactory | null>(() => createRenderer ?? null);

  // Fetch the real renderer once, and only for this route. A browser that
  // refuses the module -- no WebGL2 -- is a stated failure rather than an
  // unhandled rejection, and the counts below stay true either way.
  useEffect(() => {
    if (createRenderer !== undefined) {
      setFactory(() => createRenderer);
      return;
    }
    let live = true;
    void import("../map/sigmaRenderer")
      .then(({ createSigmaRenderer }) => {
        if (live) setFactory(() => createSigmaRenderer);
      })
      .catch((cause: unknown) => {
        if (live) setRendererError(cause instanceof Error ? cause.message : String(cause));
      });
    return () => {
      live = false;
    };
  }, [createRenderer]);

  const { snapshot, snapshotId, status, loadingMore, error } = walk.state;
  const pages = snapshot?.pagesApplied ?? 0;
  const graph = walk.graph;

  // One session for the life of the route. The cleanup is the only thing
  // standing between a filter/reload loop and a pile of WebGL contexts, and
  // `StrictMode` exercises it on every mount in development.
  useEffect(() => {
    const container = stage.current;
    if (container === null || factory === null) return;
    const live = new MapSession({ container, createRenderer: factory });
    session.current = live;
    attached.current = 0;
    return () => {
      live.kill();
      session.current = null;
    };
  }, [factory]);

  // Draw. A new snapshot gets a new renderer; another page of the same
  // snapshot re-settles the layout of the graph already on screen.
  useEffect(() => {
    const live = session.current;
    if (live === null || graph === null || pages === 0) return;
    try {
      if (attached.current === snapshotId) {
        live.update();
      } else {
        live.attach(graph);
        attached.current = snapshotId;
      }
      setRendererError(null);
    } catch (cause) {
      // A renderer that cannot be created -- no WebGL2, or a container with no
      // size -- is a state to state, not an exception to take the route down
      // with. The counts above the canvas remain true and readable.
      live.kill();
      attached.current = 0;
      setRendererError(cause instanceof Error ? cause.message : String(cause));
    }
  }, [graph, snapshotId, pages, factory]);

  // The container is sized in CSS, so its pixel size changes with the viewport
  // and with the panels around it. A renderer holding the previous dimensions
  // draws the graph outside its own box, and the shrink direction is the one
  // that shows it.
  useEffect(() => {
    const container = stage.current;
    if (container === null) return;
    if (typeof ResizeObserver === "undefined") {
      const onResize = () => session.current?.resize();
      window.addEventListener("resize", onResize);
      return () => window.removeEventListener("resize", onResize);
    }
    const observer = new ResizeObserver(() => session.current?.resize());
    observer.observe(container);
    return () => observer.disconnect();
  }, []);

  const zoomIn = useCallback(() => session.current?.zoomIn(), []);
  const zoomOut = useCallback(() => session.current?.zoomOut(), []);
  const resetView = useCallback(() => session.current?.resetView(), []);

  /** Whether there is a camera to drive: a live renderer over a loaded page. */
  const drawn = pages > 0 && factory !== null && rendererError === null;
  const conflict = error instanceof GraphConflictError ? error : null;

  return (
    <div className="stack map">
      <h1>{t("map.title")}</h1>
      <p className="muted">{t("map.subtitle")}</p>

      {error instanceof ApiFailure && <ErrorState error={error} onRetry={walk.reload} />}

      {conflict !== null && (
        <div className="notice notice--internal" role="alert" data-map-conflict={conflict.field}>
          <strong>{t("map.conflict.title")}</strong>
          <p>
            {t("map.conflict.detail", {
              kind: conflict.kind,
              id: conflict.id,
              field: conflict.field,
            })}
          </p>
        </div>
      )}

      {status === "loading" && <p className="muted">{t("common.loading")}</p>}

      {snapshot !== null && pages > 0 && (
        <section
          className="panel map__state"
          aria-label={t("map.state.title")}
          data-map-nodes={snapshot.nodes}
          data-map-edges={snapshot.edges}
          data-map-held={snapshot.pendingEdges}
          data-map-complete={String(snapshot.complete)}
          data-map-truncated={String(snapshot.lastPageTruncated)}
        >
          <h2 className="panel__title">{t("map.state.title")}</h2>
          <dl className="definitions">
            <dt>{t("map.state.nodes")}</dt>
            <dd>
              {snapshot.knownNodeTotal === null
                ? `${snapshot.nodes} · ${t("common.unknownTotal")}`
                : `${snapshot.nodes} / ${snapshot.knownNodeTotal}`}
            </dd>
            <dt>{t("map.state.edges")}</dt>
            <dd>{snapshot.edges}</dd>
            <dt>{t("map.state.held")}</dt>
            <dd>
              {snapshot.pendingEdges}
              {snapshot.pendingEdges > 0 && (
                <span className="faint"> — {t("map.state.heldNote")}</span>
              )}
            </dd>
            <dt>{t("map.state.pages")}</dt>
            <dd>{snapshot.pagesApplied}</dd>
            <dt>{t("map.state.extent")}</dt>
            <dd>
              {snapshot.complete ? t("map.state.complete") : t("map.state.partial")}
              {snapshot.lastPageTruncated && (
                <span className="faint"> — {t("map.state.truncated")}</span>
              )}
            </dd>
          </dl>
          {snapshot.nodes === 0 && <p className="muted">{t("map.empty")}</p>}
        </section>
      )}

      <div className="row" role="group" aria-label={t("map.controls")}>
        <button type="button" className="button" onClick={zoomIn} disabled={!drawn}>
          {t("map.zoomIn")}
        </button>
        <button type="button" className="button" onClick={zoomOut} disabled={!drawn}>
          {t("map.zoomOut")}
        </button>
        <button type="button" className="button" onClick={resetView} disabled={!drawn}>
          {t("map.resetView")}
        </button>
        {snapshot?.hasMore === true && (
          <button
            type="button"
            className="button"
            onClick={walk.loadMore}
            disabled={loadingMore}
            data-map-load-more
          >
            {t("map.loadMore")}
          </button>
        )}
        {loadingMore && (
          <button type="button" className="button" onClick={walk.cancel}>
            {t("map.stopLoading")}
          </button>
        )}
      </div>

      {rendererError !== null && (
        <div className="notice notice--unavailable" role="alert" data-map-renderer-failed>
          <strong>{t("map.renderer.failed")}</strong>
          <p>{t("map.renderer.failedNote")}</p>
          <p className="faint" dir="auto">
            {rendererError}
          </p>
        </div>
      )}

      {/*
        The WebGL surface. One label, and one label is not accessibility: it
        describes the existence of a graph rather than its selectable entities,
        which is why ADR 0005 (D-120) pairs it with a DOM surface and why the
        counts above are rendered as text. `T-208` owns the rest of that pairing.
      */}
      <div
        ref={stage}
        className="map__stage"
        role="img"
        aria-label={t("map.stage.label")}
        data-map-stage
      />
    </div>
  );
}
