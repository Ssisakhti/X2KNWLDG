/**
 * The timed transcript, virtualized, with jump-to-timestamp.
 *
 * The bytes come from the byte channel -- `/api/media/{artifact_id}` serves
 * `transcript.json` verbatim, which is what makes reading it here honest
 * rather than a second interpretation of canonical data. The three refusals
 * are kept apart: no transcript artifact at all, a `404 unavailable` for one
 * that is recorded but absent, and a document that parses without a caption
 * list. Each says which it is.
 *
 * A caption that states no `start_sec` gets no seek control and says so.
 * Substituting a zero would put the reader at the beginning of the medium
 * while claiming to put them at the caption -- an invented timestamp, which is
 * the one thing this project does not do.
 *
 * `highlightSec` is the offset a deep link asked for (D-069). The caption
 * containing it is scrolled to and marked, because landing on the right tab at
 * the top of a thousand-caption list is not arriving at a timestamp. An offset
 * past the end of the transcript, or one no caption can claim, highlights
 * nothing and scrolls nowhere -- the transcript is shown as it is rather than
 * the reader being moved somewhere arbitrary.
 */

import { readCaptions, type Caption } from "../api/canonical";
import { api } from "../api/client";
import type { Artifact } from "../api/contract";
import { useAsync } from "../api/useAsync";
import { useI18n } from "../i18n";
import { formatSeconds, youtubeTimestampUrl } from "../lib/format";
import { captionIndexAt } from "../lib/readerLink";
import { ErrorState } from "./ErrorState";
import { VirtualList } from "./VirtualList";
import { Bidi, Missing } from "./primitives";

function CaptionRow({
  caption,
  sourceUrl,
  onSeek,
  linked = false,
}: {
  caption: Caption;
  sourceUrl: string | null;
  onSeek: (seconds: number) => void;
  linked?: boolean;
}) {
  const { t } = useI18n();
  const start = formatSeconds(caption.startSec);
  const deepLink = youtubeTimestampUrl(sourceUrl, caption.startSec);
  return (
    <div
      className={`caption-row${linked ? " caption-row--linked" : ""}`}
      role="listitem"
      // `aria-current` rather than colour alone: the marked caption has to be
      // announced, not merely tinted (ADR 0001 invariant 10 in the same
      // spirit -- one signal is never enough).
      aria-current={linked ? "location" : undefined}
      data-linked={linked ? "true" : undefined}
    >
      <div className="caption-row__time">
        {caption.startSec === null ? (
          <span className="missing" title={t("reader.transcript.noTime")}>
            —
          </span>
        ) : (
          <button
            type="button"
            className="button"
            onClick={() => onSeek(caption.startSec as number)}
            title={t("reader.transcript.seek")}
          >
            {start}
          </button>
        )}
      </div>
      <Bidi as="div" className="caption-row__text">
        {caption.text ?? <Missing />}
      </Bidi>
      {deepLink !== null && (
        <a href={deepLink} target="_blank" rel="noopener noreferrer" aria-label={t("search.openExternal")}>
          ↗
        </a>
      )}
    </div>
  );
}

export function TranscriptPanel({
  artifact,
  sourceUrl,
  onSeek,
  highlightSec = null,
}: {
  artifact: Artifact | null;
  sourceUrl: string | null;
  onSeek: (seconds: number) => void;
  highlightSec?: number | null;
}) {
  const { t } = useI18n();
  const state = useAsync(
    (signal) => api.media(artifact?.id ?? "", signal),
    [artifact?.id ?? ""],
    { enabled: artifact !== null },
  );

  if (artifact === null) return <p className="muted">{t("reader.transcript.unavailable")}</p>;
  if (state.error !== null) return <ErrorState error={state.error} onRetry={state.reload} />;
  if (state.status !== "ready" || state.data === null)
    return <p className="muted">{t("common.loading")}</p>;

  const captions = readCaptions(state.data);
  if (captions === null) return <p className="muted">{t("reader.transcript.malformed")}</p>;

  const linkedIndex = captionIndexAt(captions, highlightSec);

  return (
    <div className="stack">
      <p className="faint">{t("reader.transcript.count", { count: captions.length })}</p>
      {highlightSec !== null && linkedIndex === null && (
        <p className="faint">{t("reader.transcript.noCaptionAt")}</p>
      )}
      <VirtualList<Caption>
        items={captions}
        estimateHeight={44}
        label={t("reader.transcript.title")}
        itemKey={(caption, index) => caption.id ?? `caption-${index}`}
        scrollToIndex={linkedIndex}
        renderItem={(caption, index) => (
          <CaptionRow
            caption={caption}
            sourceUrl={sourceUrl}
            onSeek={onSeek}
            linked={index === linkedIndex}
          />
        )}
      />
    </div>
  );
}
