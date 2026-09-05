/**
 * The stage, as something a component re-renders on.
 *
 * `stage.ts` answers "which ground is this" for the reducers, which are called
 * again on every refresh and so need no subscription. The DOM legend is the
 * other half of ADR 0005 invariant 9 -- it exists to say which mark means what
 * -- and a legend whose swatches were painted at mount would, after a theme
 * change, describe the previous stage's inks while the canvas drew the new
 * ones. A legend that disagrees with the marks is worse than no legend.
 *
 * `useSyncExternalStore` rather than `useState` + `useEffect` so the value read
 * during render is the one the subscription is for, with no frame in between.
 * The server snapshot is `light`, which is what `mapStage()` answers for an
 * environment that cannot be asked.
 */

import { useCallback, useSyncExternalStore } from "react";

import { mapStage, onMapStageChange, type MapStage } from "./stage";

export function useMapStage(): MapStage {
  const subscribe = useCallback((onStoreChange: () => void) => {
    return onMapStageChange(() => onStoreChange());
  }, []);
  return useSyncExternalStore(subscribe, mapStage, () => "light" as MapStage);
}
