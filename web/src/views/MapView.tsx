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

import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";

import { api } from "../api/client";
import { ApiFailure } from "../api/errors";
import { ErrorState } from "../components/ErrorState";
import { MapOrbit } from "../components/MapOrbit";
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
  type OrbitPlacement,
  orbitTier,
  placeOrbit,
  type StageBox,
  type StageRect,
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
import { withFocusRescue } from "../lib/focusRescue";

/** The typed loader over the frozen operation, built once rather than per render. */
const loadGraphPage = apiGraphPages(api);

/** One empty set, so "no cards" is the same object on every render. */
const EMPTY_CARDED: ReadonlySet<string> = new Set<string>();

/**
 * Whether two measured chrome lists describe the same rectangles (`T-212`).
 *
 * `getBoundingClientRect` returns a fresh object every call, so the measured
 * list is a new array on every measurement and storing it unconditionally
 * would re-place every card on every render. This is the guard that makes the
 * layout effect idempotent.
 */
function sameRects(a: readonly StageRect[], b: readonly StageRect[]): boolean {
  if (a.length !== b.length) return false;
  return a.every((rect, index) => {
    const other = b[index];
    return (
      other !== undefined &&
      rect.left === other.left &&
      rect.top === other.top &&
      rect.right === other.right &&
      rect.bottom === other.bottom
    );
  });
}

