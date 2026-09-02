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
  MapNodeEvent,
  MapPoint,
  MapRenderer,
  MapRendererFactory,
} from "../map/mapSession";
import type { MapGraph } from "../map/graphProjection";

/** Where an unlisted node is reported to be: inside any plausible stage. */
export const FAKE_DEFAULT_POINT: MapPoint = { x: 300, y: 250 };

export interface FakeRenderer extends MapRenderer {
  /** Every call the session made, in order. */
  events: string[];
  /** Fire a node event the session subscribed to. A no-op if it did not. */
  fireNode: (event: MapNodeEvent, globalId: string) => void;
  /** Fire the "a frame was drawn" event. */
  fireRender: () => void;
}

export interface FakeRendererHarness {
  factory: MapRendererFactory;
  /** Every call every renderer made, in order, across creations and kills. */
  events: string[];
  /** The renderer created most recently, or `null` before the first. */
  latest: () => FakeRenderer | null;
  /** Every renderer created, in order. */
  all: FakeRenderer[];
}

export function fakeRenderers(
  options: {
    /** Refuse to be created, as a browser with no WebGL2 does. */
    failOnCreate?: boolean;
    /** Where each node's mark is, in stage pixels, by `global_id`. */
    points?: Record<string, MapPoint>;
  } = {},
): FakeRendererHarness {
  const events: string[] = [];
  const all: FakeRenderer[] = [];
  const points = options.points ?? {};

  const factory: MapRendererFactory = (graph: MapGraph) => {
    if (options.failOnCreate === true) {
      events.push("refused");
      throw new Error("WebGL2 is not available in this browser.");
    }
    events.push("create");
    const camera: MapCamera = {
      zoomIn: () => events.push("zoomIn"),
      zoomOut: () => events.push("zoomOut"),
      reset: () => events.push("reset"),
    };
    const nodeHandlers = new Map<MapNodeEvent, (globalId: string) => void>();
    let onRenderHandler: (() => void) | null = null;

    const renderer: FakeRenderer = {
      events,
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
