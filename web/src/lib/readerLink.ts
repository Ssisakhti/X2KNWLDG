/**
 * The Reader's deep-link grammar (`D-069`): `#/sources/<id>?tab=…&t=…`
 *
 * One module, because a link that is *built* in one place and *read* in
 * another is two implementations of one rule, and the pair drifts. Everything
 * that writes a Reader URL calls `readerPath`; the Reader itself calls
 * `parseTab` and `parseSeconds` on what arrives.
 *
 * Query parameters rather than path segments: `HashRouter` (D-060) puts the
 * whole location after `#`, so pathname and search compose normally and
 * `useSearchParams` reads them untouched. Both parameters are optional and a
 * link carrying neither is still a valid Reader link, so no existing URL is
 * invalidated by this grammar arriving.
 *
 * Seconds rather than a caption id, because seconds are the one unit that
 * addresses everything the Reader can jump to -- a caption, a knowledge unit's
 * locator, and the media player's own seek, which takes seconds regardless.
 * `io.timestamp_url` already spells a moment in this project as seconds.
 *
 * The internal grammar is `t=30` and the external YouTube one is `&t=30s`;
 * they are deliberately *not* the same spelling. The two links sit beside each
 * other in every search hit, and an identical spelling would invite feeding
 * `youtubeTimestampUrl`'s output into the internal link.
 */

export const READER_TABS = [
  "overview",
  "transcript",
  "report",
  "units",
  "relations",
  "artifacts",
] as const;

export type ReaderTab = (typeof READER_TABS)[number];

export const DEFAULT_TAB: ReaderTab = "overview";

export function isReaderTab(value: string | null): value is ReaderTab {
  return value !== null && (READER_TABS as readonly string[]).includes(value);
}

/** The tab a URL asks for, or `null` when it names none this Reader has. */
export function parseTab(value: string | null): ReaderTab | null {
  return isReaderTab(value) ? value : null;
}

/**
 * The offset a URL asks for, or `null`.
 *
 * A malformed or negative `t` is **ignored**, never coerced. Reading `t=x` as
 * `0` would place the reader at the start of the medium while the URL claimed
 * to place them somewhere else -- an invented position, which is the same
 * error as rendering a missing confidence as zero. No seek happened, so none
 * is reported.
 */
export function parseSeconds(value: string | null): number | null {
  if (value === null || value.trim() === "") return null;
  const seconds = Number(value);
  if (!Number.isFinite(seconds) || seconds < 0) return null;
  return seconds;
}

/** A Reader URL. Omitted parameters are absent, never spelled as defaults. */
export function readerPath(
  sourceId: string,
  options: { tab?: ReaderTab; seconds?: number | null } = {},
): string {
  const query = new URLSearchParams();
  if (options.tab !== undefined && options.tab !== DEFAULT_TAB) query.set("tab", options.tab);
  const { seconds } = options;
  if (seconds !== undefined && seconds !== null && Number.isFinite(seconds) && seconds >= 0) {
    // An integer when it is one, so the common case reads `t=30`, not `t=30.0`.
    query.set("t", Number.isInteger(seconds) ? String(seconds) : String(seconds));
  }
  const search = query.toString();
  return `/sources/${encodeURIComponent(sourceId)}${search === "" ? "" : `?${search}`}`;
}

/**
 * The index of the caption that *contains* `seconds`, or `null`.
 *
 * Containment first, then the last caption that starts at or before the
 * offset: a transcript may have gaps (a non-speech cue keeps its timing but
 * carries no text, per `WORKFLOW.md`), and landing on the caption that was
 * playing is better than landing on nothing. A caption stating no start time
 * can never be the answer -- it has no position to match.
 */
export function captionIndexAt(
  captions: readonly { startSec: number | null; endSec: number | null }[],
  seconds: number | null,
): number | null {
  if (seconds === null) return null;
  let fallback: number | null = null;
  let fallbackEnd: number | null = null;
  let laterCaptionExists = false;
  for (let index = 0; index < captions.length; index += 1) {
    const caption = captions[index];
    if (caption === undefined || caption.startSec === null) continue;
    if (caption.startSec > seconds) {
      laterCaptionExists = true;
      break;
    }
    fallback = index;
    fallbackEnd = caption.endSec;
    if (caption.endSec !== null && seconds < caption.endSec) return index;
  }
  // D-093: the fallback exists for a *gap* -- an offset the transcript spans
  // but no caption claims. An offset past the **end** of the transcript is not
  // a gap, it is outside the medium, and returning the final caption for it
  // marked a position no data supports: on a 3-caption transcript ending at
  // 15s, `captionIndexAt(caps, 999999)` returned `2`, so `?t=999999` set
  // `aria-current="location"` on the last caption and scrolled to it while
  // `reader.transcript.noCaptionAt` never fired. `TranscriptPanel` documents
  // the opposite, and an invented position is the one thing this project does
  // not do.
  //
  // A later caption existing is what makes this a gap: without one, `fallback`
  // is the last positioned caption and its end is the end of the transcript. A
  // caption stating no end time bounds nothing, so it stays the honest answer.
  if (!laterCaptionExists && fallbackEnd !== null && seconds >= fallbackEnd) return null;
  return fallback;
}
