/**
 * Routing (`T-109`).
 *
 * Hash routing on purpose: the app is served by the local backend that
 * `T-116` wires up, and a hash route needs no SPA fallback rule on that
 * server -- deep-linking a reader works whether the assets are served by Vite
 * in development or by the FastAPI app in production, with no server change on
 * either side.
 *
 * Three routes today: the Library, the Reader, and the Map (`T-204`). The
 * Canvas (`T-301`) joins here.
 *
 * `#/map` is a first-class address rather than a panel inside the Library, so
 * a Map link can be opened cold and reloaded -- which is what makes `T-206`'s
 * URL grammar for selection and filters a widening of this route rather than a
 * new one.
 */

import { useCallback, useState } from "react";
import { HashRouter, Route, Routes, useLocation } from "react-router-dom";

import { RouteErrorBoundary } from "./components/RouteErrorBoundary";
import { Shell } from "./components/Shell";
import { I18nProvider } from "./i18n";
import { LibraryView } from "./views/LibraryView";
import { MapView } from "./views/MapView";
import { ReaderView } from "./views/ReaderView";
import { NotFoundView } from "./views/NotFoundView";

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<LibraryView />} />
      <Route path="/sources/:sourceId" element={<ReaderView />} />
      <Route path="/map" element={<MapView />} />
      <Route path="*" element={<NotFoundView />} />
    </Routes>
  );
}

/**
 * The routes under their boundary, reset by a retry *or* by a navigation.
 *
 * D-179 put the boundary inside `Shell` so a route that throws leaves the
 * navigation, the language switch and the skip link reachable -- "a reader who
 * hits one is one click from somewhere that works". The click did not work:
 * the boundary cleared its error only when `resetKey` changed and nothing
 * bumped it on navigation, so opening a bad source id and then clicking
 * Library changed the URL, moved `aria-current`, and went on rendering the
 * fallback. Every route was broken until a reload.
 *
 * So the boundary's key carries the location as well as the retry counter.
 * Clearing the error remounts the children -- React has already unmounted them
 * -- which is what makes the navigation a fresh view rather than the failed one
 * resumed.
 *
 * `AppRoutes` is keyed on the *attempt* alone, deliberately. Keying it on the
 * location too would remount the route on every query change, and on the Map
 * that would throw away the accumulated graph every time a reader selected a
 * node (D-128, D-178).
 */
function RoutedViews({ attempt, onRetry }: { attempt: number; onRetry: () => void }) {
  const location = useLocation();
  return (
    <RouteErrorBoundary
      resetKey={`${attempt}:${location.pathname}${location.search}`}
      onRetry={onRetry}
    >
      <AppRoutes key={attempt} />
    </RouteErrorBoundary>
  );
}

export function App() {
  const [attempt, setAttempt] = useState(0);
  const retry = useCallback(() => setAttempt((value) => value + 1), []);
  return (
    <I18nProvider>
      <HashRouter>
        <Shell>
          <RoutedViews attempt={attempt} onRetry={retry} />
        </Shell>
      </HashRouter>
    </I18nProvider>
  );
}
