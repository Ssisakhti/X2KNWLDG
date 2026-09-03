/**
 * One result, with enough of the record to choose before selecting (`T-206`).
 *
 * D-130's acceptance question is behavioural: *before* opening a node, can the
 * user say what it states and why it is worth opening? So a card carries the
 * statement itself, its kind, its provenance, its recorded confidence and the
 * real source/time cues -- and carries them **verbatim**. There is no summary
 * here and there is no derived title, because a client-written sentence about
 * canonical knowledge is a third claim nobody can trace (D-131, ADR 0005
 * invariant 12).
 *
 * **Truncation is presentation, and it says so.** A knowledge unit's `label`
 * is its whole `normalized_statement` and may run to thousands of characters
 * (D-122 is the same fact biting the renderer), so a list of them is
 * unreadable. `previewText` cuts on a word boundary and the card renders a
 * visible marker plus a stated note beside the cut. What it never does is cut
 * silently, cut in a data structure, or present the head of a statement as the
 * statement.
 *
 * **A missing value stays missing.** A confidence the record does not state
 * renders as `Missing`, never as `0.00`: a zero is a measurement, and this
 * project does not invent measurements. A kind that is absent renders as "not
 * stated" rather than as a guess from the entity type.
 *
 * **Unaddressable results are explained, not hidden and not linkable.** A
 * transcript caption is not an entity in v1 (D-023) and a knowledge unit whose
 * run states no `video_id` has `global_id: null` by the contract's own
 * decision. Both keep their content, their timestamp and their route into the
 * Reader; neither gets a Focus control, because the Map has no address to give
 * them (D-119). The absence of the button is the honest signal -- a disabled
 * one would suggest the address exists and is merely unavailable.
 */

import type { ReactNode } from "react";
import { Link } from "react-router-dom";

import { useI18n } from "../i18n";
import { formatConfidence, formatSeconds } from "../lib/format";
import type { MapPreview } from "../map/useMapSearch";
import type { PeekHandlers } from "../map/useMapPeek";
import { readerPath } from "../lib/readerLink";
import { cutToBudget, type CutText } from "../map/labelPolicy";
import { KindBadge, ProvenanceBadge } from "./Provenance";
import { Bidi, ExternalLink, Missing, Mono } from "./primitives";

/**
 * Characters of a statement shown in a list before it is visibly cut.
 *
 * A number chosen to fit a rail without hiding the sentence's subject, and
 * still not a measured threshold: `T-209` walked the real route and this
 * library gave it nothing to bite on -- the longest statement it holds is 121
 * characters, so the cut almost never fires here. A library with longer
 * statements is where this number will first be wrong. It is exported so
 * `T-207`'s on-stage cards can shorten to the *same* policy instead of writing
 * a second one (§8.6: one card-content formatter).
 */
export const PREVIEW_LIMIT = 240;

export type PreviewText = CutText;

/**
 * Shorten for display, on a word boundary, without rewriting anything.
 *
 * The cut is `cutToBudget`, shared with the WebGL label policy: §8.6 allows
 * one card-content formatter, and a second one here was also a *different*
 * one -- it cut with `String.prototype.slice`, which counts UTF-16 units and
 * will halve a surrogate pair on the boundary and draw a replacement
 * character. The knowledge this rail shows is Persian as often as English and
 * carries whatever the source said, so the code-point-safe cut is the one both
 * surfaces get.
 *
 * What stays here is how the cut is *admitted*: a WebGL label bakes in an
 * ellipsis because a canvas has nowhere else to put it, while this card says
 * so in words beside the text. The returned text is always a prefix of the
 * stored text; nothing is paraphrased and nothing is completed (D-131).
 */
export function previewText(text: string | null, limit: number = PREVIEW_LIMIT): PreviewText {
  return cutToBudget(text, limit);
}

/** The statement, cut visibly when it is cut at all. */
export function PreviewStatement({
  text,
  limit = PREVIEW_LIMIT,
}: {
  text: string | null;
  limit?: number;
}) {
  const { t } = useI18n();
  const { shown, truncated } = previewText(text, limit);
  if (shown === null) return <Missing />;
  return (
    <>
      <Bidi as="p">{shown}</Bidi>
      {truncated && (
        <p className="faint" data-truncated="true">
          … {t("map.search.result.truncated")}
        </p>
      )}
    </>
  );
}

