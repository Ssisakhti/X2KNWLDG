/**
 * The injected renderer the Map's tests draw through (`T-204`, extended by
 * `T-207`).
 *
 * jsdom has no WebGL, so `MapRendererFactory` is the seam every Map test uses
 * and this is the one fake behind it. One fake rather than one per suite: the
 * boundary grew three members in `T-207` (`onNode`, `onRender`,
 * `graphToViewport`), and three copies of a fake are three chances for a suite
 * to assert against a renderer that behaves unlike the others.
 *
 * Two behaviours are worth reading before using it.
 *
 * **Events are kept, not just counted.** `onNode` records the handler the
 * session subscribed, so a test can fire `clickNode` and prove the *view*
 * responded -- that a click reaches `focusEntity` and writes the URL, rather
 * than that a handler was installed.
 *
 * **`graphToViewport` resolves a coordinate back to its node.** The real
 * adapter is handed a point, not an id, because that is Sigma's signature. A
 * test, though, wants to say *where a node is* -- "`KU-000002` is off the
 * stage" -- so the fake looks the coordinate up in the graph it was created
 * with and answers from a per-node table. Nodes carry distinct seeded
 * positions (`seedPositions.ts`), so the lookup is unambiguous; a coordinate
 * that belongs to no node, or a node with no entry, falls back to a fixed
 * point well inside a normal stage.
 */

import type {
  MapCamera,
  MapCameraAnimation,
  MapCameraTarget,
  MapNodeEvent,
  MapPoint,
  MapRenderer,
  MapRendererFactory,
} from "../map/mapSession";
import type { IndexedRelation } from "../api/contract";
import type { MapGraph } from "../map/graphProjection";

/** Where an unlisted node is reported to be: inside any plausible stage. */
export const FAKE_DEFAULT_POINT: MapPoint = { x: 300, y: 250 };

export interface FakeRenderer extends MapRenderer {
  /** Every call the session made, in order. */
  events: string[];
  /**
   * The animation argument each camera gesture was handed, in order
   * (`T-208`).
   *
   * `undefined` is the renderer keeping its own duration; `{ duration: 0 }`
   * is a reader who asked for reduced motion. Recorded separately from
   * `events` so the existing assertions on the gesture *sequence* keep
   * reading as they did.
   */
  animations: (MapCameraAnimation | undefined)[];
  /** Fire a node event the session subscribed to. A no-op if it did not. */
  fireNode: (event: MapNodeEvent, globalId: string) => void;
  /** Fire the "a frame was drawn" event. */
  fireRender: () => void;
  /** Every framing gesture the camera was asked for, in order (`T-209`). */
  framings: MapCameraTarget[];
}

export interface FakeRendererHarness<E = IndexedRelation> {
  factory: MapRendererFactory<E>;
  /** Every call every renderer made, in order, across creations and kills. */
  events: string[];
  /** The renderer created most recently, or `null` before the first. */
  latest: () => FakeRenderer | null;
  /** Every renderer created, in order. */
  all: FakeRenderer[];
}

export function fakeRenderers<E = IndexedRelation>(
  options: {
    /** Refuse to be created, as a browser with no WebGL2 does. */
    failOnCreate?: boolean;
    /** Where each node's mark is, in stage pixels, by `global_id`. */
    points?: Record<string, MapPoint>;
    /**
     * Where each node is in the renderer's *framed* space, by `global_id`
     * (`T-209`). Unlisted nodes have no display position, which is what a
     * renderer answers for a node it does not hold.
     */
    display?: Record<string, MapPoint>;
  } = {},
): FakeRendererHarness<E> {
  const events: string[] = [];
  const all: FakeRenderer[] = [];
  const points = options.points ?? {};
  const display = options.display ?? {};

  // Generic over the edge record for the reason the real factory is: `T-256`
  // gave the session a second caller whose edges are source relations, and this
  // fake reads no edge attribute at all.
  const factory: MapRendererFactory<E> = (graph: MapGraph<E>) => {
    if (options.failOnCreate === true) {
      events.push("refused");
      throw new Error("WebGL2 is not available in this browser.");
    }
    events.push("create");
    const animations: (MapCameraAnimation | undefined)[] = [];
    const framings: MapCameraTarget[] = [];
    const camera: MapCamera = {
      zoomIn: (animation?: MapCameraAnimation) => {
        animations.push(animation);
        events.push("zoomIn");
      },
      zoomOut: (animation?: MapCameraAnimation) => {
        animations.push(animation);
        events.push("zoomOut");
      },
      reset: (animation?: MapCameraAnimation) => {
        animations.push(animation);
        events.push("reset");
      },
      animate: (target: MapCameraTarget, animation?: MapCameraAnimation) => {
        animations.push(animation);
        framings.push(target);
        events.push("animate");
      },
    };
    const nodeHandlers = new Map<MapNodeEvent, (globalId: string) => void>();
    let onRenderHandler: (() => void) | null = null;

    const renderer: FakeRenderer = {
      events,
      animations,
      framings,
      resize: (force?: boolean) => events.push(`resize:${String(force)}`),
      refresh: () => events.push("refresh"),
      kill: () => events.push("kill"),
      getCamera: () => camera,
      onNode: (event, handler) => {
        events.push(`onNode:${event}`);
        nodeHandlers.set(event, handler);
      },
      onRender: (handler) => {
        events.push("onRender");
        onRenderHandler = handler;
      },
      graphToViewport: (point: MapPoint) => {
        let found: string | null = null;
        graph.forEachNode((key, attributes) => {
          if (found === null && attributes.x === point.x && attributes.y === point.y) found = key;
        });
        return (found === null ? undefined : points[found]) ?? FAKE_DEFAULT_POINT;
      },
      nodeDisplay: (globalId: string) => display[globalId] ?? null,
      fireNode: (event, globalId) => nodeHandlers.get(event)?.(globalId),
      fireRender: () => onRenderHandler?.(),
    };
    all.push(renderer);
    return renderer;
  };

  return {
    factory,
    events,
    latest: () => (all.length === 0 ? null : (all[all.length - 1] as FakeRenderer)),
    all,
  };
}
