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

import { HashRouter, Route, Routes } from "react-router-dom";

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

export function App() {
  return (
    <I18nProvider>
      <HashRouter>
        <Shell>
          <AppRoutes />
        </Shell>
      </HashRouter>
    </I18nProvider>
  );
}
