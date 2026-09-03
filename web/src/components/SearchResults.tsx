/**
 * Search hits, in the two shapes the contract actually returns.
 *
 * `/api/search` preserves what `query.search_knowledge` already returned,
 * discriminated by `type`, so `video_id` stays `video_id` and the canonical
 * unit id stays `id`. Nothing is renamed or reshaped on the way in here
 * either.
 *
 * The load-bearing difference between the two shapes: a `transcript_caption`
 * hit carries **no** `global_id`, because v1 emits no caption entities
 * (D-023). It is therefore never linked as an entity -- doing so would mint an
 * address that resolves to nothing. It navigates by source and timestamp
 * instead, using the `source_url` the server built with `io.timestamp_url`,
 * verbatim.
 *
 * A `knowledge_unit` hit whose canonical metadata states no `video_id` has
 * `global_id: null` and `source_id: null` by design; that is rendered as an
 * unaddressable hit rather than as a plausible link.
 */

import { Link } from "react-router-dom";

import { api } from "../api/client";
import type { SearchHit } from "../api/contract";
import { usePaged } from "../api/usePaged";
import { useI18n } from "../i18n";
import { formatConfidence, formatSeconds } from "../lib/format";
import { PagedList } from "./PagedList";
import { ProvenanceBadge } from "./Provenance";
import { readerPath, type ReaderTab } from "../lib/readerLink";
import { Bidi, ExternalLink, Missing, Mono } from "./primitives";

function hitKey(hit: SearchHit, index: number): string {
  const local = hit.type === "knowledge_unit" ? hit.id : hit.caption_id;
  return `${hit.type}|${hit.video_id ?? ""}|${local ?? ""}|${index}`;
}

/**
 * The link from a hit into the Reader (D-069).
 *
 * A hit knows where it was found, and until this carried `tab`/`t` that
 * knowledge was thrown away at the click: the Reader opened on Overview and
 * the offset survived only in the external link, which answers "jump to the
 * timestamp" by leaving the application. `readerLink` owns the grammar so this
 * cannot spell it differently from the Reader that reads it.
 */
function SourceLink({
  sourceId,
  tab,
  seconds = null,
}: {
  sourceId: string | null;
  tab: ReaderTab;
  seconds?: number | null;
}) {
  const { t } = useI18n();
  if (sourceId === null) return null;
  return <Link to={readerPath(sourceId, { tab, seconds })}>{t("search.openSource")}</Link>;
}

function Hit({ hit }: { hit: SearchHit }) {
  const { t } = useI18n();

  if (hit.type === "transcript_caption") {
    return (
      <article className="card stack" data-hit-type="transcript_caption">
        <div className="row">
          <span className="badge">{t("search.hit.transcript_caption")}</span>
          <span className="faint">
            {t("time.at", { time: formatSeconds(hit.start_sec) ?? "?" })}
          </span>
          <span className="shell__spacer" />
          <Mono>{hit.caption_id ?? ""}</Mono>
        </div>
        <Bidi as="p">{hit.content ?? <Missing />}</Bidi>
        <p className="faint">{t("search.captionNotAddressable")}</p>
        <div className="row">
          <SourceLink sourceId={hit.source_id} tab="transcript" seconds={hit.start_sec} />
          <ExternalLink href={hit.source_url}>
            {t("search.openExternal")}
          </ExternalLink>
        </div>
      </article>
    );
  }

  const start = formatSeconds(hit.start_sec);
  return (
    <article
      className={`card card--${hit.source_class === "derived" ? "derived" : "source"} stack`}
      data-hit-type="knowledge_unit"
    >
      <div className="row">
        <span className="badge">{t("search.hit.knowledge_unit")}</span>
        {(hit.source_class === "source" || hit.source_class === "derived") && (
          <ProvenanceBadge provenance={hit.source_class} />
        )}
        <span className="badge">{hit.kind ?? t("common.notStated")}</span>
        <span className="faint">
          {t("reader.units.confidence")}: {formatConfidence(hit.confidence) ?? <Missing />}
        </span>
        <span className="shell__spacer" />
        <Mono>{hit.global_id ?? hit.id ?? ""}</Mono>
      </div>
      <Bidi as="p">{hit.content ?? <Missing />}</Bidi>
      <div className="row">
        {start !== null && <span className="faint">{t("time.at", { time: start })}</span>}
        <SourceLink sourceId={hit.source_id} tab="units" />
        {hit.source_url !== undefined && (
          <ExternalLink href={hit.source_url}>
            {t("search.openExternal")}
          </ExternalLink>
        )}
      </div>
    </article>
  );
}

export function SearchResults({
  query,
  includeTranscript,
}: {
  query: string;
  includeTranscript: boolean;
}) {
  const { t } = useI18n();
  const state = usePaged<SearchHit>(
    async (cursor, signal) => {
      const response = await api.call("search", {
        query: {
          q: query,
          limit: 25,
          include_transcript: includeTranscript,
          ...(cursor === undefined ? {} : { cursor }),
        },
        signal,
      });
      return {
        items: response.data,
        next: response.page.next_cursor,
        total: response.page.total ?? null,
      };
    },
    [query, includeTranscript],
    { enabled: query !== "" },
  );

  if (query === "") return null;

  return (
    <section className="stack" aria-label={t("search.results", { query })} data-focus-anchor>
      <h2>{t("search.results", { query })}</h2>
      {/*
        `PagedList` owns the ladder (D-203). Two of this surface's three
        defects were in the copy it replaces: "More" was one of the two
        buttons `withFocusRescue` never reached, so pressing it on the last
        page reset focus to the top of the document; and a failed later page
        rendered the error panel *instead of* the hits already loaded.
      */}
      <PagedList state={state} label={t("search.results", { query })} empty={t("search.empty")}>
        {(hits) => hits.map((hit, index) => <Hit key={hitKey(hit, index)} hit={hit} />)}
      </PagedList>
    </section>
  );
}
