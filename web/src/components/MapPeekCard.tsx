/**
 * The one transient Peek card (`T-206`, D-133, ADR 0005 invariants 13 and 14).
 *
 * Hover or keyboard focus over a **loaded** node, and this says what the node
 * states -- kind, provenance, recorded confidence, the beginning of the stored
 * statement, and the recorded time. That is the information scent that turns a
 * circle into a choice; without it the user must select a node to learn
 * whether selecting it was worth doing, which is the pogo-sticking D-130 names.
 *
 * Three properties are the whole design, and each is somewhere else in the
 * code rather than here:
 *
 * - **It is transient.** Nothing on this card navigates. `useMapPeek` holds no
 *   URL and calls no `navigate`, so a pointer crossing the graph writes no
 *   history at all.
 * - **There is at most one.** `useMapPeek` keeps a single value, so a second
 *   Peek cannot exist; this component renders whatever that value is. Render
 *   it in exactly one place -- two components reading one binding would draw
 *   the same Peek twice.
 * - **It is not a selection.** Nothing here focuses, and the card says so out
 *   loud, because a card that appears under the pointer and a card that
 *   appears after a click otherwise look like the same event.
 *
 * The text is the record's own, cut by the same `previewText` policy the
 * result cards use, and cut shorter: a Peek is a glance, and the full
 * statement belongs to Quick Read (`T-207`). Everything absent stays visibly
 * absent.
 */

import { useI18n } from "../i18n";
import { formatConfidence, formatSeconds } from "../lib/format";
import type { MapPeekState } from "../map/useMapPeek";
import { previewOfEntity } from "../map/useMapSearch";
import { ProvenanceBadge } from "./Provenance";
import { PreviewStatement } from "./MapResultCard";
import { Missing, Mono } from "./primitives";

/** A glance is shorter than a list entry. Same policy, tighter bound. */
export const PEEK_LIMIT = 160;

export function MapPeekCard({
  peek,
  onClose,
}: {
  peek: MapPeekState;
  /** Optional dismissal, for the keyboard path where there is no "leave". */
  onClose?: () => void;
}) {
  const { t } = useI18n();
  const preview = previewOfEntity(peek.record);
  const start = formatSeconds(preview.startSec);
  const confidence = formatConfidence(preview.confidence);

  return (
    <aside
      className={`card${preview.provenance === null ? "" : ` card--${preview.provenance}`} stack map__peek`}
      // `status`, not `dialog`: it takes no focus and traps none. A Peek that
      // moved focus would fight the very keyboard walk that opened it.
      role="status"
      aria-live="polite"
      aria-label={t("map.peek.title")}
      data-map-peek={peek.globalId}
      data-peek-origin={peek.origin}
    >
      <div className="row">
        <span className="badge">{t("map.peek.title")}</span>
        {preview.provenance !== null && <ProvenanceBadge provenance={preview.provenance} />}
        <span className="badge">{preview.kind ?? t("common.notStated")}</span>
        <span className="faint">
          {t("reader.units.confidence")}: {confidence ?? <Missing />}
        </span>
        <span className="shell__spacer" />
        <Mono>{peek.globalId}</Mono>
      </div>

      <PreviewStatement text={preview.text} limit={PEEK_LIMIT} />

      <div className="row">
        {start !== null && <span className="faint">{t("time.at", { time: start })}</span>}
        <span className="faint">{t("map.peek.note")}</span>
        {onClose !== undefined && (
          <button type="button" className="button" onClick={onClose}>
            {t("map.peek.close")}
          </button>
        )}
      </div>
    </aside>
  );
}
