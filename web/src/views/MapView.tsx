/**
 * The Knowledge Map at `#/map` (`T-204`).
 *
 * `T-204` built the shell: the address, the renderer's life and death, the
 * container's size, the camera, and the honest statement of what the snapshot
 * holds. `T-205` and `T-206` are now joined onto it, and this file is the join
 * rather than a third implementation of either -- the style table lives in
 * `mapStyle`, the URL grammar in `mapLink`, and this view only tells each of
 * them what the other one did.
 *
 * **The one selection identity.** `useMapFocus` owns it, so a result card, a
 * cleared focus and a reloaded URL all resolve the same `global_id` through
 * the same function. The style table is told about it here, and the two never
 * disagree because neither holds its own copy: `mapStyle.setView` is written
 * from `focus.focus` and `peek.peek`, and `MapSession.refresh()` redraws
 * without relaxing the layout (`update()` would, and the picture would jump on
 * every pointer move).
 *
 * **A focus the graph has not loaded highlights nothing.** The URL may name an
 * entity that this filter's pages have not reached, and dimming every drawn
 * node around a selection that is not on screen would be a picture of a focus
 * that does not exist. The canvas stays unfocused and the rail says why.
 *
 * **The canvas is now a third caller, not a second identity** (`T-207`,
 * §8.6). `MapSession` reports a click, an enter and a leave; this view answers
 * them with the *same* `focus.focusEntity` the rail's buttons call and the
 * *same* `peek.open`/`peek.close` its rows call. Nothing about selection lives
 * in the renderer, which is why the canvas can be absent -- no WebGL, no
 * measured container -- and the whole journey still works from the DOM.
 *
 * **A selection also asks two questions of its own** (`T-207`): what the
 * entity is (`/api/entities/{id}`) and what it is connected to
 * (`/api/graph/neighborhood/{id}`, depth 1..3). Those answers are the
 * neighbourhood, and they never touch the drawn graph: `GraphSnapshot`
 * accumulates the pages these filters describe (D-118) and merging a
 * neighbourhood into it would draw nodes the filters exclude and make the
 * counts beside the canvas uncomparable. So the bounded overlay is anchored to
 * the marks the snapshot *does* hold, and every returned neighbour -- drawn or
 * not, carded or not -- is in the related list (D-132, R20).
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
 * anyone who never reaches the picture.
 *
 * **And the account is no longer only counts** (`T-208`). `MapOutline` lists
 * every entity the Map has drawn, as the same cards the search rail renders,
 * so the drawing is *one view* of a list that is also in the DOM -- reachable
 * with no pointer, no WebGL2 and no query typed. `mapState.ts` decides what
 * the Map may claim about the graph and about the picture, which are two
 * different questions: a graph can be whole and undrawable at once.
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

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { api } from "../api/client";
import { ApiFailure } from "../api/errors";
import { ErrorState } from "../components/ErrorState";
import { MapConstellation } from "../components/MapConstellation";
import { MapFilters } from "../components/MapFilters";
import { MapLegend } from "../components/MapLegend";
import { MapOutline } from "../components/MapOutline";
import { MapPeekCard } from "../components/MapPeekCard";
import { MapQuickRead } from "../components/MapQuickRead";
import { MapRelatedList } from "../components/MapRelatedList";
import { MapSearchRail } from "../components/MapSearchRail";
import { Bidi } from "../components/primitives";
import { useI18n } from "../i18n";
import {
  MAP_STAGE_SETTLE_MS,
  placeConstellation,
  type StageBox,
  type StagePlacement,
} from "../map/constellation";
import { GraphConflictError } from "../map/graphProjection";
import type { GraphFilters } from "../map/graphSnapshot";
import { apiGraphPages } from "../map/graphWalk";
import { describeCanvas, describeGraph, type RendererFault } from "../map/mapState";
import { mapStyle } from "../map/mapStyle";
import { MapSession, type MapRendererFactory } from "../map/mapSession";
import { useGraphWalk } from "../map/useGraphWalk";
import { useMapFocus } from "../map/useMapFocus";
import { useMapPeek } from "../map/useMapPeek";
import { useNeighbourhood } from "../map/useNeighbourhood";
import { recordLookup } from "../map/useMapSearch";

/** The typed loader over the frozen operation, built once rather than per render. */
const loadGraphPage = apiGraphPages(api);