export function MapResultCard({
  preview,
  focused = false,
  onFocus,
  peek,
  limit = PREVIEW_LIMIT,
  children,
}: {
  preview: MapPreview;
  focused?: boolean;
  /** Called with a real `global_id`. Never called for an unaddressable result. */
  onFocus: (globalId: string) => void;
  /** Pointer *and* keyboard peek handlers for this node, when it is loaded. */
  peek?: PeekHandlers;
  limit?: number;
  /**
   * What this result *is to the reader*, rendered under the statement
   * (`T-207`).
   *
   * The slot exists so the related list can name a neighbour's real relation
   * and direction on the same card the search rail uses, rather than growing a
   * second card that would drift from this one. It carries context about the
   * record, never content from it: everything above and below is still the
   * API's own text, cut by the one cutter (D-131).
   */
  children?: ReactNode;
}) {
  const { t } = useI18n();
  const isCaption = preview.unaddressable === "caption";
  const start = formatSeconds(preview.startSec);
  const confidence = formatConfidence(preview.confidence);
  const identity = preview.globalId ?? preview.localId ?? "";

  return (
    <article
      className={`card${preview.provenance === null ? "" : ` card--${preview.provenance}`} stack`}
      data-map-result={preview.origin}
      data-global-id={preview.globalId ?? undefined}
      data-addressable={String(preview.globalId !== null)}
      data-unaddressable={preview.unaddressable ?? undefined}
      {...peek}
    >
      <div className="row">
        <span className="badge">
          {isCaption ? t("search.hit.transcript_caption") : t("search.hit.knowledge_unit")}
        </span>
        {preview.provenance !== null && <ProvenanceBadge provenance={preview.provenance} />}
        {preview.provenance === null && preview.provenanceRaw !== null && (
          // A provenance value outside the three the contract defines is shown
          // as written rather than rounded to one of them.
          <span className="badge" data-provenance-unknown>
            {preview.provenanceRaw}
          </span>
        )}
        {!isCaption && <KindBadge kind={preview.kind} />}
        {!isCaption && (
          <span className="faint">
            {t("reader.units.confidence")}: {confidence ?? <Missing />}
          </span>
        )}
        <span className="shell__spacer" />
        <Mono>{identity}</Mono>
      </div>

      <PreviewStatement text={preview.text} limit={limit} />

      {children}

      <div className="row">
        {start !== null && <span className="faint">{t("time.at", { time: start })}</span>}
        {preview.sourceTitle !== null && (
          <Bidi className="faint">{preview.sourceTitle}</Bidi>
        )}
        {preview.origin === "index" && preview.globalId !== null && (
          <span className="faint" data-map-loaded={String(preview.loaded)}>
            {preview.loaded
              ? t("map.search.result.onMap")
              : t("map.search.result.notLoaded")}
          </span>
        )}
      </div>

      {preview.unaddressable !== null && (
        <p className="faint" data-unaddressable-reason={preview.unaddressable}>
          {isCaption
            ? t("search.captionNotAddressable")
            : t("map.search.result.noGlobalId")}
        </p>
      )}

      <div className="row">
        {preview.globalId !== null && (
          <button
            type="button"
            className="button"
            aria-pressed={focused}
            data-map-focus-action={preview.globalId}
            onClick={() => onFocus(preview.globalId as string)}
          >
            {focused
              ? t("map.search.result.focused")
              : t("map.search.result.focus")}
          </button>
        )}
        {preview.sourceId !== null && (
          <Link
            to={readerPath(preview.sourceId, {
              tab: preview.readerTab,
              seconds: preview.startSec,
            })}
          >
            {t("search.openSource")}
          </Link>
        )}
        {preview.sourceUrl !== null && (
          <ExternalLink href={preview.sourceUrl}>{t("search.openExternal")}</ExternalLink>
        )}
      </div>
    </article>
  );
}
