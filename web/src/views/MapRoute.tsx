/**
 * The `/map` route, which is two Maps (`T-256`).
 *
 * A dispatch and nothing else. It exists as its own file rather than as a
 * branch inside `MapView` for the reason D-249 has held through four tasks: the
 * Knowledge Map's view is not edited to make room for the Source Map, so
 * nothing about the existing route can move by accident. `MapView` is imported
 * here exactly as `App` used to import it, and its file is untouched.
 *
 * The mode is read from the URL rather than held in state, so a Source Map is a
 * link that can be sent, opened cold and reloaded — the same property
 * `#/map?focus=` has, and the reason the mode is in the grammar at all.
 *
 * Both views are imported eagerly. A `lazy` boundary here would buy a smaller
 * initial chunk for a route that already loads Sigma on demand, and would cost a
 * suspense state on a switch a reader makes with a button — the renderer is the
 * heavy part and it is already deferred.
 */

import { useLocation } from "react-router-dom";

import { modeOf, parseMapState } from "../lib/mapLink";
import { MapView } from "./MapView";
import { SourceMapView } from "./SourceMapView";

export function MapRoute() {
  const location = useLocation();
  return modeOf(parseMapState(location.search)) === "sources" ? <SourceMapView /> : <MapView />;
}
