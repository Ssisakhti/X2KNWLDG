/**
 * Focus, and the history it writes (`T-206`, D-133).
 *
 * The Map's selection lives in the URL and nowhere else. That is not a
 * preference about where to keep state: it is what makes ADR 0005 invariant 14
 * testable. "Browser Back restores a prior focus **without leaving Map**" is
 * only true if a focus change is a navigation *within* `#/map` -- same route,
 * different query -- so the route element is never unmounted and the graph
 * behind it is never rebuilt. A selection kept in component state would either
 * write no history at all, or need a second mechanism to mirror itself into
 * the URL, and the two would disagree the first time someone pressed Back.
 *
 * This hook is a binding, in the sense `useGraphWalk` is: every rule about what
 * a Map URL may say lives in `mapLink`, and nothing here parses or spells a
 * parameter itself. It decides only *when* a navigation happens.
 *
 * **One entry point for both input paths.** `focusEntity` is what the search
 * rail's button calls and what a Sigma `clickNode` handler must call, so
 * pointer and keyboard cannot resolve to two different identities (ADR 0005
 * invariant 8, D-120). The argument is an existing `global_id`; there is no
 * overload taking a label, an index or a node object, because each of those
 * would be an identity this application invented.
 *
 * **What does not write history.** Peek does not -- it is not here at all, it
 * is `useMapPeek`, and the separation is structural rather than remembered.
 * Re-selecting what is already selected does not either: it would push an
 * entry identical to the current one, and Back would then appear to do
 * nothing, which is worse than an unexplained no-op.
 */

import { useCallback, useMemo } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import type { GraphFilters } from "./graphSnapshot";
import {
  type MapState,
  graphFiltersOf,
  mapPath,
  parseMapState,
  sameMapState,
} from "../lib/mapLink";

/** The filter half of the state: everything except the selection. */
export type MapFilterState = Omit<MapState, "focus">;

export interface MapFocusBinding {
  /** The whole addressable state, as the URL states it. Malformed values are absent. */
  state: MapState;
  /** The focused `global_id`, or `null`. */
  focus: string | null;
  /** The same state as the three query parameters `GET /api/graph` accepts. */
  filters: GraphFilters;
  /**
   * Focus an entity by its existing `global_id`, or clear the focus with
   * `null`. Pushes history, so Back restores the previous focus.
   */
  focusEntity: (globalId: string | null, options?: { replace?: boolean }) => void;
  /** Clear the selection, keeping the filters. Pushes, so Back re-selects. */
  clearFocus: () => void;
  /**
   * Change one or more filters, keeping the selection.
   *
   * Also a push: a filter change replaces the whole snapshot (invariant 5), so
   * it is exactly the kind of step a user needs Back to undo. A control that
   * wants otherwise -- a slider settling, say -- passes `replace`.
   */
  setFilters: (
    next: Partial<MapFilterState>,
    options?: { replace?: boolean },
  ) => void;
}

export function useMapFocus(): MapFocusBinding {
  const location = useLocation();
  const navigate = useNavigate();

  // Keyed on the query string alone: two renders at the same URL produce the
  // same object, so this can be a dependency of an effect without re-running it
  // on every render of the view above.
  const state = useMemo<MapState>(() => parseMapState(location.search), [location.search]);
  const filters = useMemo<GraphFilters>(() => graphFiltersOf(state), [state]);

  const go = useCallback(
    (next: MapState, replace: boolean) => {
      // Nothing changed, so nothing is pushed. A duplicate entry would make
      // Back look broken rather than making it do more.
      if (sameMapState(next, state)) return;
      navigate(mapPath(next), { replace });
    },
    [navigate, state],
  );

  const focusEntity = useCallback(
    (globalId: string | null, options: { replace?: boolean } = {}) => {
      go({ ...state, focus: globalId }, options.replace ?? false);
    },
    [go, state],
  );

  const clearFocus = useCallback(() => focusEntity(null), [focusEntity]);

  const setFilters = useCallback(
    (next: Partial<MapFilterState>, options: { replace?: boolean } = {}) => {
      go({ ...state, ...next }, options.replace ?? false);
    },
    [go, state],
  );

  return { state, focus: state.focus, filters, focusEntity, clearFocus, setFilters };
}
