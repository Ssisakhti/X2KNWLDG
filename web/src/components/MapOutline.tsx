/**
 * The Map's semantic companion: everything the canvas draws, as a list
 * (`T-208`, D-120, D-129).
 *
 * The counts above the canvas say *how much* the Map holds. This says *what*
 * it holds, and it is the surface that makes the whole route work without a
 * pointer, without WebGL2 and without a query having been typed. Every row
 * carries the same three affordances a mark on the canvas carries -- a
 * preview on focus, a Focus button that selects it, and a link into the
 * Reader -- because they are literally the same card the search rail and the
 * related list render (§8.6: one card-content formatter, one selection
 * identity).
 *
 * It opens itself when there is no picture to read. A browser that refuses
 * the renderer, a stage with no measured height and a graph with no page yet
 * are all states where this list is the only view of the graph, so the view
 * hands it `preferOpen` and the reader is not asked to go looking for the
 * content that is left.
 *
 * What it must not become: a second graph store, a second order, or a second
 * count. The rows come from `outlineOfGraph`, the order is the API's own, and
 * the bound states what it did not list rather than dropping it quietly.
 */

import { useMemo, useState } from "react";

import { useI18n } from "../i18n";
import { withFocusRescue } from "../lib/focusRescue";
import type { MapGraph } from "../map/graphProjection";
import { MAP_OUTLINE_PAGE, outlineOfGraph } from "../map/outline";
import type { MapPeekBinding } from "../map/useMapPeek";
import { Disclosure } from "./Disclosure";
import { MapResultCard } from "./MapResultCard";

export function MapOutline({
  graph,
  revision,
  focus,
  onFocus,
  peek,
  preferOpen,
}: {
  /** The accumulated snapshot. `null` before the first page arrives. */
  graph: MapGraph | null;
  /** `snapshotId + pagesApplied`: the graph is mutated in place, so it needs one. */
  revision: number;
  focus: string | null;
  onFocus: (globalId: string | null) => void;
  /** The one Peek binding, shared with the canvas and the rail. */
  peek: MapPeekBinding;
  preferOpen: boolean;
}) {
  const { t } = useI18n();
  const [limit, setLimit] = useState(MAP_OUTLINE_PAGE);
  // The graph is mutated in place (D-118), so its identity is not the
  // dependency -- the revision is, exactly as in `useMapSearch`.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const outline = useMemo(() => outlineOfGraph(graph, limit), [graph, revision, limit]);

  return (
    <Disclosure
      id="outline"
      className="map__outline"
      title={t("map.outline.title")}
      summary={t("map.outline.summary", { listed: outline.listed, loaded: outline.loaded })}
      preferOpen={preferOpen}
      marks={{
        "data-map-outline": String(outline.listed),
        "data-map-outline-loaded": String(outline.loaded),
        "data-map-outline-unlisted": String(outline.unlisted),
        // The anchor `withFocusRescue` lands on when "More" unmounts itself.
        // It has to be a surface that *survives* that: the row holding the
        // button goes with it, and an anchor that is gone is one `rescue`
        // skips (`focusRescue.ts` checks `isConnected`).
        "data-focus-anchor": "",
      }}
    >
      <p className="faint">{t("map.outline.hint")}</p>

      {outline.loaded === 0 ? (
        <p className="muted">{t("map.outline.none")}</p>
      ) : (
        <>
          {outline.rows.map((row) => (
            <MapResultCard
              key={row.globalId}
              preview={row.preview}
              focused={row.globalId === focus}
              onFocus={onFocus}
              peek={peek.handlers(row.globalId)}
            >
              <p className="faint" data-map-outline-edges={row.edgesDrawn}>
                {t("map.outline.edges", { count: row.edgesDrawn })}
              </p>
            </MapResultCard>
          ))}
          {outline.unlisted > 0 && (
            // The click is wrapped: D-180 documents the seven controls that
            // were fixed and this was the same defect unwrapped. Press "More"
            // on the last page, the button unmounts because nothing is
            // unlisted any more, and focus resets to the top of the document.
            // The anchor is the panel above, not this row — this row unmounts
            // with the button.
            <div className="stack">
              <p className="faint">{t("map.outline.unlisted", { count: outline.unlisted })}</p>
              <button
                type="button"
                className="button"
                data-map-outline-more
                onClick={withFocusRescue(() => setLimit((value) => value + MAP_OUTLINE_PAGE))}
              >
                {t("map.outline.more")}
              </button>
            </div>
          )}
        </>
      )}
    </Disclosure>
  );
}