export function MapView({ createRenderer }: { createRenderer?: MapRendererFactory } = {}) {
  const { t, dir } = useI18n();

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
  /** The route's own element: the field every floating surface is placed on. */
  const root = useRef<HTMLDivElement | null>(null);
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
  /**
   * Where the floating chrome is, in the stage's own pixels (`T-212`).
   *
   * The workspace put the controls on the field instead of above it, so
   * "which cards may the stage carry" now has a second half: not under the
   * search surface, the counts, the legend, the drawer or the camera's
   * controls. They are *measured* rather than stated as insets because the
   * whole composition mirrors under `dir="rtl"` and a hand-written inset per
   * edge is the exact defect D-191 carries forward from the mockup.
   */
  const [chrome, setChrome] = useState<readonly StageRect[]>([]);
  //: Bumped to ask the draw effect to try again after a refusal (D-176).
  const [retryAt, setRetryAt] = useState(0);
  //: The stage size the last refusal was measured at, so one unusable
  //: container is refused once rather than retried on every render.
  const refusedBox = useRef("");
  /*
   * What `T-213` deleted here, and why it is a deletion rather than a move.
   *
   * A per-frame `onRender` subscription used to drive a trailing timer, so the
   * cards were hidden while the camera moved and placed again once it stopped
   * (`MAP_STAGE_SETTLE_MS`). Every line of it existed because a card was
   * pinned to a mark, and the Directional Orbit is not: it is laid out from
   * the field, the neighbourhood and the chrome's rectangles, none of which a
   * pan or a zoom changes. So the orbit stays still and legible through a
   * gesture that used to erase it, and the route subscribes to no frame at
   * all. `MapSession.onRender` remains on the renderer boundary, where D-146
   * put it, with no caller in the route.
   */

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
  });
  canvas.current = {
    select: focus.focusEntity,
    enter: peek.open,
    leave: peek.close,
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

  /*
   * Bring a new focus onto the stage (`T-209`, D-146).
   *
   * The walk found selection and the camera never speaking: the camera framed
   * the whole graph, so a focus sat wherever the layout had put it -- and
   * `Zoom in` zooms about the middle of the stage, so a reader who selected a
   * node and zoomed pushed it off screen altogether. Every neighbour card was
   * refused for covering the focused one, because a neighbourhood at
   * whole-graph scale is about a tenth of the stage wide.
   *
   * Keyed on the *drawn* focus and on the graph the renderer holds, so this
   * fires once per selection: a re-render moves nothing, and a focus named by
   * the URL before the first page arrives is framed when the picture appears.
   * The neighbours come from the drawn graph rather than from the bounded
   * neighbourhood, which arrives later and would move the camera a second
   * time under a reader who had started reading.
   */
  useEffect(() => {
    if (drawnFocus === null || graph === null) return;
    session.current?.frame(drawnFocus, graph.neighbors(drawnFocus));
    // D-178: `pages` was in here too, so every `Load more` re-framed the
    // camera and threw away the reader's pan and zoom -- select a node, zoom
    // in to read it, press `Load more`, and the camera animates back. The
    // comment above says this fires once per selection, and with `pages` it
    // fired once per selection *per page*. `holdingId` is what says "the
    // renderer is holding a picture to frame", which is the condition this
    // effect actually needs; a merged page changes the picture but not the
    // question, and D-128 in this file is precisely about not moving the
    // picture under the reader.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [drawnFocus, holdingId]);


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
    if (live === null) return;
    if (graph === null || pages === 0) {
      // D-177: this used to be a bare `return`, so on a filter change --
      // `open()` bumps `snapshotId` and resets `pages` to 0 -- the live
      // renderer kept snapshot N-1 on screen while the counts panel unmounted
      // and the stage took `aria-hidden="true"`. The result was a visible,
      // interactive-looking picture of question A, hidden from assistive
      // technology, beside a route describing question B. Retiring the picture
      // is what makes the empty stage and the honest state agree.
      if (attached.current !== 0) {
        live.kill();
        attached.current = 0;
        setHoldingId(0);
      }
      return;
    }
    try {
      if (attached.current === snapshotId) {
        live.update();
      } else {
        live.attach(graph);
        attached.current = snapshotId;
      }
      setFault(null);
      // `T-207` bumped a placement counter here, because the overlay's cards
      // were anchored to marks and the renderer had only just been given the
      // graph that gives them positions. `T-213` does not: the orbit is laid
      // out from the field and the neighbourhood, so `setHoldingId` alone --
      // which is what turns the picture into a `drawing` -- is the whole of
      // the first placement.
      setHoldingId(snapshotId);
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
  }, [graph, snapshotId, pages, factory, retryAt]);

  // D-176: a renderer that refused its container never tried again.
  //
  // `mapState.ts` and the shipped string in `i18n/catalog.ts` both promise
  // that "the next layout recovers it", and there was no path by which it
  // could: the draw effect does not depend on `stageBox`, and the resize
  // effect only calls `session.resize()`, which is `this.renderer?.resize()`
  // and therefore a no-op once the refusal has killed the renderer. So
  // `data-map-canvas="refused"` was permanent until the reader changed a
  // filter -- on the commonest cause of a refusal, a stage that has not been
  // laid out yet.
  //
  // Keyed on the box that was tried rather than on `fault`, which is a new
  // object on every failure: a retry happens once per *size*, so a container
  // that is genuinely unusable is refused once and not in a loop.
  useEffect(() => {
    if (fault === null) return;
    if (stageBox.width === 0 || stageBox.height === 0) return;
    const box = `${stageBox.width}x${stageBox.height}`;
    if (refusedBox.current === box) return;
    refusedBox.current = box;
    setRetryAt((value) => value + 1);
  }, [fault, stageBox]);

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

  /**
   * Measure the floating chrome against the stage (`T-212`).
   *
   * One rectangle per surface marked `data-map-chrome`, in the coordinates
   * `MapSession.nodePosition` answers in -- the renderer's own container --
   * because that is the space a card's anchor is in and a rectangle in any
   * other space is a policy about nothing.
   *
   * A zero-sized surface is skipped rather than reserved as a point: in jsdom
   * every rectangle is zero, and a run of empty rectangles at the origin would
   * refuse every card at the top-start corner of a stage that has no measured
   * size either.
   */
  const measureChrome = useCallback(() => {
    const container = stage.current;
    const host = root.current;
    if (container === null || host === null) return;
    const base = container.getBoundingClientRect();
    const measured: StageRect[] = [];
    for (const element of host.querySelectorAll<HTMLElement>("[data-map-chrome]")) {
      const box = element.getBoundingClientRect();
      if (box.width === 0 || box.height === 0) continue;
      measured.push({
        left: box.left - base.left,
        top: box.top - base.top,
        right: box.right - base.left,
        bottom: box.bottom - base.top,
      });
    }
    setChrome((current) => (sameRects(current, measured) ? current : measured));
  }, []);

  /*
   * Two triggers, because a surface moves for two different reasons.
   *
   * A layout effect after every render catches the ones a render causes: the
   * drawer opening takes its width out of the field, which moves the counts
   * and the camera's controls without either of them changing size. The
   * observer catches the ones no render causes: a panel expanded by its own
   * `<details>`, a font arriving, the window resized.
   *
   * The setter compares before it stores, so neither trigger can loop.
   */
  useLayoutEffect(measureChrome);

  useEffect(() => {
    const host = root.current;
    if (host === null || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(measureChrome);
    observer.observe(host);
    for (const element of host.querySelectorAll<HTMLElement>("[data-map-chrome]")) {
      observer.observe(element);
    }
    return () => observer.disconnect();
  }, [measureChrome]);

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

  /*
   * Escape dismisses the Peek from anywhere on the route (`T-208`, corrected
   * by `T-209`).
   *
   * One reader of the key for the whole route rather than one per panel: a
   * Peek can be opened from the rail, the outline, a related row or a mark on
   * the canvas, and the keyboard has no "leave" event to end any of them.
   * (`MapSearchRail` keeps its own, so the panel is still self-contained when
   * it is rendered alone -- calling `peek.close()` twice closes nothing
   * twice.)
   *
   * On `window`, not on the route's own element, and that is `T-209`'s
   * correction: a React `onKeyDown` on this `<div>` only ever sees a key
   * pressed while focus is *inside* it, and a canvas takes no focus. So a
   * pointer on a mark opened a Peek that Escape could not close -- the one
   * surface with no other way to dismiss it -- while the same key worked
   * everywhere a control had been tabbed to. Measured in Chrome on the real
   * route; jsdom could not have shown it, because a test fires the event at
   * the element it chooses.
   *
   * Listening only while a Peek is open, so this route adds no global key
   * handler to a page that has nothing to dismiss.
   */
  const closePeek = peek.close;
  const peeking = peek.peek !== null;
  useEffect(() => {
    if (!peeking) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") closePeek();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [peeking, closePeek]);

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
   * The Directional Orbit over this selection (`T-213`, ADR 0006 clause 3).
   *
   * `null` -- not "an empty placement" -- whenever there is no field to lay
   * anything out on: nothing selected, or no live renderer over a measured
   * container. The distinction matters because the omission report is a
   * statement *about the composition*, and reporting every neighbour as "not
   * placed" when the whole canvas is missing would explain the wrong thing.
   * The renderer's own refusal is already stated above, and the related list
   * is complete either way.
   *
   * Four inputs and no camera. It is recomputed when the selection, the
   * neighbourhood, the field's size or the chrome's rectangles change --
   * because those are the only four things the layout reads. A pan is not one
   * of them, which is why the orbit no longer flickers through a gesture, and
   * `snapshotId`/`pages` are no longer inputs either: a neighbour whose page
   * the walk has not reached still has a direction and a hop count, so it
   * still has a card.
   *
   * `dir` is here because incoming-first is a *reading* order (D-012): in
   * Persian the incoming side is the right, where reading starts. The records
   * are untouched; only which side draws them changes.
   */
  const placement = useMemo<OrbitPlacement | null>(() => {
    if (!drawing || focus.focus === null) return null;
    return placeOrbit({
      centreId: drawnFocus,
      related: neighbourhood?.related ?? [],
      field: stageBox,
      obstacles: chrome,
      rtl: dir === "rtl",
    });
  }, [drawing, focus.focus, drawnFocus, neighbourhood, stageBox, chrome, dir]);

  /**
   * Which of SPEC §5's three compositions this field can hold.
   *
   * Read from the same measured box the orbit is laid out in, so the CSS that
   * dresses the field and the TypeScript that fills it can never disagree
   * about which composition is on screen. Below the `compact` minimum there is
   * no orbit at all: the route keeps its document composition, where the
   * focused record and *every* one of its relations is a row and none is
   * dropped (SPEC §5's `stack` tier).
   */
  const tier = orbitTier(stageBox.width);

  /*
   * The style table is told *after* the orbit has decided, and that ordering
   * is the whole of it: which nodes carry cards is an output of `placeOrbit`,
   * so the effect that hands the view state to the renderer has to sit below
   * the memo that computes it. It used to sit beside the selection effects
   * two hundred lines up, where `placement` does not exist yet.
   */
  /**
   * Which nodes the orbit has drawn a card for (`T-214`).
   *
   * Handed to the style table so their canvas labels go: a card carries the
   * statement in more of it than a label can and with the cut marked, and the
   * label underneath it is the same sentence twice in one place (ADR 0006
   * clause 5). A neighbour the orbit *counted* is deliberately not in here --
   * its label is the only thing naming it.
   */
  const cardedIds = useMemo(() => {
    if (placement === null) return EMPTY_CARDED;
    const carded = new Set<string>(placement.cards.map((card) => card.globalId));
    if (placement.centre !== null) carded.add(placement.centre.globalId);
    return carded;
  }, [placement]);

  useEffect(() => {
    const changed = mapStyle.setView({
      selectedNode: drawnFocus,
      hoveredNode,
      neighbourNodes: relatedIds,
      cardedNodes: cardedIds,
    });
    // `refresh`, never `update`: `update` re-settles the layout (D-128), which
    // would make the graph jump every time the pointer crossed a result row.
    if (changed) session.current?.refresh();
  }, [drawnFocus, hoveredNode, relatedIds, cardedIds]);

  return (
    <div
      ref={root}
      /*
       * The field (`T-212`, D-153).
       *
       * `stack map` until now: a flex column of panels, which is what made the
       * stage a 640 px band 790 px down a 5795 px document. It is a workspace
       * now -- one positioned field with the graph in it and every control
       * floating on top -- and `map--focused` is the one fact five surfaces
       * have to agree about: a focus opens the drawer, and the drawer's width
       * comes out of the field before anything is placed in it.
       */
      className={`map${focus.focus === null ? "" : " map--focused"}`}
      // The two readings, as one attribute each: the whole route's state in a
      // place a test can read without going looking for the sentence that
      // renders it, and `T-209`'s seam for the same states in a browser.
      data-map-reading={reading.kind}
      data-map-canvas={picture.kind}
      // Which of SPEC §5's three compositions the measured field can hold. On
      // the element rather than only in a memo, so the stylesheet dresses the
      // same tier the layout used and a test can read it without inferring it
      // from a card count.
      data-map-tier={tier}
    >
      {/*
        The route's name, for the document outline and for a screen reader's
        heading list. Visually hidden because the app bar already carries it
        and a workspace has no room for a title and a subtitle: the pixels a
        heading would take are the pixels the graph exists in. Hidden, not
        removed -- `visually-hidden` keeps it in the accessibility tree, which
        is where its readers are.
      */}
      <h1 className="visually-hidden">{t("map.title")}</h1>
      <p className="visually-hidden">{t("map.subtitle")}</p>

      {/*
        Filters and counts: the field's top end (SPEC §2, §7 row 2).

        The counts still precede the stage in the DOM, which is D-129 and is
        the reason this surface is second rather than wherever it looks
        best: it is the text that survives when the WebGL view cannot be read
        at all, and a Map whose only honest description came after the picture
        would read as complete to anyone who never reaches the picture.
      */}
      <div className="map__float map__float--status stack" data-map-chrome>
        <MapFilters value={focus.filters} onChange={onFiltersChange} />

        {/*
          `reading.counted` is the whole distinction `T-208` added here: a
          snapshot with no page applied has nothing to count, and printing
          zeros for it would say "your library holds no graph" on the strength
          of a request that has not been answered. So the counts appear when
          there are counts, and the states centred on the field say what they
          are instead.
        */}
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

            {/*
              Continuing the walk is about the graph's *extent*, so it belongs
              with the counts that state that extent rather than with the
              camera's controls, which are about the picture. `T-212` split the
              one control row the document composition had along that line.
            */}
            {(snapshot.hasMore === true || loadingMore) && (
              <div className="row">
                {snapshot.hasMore === true && (
                  <button
                    type="button"
                    className="button"
                    onClick={withFocusRescue(walk.loadMore)}
                    disabled={loadingMore}
                    data-map-load-more
                  >
                    {t("map.loadMore")}
                  </button>
                )}
                {loadingMore && (
                  <button type="button" className="button" onClick={withFocusRescue(walk.cancel)}>
                    {t("map.stopLoading")}
                  </button>
                )}
              </div>
            )}
          </section>
        )}
      </div>

      {/*
        Search, and the list the drawing is a view of: the field's top start
        (SPEC §2, §7 rows 3 and 5).

        SPEC §7 numbers the outline after the stage while placing it visually
        "in the search drawer's panel list". Those two cannot both be true of
        one DOM, and the visual column is the binding one -- the table's own
        subject is that tab order must follow visual order, and a panel
        rendered inside this surface is the only way the keyboard reaches it
        where a reader sees it. So the outline is this drawer's second panel
        and precedes the stage, which is also what D-129 asks for.
      */}
      <div className="map__float map__float--search stack" data-map-chrome>
        <MapSearchRail
          graph={graph}
          revision={snapshotId + pages}
          focus={focus.focus}
          onFocus={focus.focusEntity}
          peek={peek}
          sourceScope={source}
        />

        {/*
          The pointer path is an enhancement over the DOM path, and this
          sentence is where the Map says so: the marks are one view of a list
          that is right here, and everything a mark can do a row can do. It
          names the panel by its title rather than by its position, which is
          why moving the panel did not make the sentence wrong.
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
      </div>

      {/*
        The honest states, centred on the field (`T-211`'s states sheet).

        Before the stage in the DOM and over it on screen. `mapState.ts`
        decides what each of these says; this decides only where, and the
        answer is "in the workspace" rather than "on a line that pushes the
        stage down the document". A browser that cannot draw at all and a
        renderer that refused this container stay two states with two answers
        (`T-208`): the first is permanent for this browser and the second
        usually resolves on the next layout. Neither costs the reader anything
        but the picture -- the counts and every list are unchanged, and the
        outline is opened for them.
      */}
      <div className="map__notices">
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

        {reading.kind === "loading" && !reading.counted && (
          <p className="notice muted">{t("map.reading.loading")}</p>
        )}
        {reading.kind === "unasked" && <p className="notice muted">{t("map.reading.unasked")}</p>}

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

        {picture.kind === "pending" && <p className="notice muted">{t("map.canvas.pending")}</p>}
        {picture.kind === "nothing" && <p className="notice muted">{t("map.canvas.nothing")}</p>}
      </div>

      {/*
        The WebGL surface, and the overlay anchored to it.

        One label, and one label is not accessibility: it describes the
        existence of a graph rather than its selectable entities, which is why
        ADR 0005 (D-120) pairs it with a DOM surface and why the counts above
        are rendered as text. `MapOutline` is the rest of that pairing
        (`T-208`), and the label is written only while there is a picture to
        label.

        The overlay is a *sibling* of the stage rather than a child of it, and
        that is not layout taste: `MapSession.kill()` empties the container,
        because Sigma appends its own canvases to it and a killed renderer's
        leftovers would otherwise sit under the next one's. A React subtree
        inside that container would be removed from under React the first time
        a filter changed.

        The pair is the field less the drawer (`T-212`): both are absolutely
        placed in one box, and that box is what is measured and handed to
        `placeConstellation`, so opening the drawer is a resize the renderer is
        told about rather than a surface laid over a picture that did not move.

        While the camera is moving nothing is drawn here at all -- the same
        rule `hideLabelsOnMove` applies to labels, for the same reason.
      */}
      <div className="map__canvas">
        {/*
          `role="img"` only while there *is* a picture (`T-208`). An empty box
          announced as an image of the knowledge graph is a claim about content
          that is not there, and the notices centred on the field say what is
          there instead.
        */}
        <div
          ref={stage}
          className="map__stage"
          role={drawing ? "img" : undefined}
          aria-label={drawing ? t("map.stage.label") : undefined}
          aria-hidden={drawing ? undefined : true}
          data-map-stage
        />
        <MapOrbit placement={placement} centre={hood.centre} />
      </div>

      {/*
        The field's inline-end rail: the one primary drawer, and the camera's
        controls under it (SPEC §2, §7 rows 6 and 7).

        ADR 0006 clause 4 allows one primary drawer to open on demand over the
        workspace, and rejected a large inspector standing permanently beside
        the graph. So with nothing focused this is its own trigger -- two
        collapsed panels, each still stating what it holds -- and it takes only
        the height that needs; a focus opens it to the rail's full height and
        takes its width out of the field.

        Quick Read holds the focus and its active relations; the related list
        follows *inside the same drawer*, which is SPEC §7's reading order:
        focus, then its relations, then the wider list. Both panels stay
        mounted with nothing selected, because a panel that disappears cannot
        say that nothing is selected.

        The camera's controls are the rail's last child rather than a float in
        the same corner. In the approved Focus capture the drawer is full
        height at the inline end and the zoom float is at the bottom end
        underneath it, so the drawer paints over the camera controls: a reader
        who opens Quick Read cannot zoom the graph they are reading about, which
        is the *Focus Not Obscured* failure SPEC §8 cites, one surface over.
        Sharing the rail costs the drawer about 60 px and costs the reader
        nothing.
      */}
      <div className="map__endrail">
        <div className="map__drawer" data-map-chrome>
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
        </div>

        <div className="map__zoom row" role="group" aria-label={t("map.controls")} data-map-chrome>
          <button type="button" className="button" onClick={zoomIn} disabled={!drawn}>
            {t("map.zoomIn")}
          </button>
          <button type="button" className="button" onClick={zoomOut} disabled={!drawn}>
            {t("map.zoomOut")}
          </button>
          <button type="button" className="button" onClick={resetView} disabled={!drawn}>
            {t("map.resetView")}
          </button>
        </div>
      </div>

      {/* The quietest surface on the field: the bottom start (SPEC §2, §7 row 8). */}
      <div className="map__float map__float--legend" data-map-chrome>
        <MapLegend />
      </div>

      {/*
        The one Peek, rendered in the one place (invariant 13).

        It is not inside any panel, because `T-208` made the panels foldable
        and a Peek rendered inside a collapsed `<details>` is a card nobody can
        see -- while the pointer that opened it was on the canvas, which has no
        other way to say what a mark states. It is the route's, and it floats
        at the field's block end rather than in the flow, because a transient
        card that resizes anything makes the renderer re-measure on every
        hover. It is deliberately not measured as chrome: it is the reader's
        own momentary card, it closes on leaving the mark or on Escape, and
        re-placing every neighbour card underneath it would make the
        constellation flicker as the pointer crossed the stage.
      */}
      {peek.peek !== null && <MapPeekCard peek={peek.peek} onClose={() => peek.close()} />}
    </div>
  );
}
