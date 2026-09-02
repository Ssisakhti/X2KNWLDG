/**
 * The one place the application constructs Sigma (`T-204`).
 *
 * Kept apart from `mapSession.ts` so the lifecycle can be tested in jsdom --
 * which has no WebGL -- against an injected fake, exactly as the `T-202` gate
 * kept `new Sigma` out of its session module. Importing this file is what
 * pulls the renderer into the bundle, and only the Map route does.
 *
 * Three settings are stated rather than inherited, because each one is a
 * decision this phase already recorded:
 *
 * - `allowInvalidContainer: false`. The Map sizes its container in CSS, so a
 *   zero-sized container is a defect to see rather than a graph quietly drawn
 *   into nothing. `MapView` renders the refusal instead of crashing the route.
 * - `renderLabels: false`. D-122: a knowledge unit's `label` is its whole
 *   `normalized_statement`, and the gate drew 86 of them into a pile that hid
 *   the graph. The truncation and density policy is `T-205`'s to write; until
 *   it exists the Map draws none. The graph carries no `label` attribute at all
 *   (D-124), so this states the policy rather than relying on the absence.
 * - `enableEdgeEvents: false`. Nothing in `T-204` responds to an edge, and
 *   edge picking costs a hit-test pass per frame. `T-207` turns it on when
 *   there is something for it to select.
 *
 * Node and edge appearance is Sigma's own default here -- uniform size and
 * colour from `DEFAULT_STYLES`, since the graph stores no display attribute.
 * The provenance/kind style matrix is `T-205`'s, in reducers (D-124), and a
 * placeholder palette written here would be the second style table §8.6
 * forbids.
 */

import Sigma from "sigma";

import type { MapGraph } from "./graphProjection";
import type { MapRenderer, MapRendererFactory } from "./mapSession";

export const createSigmaRenderer: MapRendererFactory = (
  graph: MapGraph,
  container: HTMLElement,
): MapRenderer =>
  new Sigma(graph, container, {
    settings: {
      allowInvalidContainer: false,
      renderLabels: false,
      enableEdgeEvents: false,
    },
  });
