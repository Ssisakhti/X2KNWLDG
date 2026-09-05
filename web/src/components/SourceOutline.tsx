/**
 * Every source this Map holds, as a list (`T-256`).
 *
 * `MapOutline` is this for the Knowledge Map and the argument is the same one,
 * so it is worth restating rather than cross-referencing: the drawing is **one
 * view** of a list that is also in the DOM. Everything a mark can do a row can
 * do — focus a source, read its title, see its medium — with no pointer, no
 * WebGL2 and no query typed.
 *
 * Two things this list does that the drawing cannot.
 *
 * **It is complete.** Every node the response returned is a row, including the
 * ones a bounded field did not draw and the ones whose label had no clear seat.
 * A field that could not place a label loses a title; this list never does.
 *
 * **It states the order it is in.** The rows are in the order the server
 * returned them, which is id order and is not importance. Saying so is the
 * difference between a list and a ranking, and this Map has no ranking to give
 * (D-247).
 */

import type { EntityRef } from "../api/contract";
import { useI18n } from "../i18n";
import type { BriefState } from "../map/sourceStyle";
import { Bidi, Mono } from "./primitives";
import { BriefStateBadge, MediumBadge } from "./SourceMarks";
import { Disclosure } from "./Disclosure";

export function SourceOutline({
  sources,
  focus,
  onFocus,
  briefStates,
  preferOpen,
}: {
  sources: readonly EntityRef[];
  focus: string | null;
  onFocus: (globalId: string) => void;
  /** What is known about each source's brief; unknown reads as `unavailable`. */
  briefStates: ReadonlyMap<string, BriefState>;
  preferOpen: boolean;
}) {
  const { t } = useI18n();
  return (
    <Disclosure
      id="source-outline"
      title={t("source.map.outline")}
      summary={String(sources.length)}
      preferOpen={preferOpen}
      marks={{ "data-source-outline": String(sources.length) }}
    >
      {sources.length === 0 ? (
        <p className="muted">{t("source.empty")}</p>
      ) : (
        <ul className="sourceoutline">
          {sources.map((source) => {
            const selected = focus === source.global_id;
            return (
              <li key={source.global_id} data-source-row={source.source_id ?? source.global_id}>
                <button
                  type="button"
                  className={`sourceoutline__row${selected ? " sourceoutline__row--on" : ""}`}
                  aria-pressed={selected}
                  onClick={() => onFocus(source.global_id)}
                >
                  <span className="sourceoutline__marks">
                    <MediumBadge sourceType={source.source_type} />
                    <BriefStateBadge
                      state={briefStates.get(source.global_id) ?? "unavailable"}
                    />
                  </span>
                  <Bidi className="sourceoutline__title">{source.label}</Bidi>
                  <Mono>{source.source_id ?? source.global_id}</Mono>
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </Disclosure>
  );
}