export function MapView({ createRenderer }: { createRenderer?: MapRendererFactory } = {}) {
  const { t } = useI18n();

  // The URL is the question. `filters` is the three parameters `GET /api/graph`
  // accepts and nothing else -- `mapLink` refuses a value it cannot read rather
  // than coercing one, so a hand-edited URL cannot smuggle a filter the server
  // would ignore past `GraphFilters` (ADR 0005 invariant 7).
  const focus = useMapFocus();
  const { source, provenance, vocabulary } = focus.state;
  // The three primitives, not the object: `filters` is a fresh object on every
  // render, and `deps` is what decides whether this is a *different question*
  // (D-118). Passing the object would open a new snapshot on every render.
  const walk = useGraphWalk(loadGraphPage, focus.filters, [source, provenance, vocabulary]);

  const stage = useRef<HTMLDivElement | null>(null);
  const session = useRef<MapSession | null>(null);
  /** Which snapshot the live renderer was created for; `0` is none. */
  const attached = useRef(0);
  /**
   * The same fact, in state, because the *view* has to render it (`T-208`).
   *
   * A ref cannot say "there is a picture now": it changes without a render.
   * So the snapshot the renderer holds is state as well, and it is what
   * `describeCanvas` is told -- otherwise the canvas reads as drawing for the
   * one render between a page arriving and the effect that draws it.
   */
  const [holdingId, setHoldingId] = useState(0);
  /**
   * Why there is no drawing, when there is none (`T-208`).
   *
   * Two phases, because they are two different failures with two different
   * answers: the module never loaded (a browser with no WebGL2 -- nothing on
   * this canvas will ever work), or a renderer was reached and refused this
   * container (almost always its size, which the next layout fixes). One
   * message for both sent a reader with an unsized stage looking for a
   * different browser.
   */
  const [fault, setFault] = useState<RendererFault | null>(null);
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
        if (live) {
          setFault({
            phase: "module",
            detail: cause instanceof Error ? cause.message : String(cause),
          });
        }
      });
    return () => {
      live = false;
    };
  }, [createRenderer]);

  const { snapshot, snapshotId, loadingMore, error } = walk.state;
  const pages = snapshot?.pagesApplied ?? 0;
  const graph = walk.graph;

  // One Peek, above both surfaces, and it can only show a record the Map has
  // actually loaded: `recordLookup` reads the accumulated graph, so a Peek can
  // never attribute a statement to a node no request returned (D-131).
  const peek = useMapPeek(recordLookup(graph));

  // The selection's own two questions (`T-207`). Keyed on the focus and the
  // depth, so a re-render asks nothing and a new selection asks once.
  const hood = useNeighbourhood(focus.focus);

  /** The stage's measured box, in pixels. Zero until the container is laid out. */
  const [stageBox, setStageBox] = useState<StageBox>({ width: 0, height: 0 });
  /** Bumped when the camera settles, which is when cards are placed again. */
  const [placedAt, setPlacedAt] = useState(0);
  /** Whether the camera is mid-gesture, in which case no card is drawn. */
  const [moving, setMoving] = useState(false);
  const settle = useRef<ReturnType<typeof setTimeout> | null>(null);
  /** The same fact, readable without a render, so a frame can check it. */
  const isMoving = useRef(false);

  /**
   * The renderer drew a frame.
   *
   * Called once per frame while the camera moves, so it must not re-render per
   * frame: the state change is guarded by a ref, and the trailing timer is one
   * too. Two renders per gesture -- one to hide the cards, one to place them
   * again -- rather than sixty (`MAP_STAGE_SETTLE_MS`).
   */
  const onRendered = useCallback(() => {
    if (!isMoving.current) {
      isMoving.current = true;
      setMoving(true);
    }
    if (settle.current !== null) clearTimeout(settle.current);
    settle.current = setTimeout(() => {
      settle.current = null;
      isMoving.current = false;
      setMoving(false);
      setPlacedAt((value) => value + 1);
    }, MAP_STAGE_SETTLE_MS);
  }, []);

  useEffect(
    () => () => {
      if (settle.current !== null) clearTimeout(settle.current);
    },
    [],
  );

  // Only a selection the graph *holds* is drawn as one. `hasFocus` dims
  // everything unrelated, so a focus naming an entity these pages have not
  // reached would dim the whole picture around nothing. The rail states that
  // case in words instead.
  const drawnFocus =
    focus.focus !== null && graph !== null && graph.hasNode(focus.focus) ? focus.focus : null;
  const hoveredNode = peek.peek?.globalId ?? null;

  /**
   * What the canvas reports to, kept in a ref and refreshed on every render.
   *
   * The same device `useMapPeek` uses for its lookup, and for the same reason:
   * these close over the current URL and the current Peek, while the
   * renderer's subscription is made once when the renderer is created. A
   * session re-created to pick up a new closure would kill a live renderer --
   * and the accumulated picture with it -- on every render.
   *
   * Note what is *not* here: any decision. `select` is `focus.focusEntity`
   * itself, which is the function the search rail's buttons call, so the
   * canvas is a third caller of one selection identity rather than a second
   * identity (§8.6, invariant 8).
   */
  const canvas = useRef({
    select: focus.focusEntity as (globalId: string) => void,
    enter: peek.open,
    leave: peek.close,
    rendered: onRendered,
  });
  canvas.current = {
    select: focus.focusEntity,
    enter: peek.open,
    leave: peek.close,
    rendered: onRendered,
  };

  // Always this focus's own, never a previous selection's: `useNeighbourhood`
  // reports only an answer to the question currently being asked, so nothing
  // downstream has to re-check the centre.
  const neighbourhood = hood.neighbourhood;
  // Which marks are lit as neighbours of the focus: the edges actually drawn,
  // plus the bounded neighbourhood's own answer restricted to nodes the Map
  // holds (`T-207`). Both are the API's statements about relatedness, so the
  // union is not a guess -- and it only ever *grows* as the neighbourhood
  // arrives, so a selection does not flicker between two highlight sets. A
  // node that is not drawn cannot be styled at all, which is why the related
  // list, not this set, is the completeness path (D-132).
  const relatedIds = useMemo(() => {
    const ids = new Set<string>();
    if (graph === null || drawnFocus === null) return ids;
    for (const id of graph.neighbors(drawnFocus)) ids.add(id);
    if (neighbourhood !== null) {
      for (const entity of neighbourhood.related) {
        if (graph.hasNode(entity.globalId)) ids.add(entity.globalId);
      }
    }
    return ids;
    // The graph is mutated in place (D-118), so its identity is not the
    // dependency -- the snapshot and the page count are.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [graph, snapshotId, pages, drawnFocus, neighbourhood]);

  useEffect(() => {
    const changed = mapStyle.setView({
      selectedNode: drawnFocus,
      hoveredNode,
      neighbourNodes: relatedIds,
    });
    // `refresh`, never `update`: `update` re-settles the layout (D-128), which
    // would make the graph jump every time the pointer crossed a result row.
    if (changed) session.current?.refresh();
  }, [drawnFocus, hoveredNode, relatedIds]);

  // One session for the life of the route. The cleanup is the only thing
  // standing between a filter/reload loop and a pile of WebGL contexts, and
  // `StrictMode` exercises it on every mount in development.
  useEffect(() => {
    const container = stage.current;
    if (container === null || factory === null) return;
    const live = new MapSession({
      container,
      createRenderer: factory,
      // Stable trampolines over the ref above, so the handlers can change
      // every render without the session ever being rebuilt.
      handlers: {
        onSelectNode: (globalId) => canvas.current.select(globalId),
        onEnterNode: (globalId) => canvas.current.enter(globalId, "pointer"),
        onLeaveNode: (globalId) => canvas.current.leave(globalId),
        onRender: () => canvas.current.rendered(),
      },
    });
    session.current = live;
    attached.current = 0;
    setHoldingId(0);
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
      setFault(null);
      setHoldingId(snapshotId);
      // The renderer now holds this graph, so its marks have positions to
      // anchor cards to (`T-207`). This is the *first* placement: without it
      // the overlay would wait for a frame event, and the placement computed
      // during the render that preceded this effect asked a renderer that had
      // not been given the graph yet -- which reads as "no neighbour is
      // drawn", which would be a report about the wrong thing.
      setPlacedAt((value) => value + 1);
    } catch (cause) {
      // A renderer that cannot be created -- no WebGL2, or a container with no
      // size -- is a state to state, not an exception to take the route down
      // with. The counts above the canvas remain true and readable.
      live.kill();
      attached.current = 0;
      setHoldingId(0);
      setFault({
        phase: "create",
        detail: cause instanceof Error ? cause.message : String(cause),
      });
    }
  }, [graph, snapshotId, pages, factory]);

  // The container is sized in CSS, so its pixel size changes with the viewport
  // and with the panels around it. A renderer holding the previous dimensions
  // draws the graph outside its own box, and the shrink direction is the one
  // that shows it.
  useEffect(() => {
    const container = stage.current;
    if (container === null) return;
    // One callback, two consumers: the renderer needs the new size, and the
    // overlay needs the box to decide which anchors are inside the stage. A
    // second observer would be a second answer to one question.
    const measure = () => {
      session.current?.resize();
      const box = container.getBoundingClientRect();
      setStageBox((current) =>
        current.width === box.width && current.height === box.height
          ? current
          : { width: box.width, height: box.height },
      );
    };
    measure();
    if (typeof ResizeObserver === "undefined") {
      window.addEventListener("resize", measure);
      return () => window.removeEventListener("resize", measure);
    }
    const observer = new ResizeObserver(measure);
    observer.observe(container);
    return () => observer.disconnect();
  }, []);

  // `MapFilters` speaks the API's parameter names and `mapLink` stores the same
  // three values, so this is a rename and not a translation. A control returning
  // to "any" clears the parameter rather than spelling an empty one.
  const { setFilters } = focus;
  const onFiltersChange = useCallback(
    (next: GraphFilters) => {
      setFilters({
        source: next.source_id ?? null,
        provenance: next.provenance_class ?? null,
        vocabulary: next.relation_vocabulary ?? null,
      });
    },
    [setFilters],
  );

  const zoomIn = useCallback(() => session.current?.zoomIn(), []);
  const zoomOut = useCallback(() => session.current?.zoomOut(), []);
  const resetView = useCallback(() => session.current?.resetView(), []);

  /**
   * The two honest states, each decided in one place (`T-208`, `mapState.ts`).
   *
   * `reading` is what the accumulated graph *is* -- and above all which pairs
   * it must not collapse: empty is not absent, partial is not whole, refused
   * is not empty. `canvas` is whether there is a picture of it, which is a
   * different question with a different answer: a graph can be whole and
   * undrawable at once, and every list on this route works either way.
   */
  const reading = describeGraph(walk.state);
  const picture = describeCanvas({
    fault,
    holding: holdingId !== 0 && holdingId === snapshotId,
    nodes: snapshot?.nodes ?? 0,
  });
  /** Whether there is a camera to drive: a live renderer over a loaded page. */
  const drawn = picture.interactive;
  /** Whether the stage really holds a picture, which is what a card anchors to. */
  const drawing = picture.kind === "drawing";
  const conflict = error instanceof GraphConflictError ? error : null;

  /**
   * Which cards the stage may carry, and why the rest have none (`T-207`).
   *
   * `null` -- not "an empty placement" -- whenever there is no stage to place
   * anything on: nothing selected, or no live renderer over a measured
   * container. The distinction matters because the omission report is a
   * statement *about the stage*, and reporting every neighbour as "not drawn"
   * when the whole canvas is missing would explain the wrong thing. The
   * renderer's own refusal is already stated above, and the related list is
   * complete either way.
   *
   * Recomputed when the selection, the neighbourhood, the graph or the stage's
   * size changes -- and when the camera settles (`placedAt`), which is what
   * makes a card follow its mark.
   */
  const placement = useMemo<StagePlacement | null>(() => {
    if (!drawing || focus.focus === null) return null;
    return placeConstellation({
      centreId: drawnFocus,
      related: neighbourhood?.related ?? [],
      position: (globalId) => session.current?.nodePosition(globalId) ?? null,
      stage: stageBox,
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [drawing, focus.focus, drawnFocus, neighbourhood, stageBox, placedAt, snapshotId, pages]);

  return (
    // Escape dismisses the Peek anywhere on the Map (`T-208`). One handler for
    // the route rather than one per panel: a Peek can be opened from the
    // rail, the outline, a related row or a mark on the canvas, and the
    // keyboard has no "leave" event to end any of them. (`MapSearchRail`
    // keeps its own, so the panel is still self-contained when it is rendered
    // alone -- calling `peek.close()` twice closes nothing twice.)
    <div
      className="stack map"
      // The two readings, as one attribute each: the whole route's state in a
      // place a test can read without going looking for the sentence that
      // renders it, and `T-209`'s seam for the same states in a browser.
      data-map-reading={reading.kind}
      data-map-canvas={picture.kind}
      onKeyDown={(event) => {
        if (event.key === "Escape") peek.close();
      }}
    >
      <h1>{t("map.title")}</h1>
      <p className="muted">{t("map.subtitle")}</p>

      <MapFilters value={focus.filters} onChange={onFiltersChange} />

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

      {/*
        The Map's own state, in words, before the picture (D-129).

        `reading.counted` is the whole distinction `T-208` added here: a
        snapshot with no page applied has nothing to count, and printing zeros
        for it would say "your library holds no graph" on the strength of a
        request that has not been answered. So the counts appear when there are
        counts, and the states that precede them say what they are instead.
      */}
      {reading.kind === "loading" && !reading.counted && (
        <p className="muted">{t("map.reading.loading")}</p>
      )}
      {reading.kind === "unasked" && <p className="muted">{t("map.reading.unasked")}</p>}

      {reading.counted && snapshot !== null && (
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
          {reading.kind === "empty" && <p className="muted">{t("map.empty")}</p>}
          {(reading.kind === "refused" || reading.kind === "conflict") && (
            // The pages that arrived before the failure are still drawn, and
            // they are still true -- but they are not an answer to the
            // question that failed, and a count sitting under an error panel
            // reads as one.
            <p className="faint" data-map-reading-stale>
              {t("map.reading.stale")}
            </p>
          )}
          {reading.kind === "loading" && <p className="muted">{t("map.reading.loading")}</p>}
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

      <MapSearchRail
        graph={graph}
        revision={snapshotId + pages}
        focus={focus.focus}
        onFocus={focus.focusEntity}
        peek={peek}
        sourceScope={source}
      />

      {/*
        A browser that cannot draw at all, and a renderer that refused this
        container, are two states with two answers (`T-208`). The first is
        permanent for this browser and the second usually resolves on the next
        layout, so they are not one message -- and neither of them costs the
        reader anything but the picture: the counts above and every list below
        are unchanged, and the outline is opened for them.
      */}
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

      {/*
        The WebGL surface, and the overlay anchored to it.

        One label, and one label is not accessibility: it describes the
        existence of a graph rather than its selectable entities, which is why
        ADR 0005 (D-120) pairs it with a DOM surface and why the counts above
        are rendered as text. `MapOutline` below is the rest of that pairing
        (`T-208`), and the label is written only while there is a picture to
        label.

        The overlay is a *sibling* of the stage rather than a child of it, and
        that is not layout taste: `MapSession.kill()` empties the container,
        because Sigma appends its own canvases to it and a killed renderer's
        leftovers would otherwise sit under the next one's. A React subtree
        inside that container would be removed from under React the first time
        a filter changed.

        While the camera is moving nothing is drawn here at all -- the same
        rule `hideLabelsOnMove` applies to labels, for the same reason.
      */}
      <div className="map__canvas">
        {/*
          `role="img"` only while there *is* a picture (`T-208`). An empty box
          announced as an image of the knowledge graph is a claim about content
          that is not there, and the states below say what is there instead.
        */}
        <div
          ref={stage}
          className="map__stage"
          role={drawing ? "img" : undefined}
          aria-label={drawing ? t("map.stage.label") : undefined}
          aria-hidden={drawing ? undefined : true}
          data-map-stage
        />
        {!moving && <MapConstellation placement={placement} centre={hood.centre} />}
      </div>

      {/*
        The one Peek, rendered in the one place (invariant 13).

        It is here rather than in the search rail because `T-208` made the
        panels foldable, and a Peek rendered inside a collapsed `<details>` is
        a card nobody can see -- while the pointer that opened it was on the
        canvas, which has no other way to say what a mark states. Below the
        stage rather than above it, because a transient card that resizes the
        container makes the renderer re-measure on every hover.
      */}
      {peek.peek !== null && <MapPeekCard peek={peek.peek} onClose={() => peek.close()} />}

      {picture.kind === "pending" && <p className="muted">{t("map.canvas.pending")}</p>}
      {picture.kind === "nothing" && <p className="muted">{t("map.canvas.nothing")}</p>}
      {/*
        The pointer path is an enhancement over the DOM path, and this sentence
        is where the Map says so: the marks are one view of a list that is
        right below, and everything a mark can do a row can do.
      */}
      <p className="faint" data-map-stage-companion>
        {t("map.stage.companion")}
      </p>

      <MapOutline
        graph={graph}
        revision={snapshotId + pages}
        focus={focus.focus}
        onFocus={focus.focusEntity}
        peek={peek}
        // The companion opens itself whenever it is the only view of the
        // graph: no renderer, a refused container, or nothing drawn yet.
        preferOpen={!drawing}
      />

      <MapQuickRead
        focus={focus.focus}
        entity={hood.centre}
        error={hood.centreError}
        onRetry={hood.reload}
        relations={neighbourhood?.active ?? []}
        loading={hood.status === "loading"}
      />

      <MapRelatedList
        focus={focus.focus}
        neighbourhood={neighbourhood}
        status={hood.status}
        error={hood.neighbourhoodError}
        onRetry={hood.reload}
        depth={hood.depth}
        onDepthChange={hood.setDepth}
        graph={graph}
        onFocus={focus.focusEntity}
        peek={peek}
        placement={placement}
      />

      <MapLegend />
    </div>
  );
}
