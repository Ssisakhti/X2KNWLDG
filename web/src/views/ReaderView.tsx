/**
 * The Reader (`T-112`): one source, read end to end.
 *
 * Six panels over the frozen surface -- metadata and status, the virtualized
 * transcript, the canonical report, the knowledge units with their evidence,
 * the relations, and the artifact inventory. Everything is fetched through
 * `getSource`, `listSourceEntities`, `listSourceRelations` and the byte
 * channel; nothing is recomputed and no canonical file is opened by any other
 * route.
 *
 * Status lives in the sidebar rather than in a banner because canvas plan §7
 * asks for it to be always available and never in the way of reading -- and
 * it is the copied triple, so a run whose coverage passes under a failing
 * validation shows both.
 *
 * The seek signal is a `{seconds, nonce}` pair rather than a bare number so
 * that clicking the same timestamp twice seeks twice.
 *
 * Which tab is open and where the reader is pointed both live in the URL
 * (D-069, grammar in `lib/readerLink`), so a search hit can hand its offset
 * over and a reader can be shared or reloaded where it was left. They stay
 * *only* in the URL rather than being mirrored into state, because two homes
 * for one fact is how the address bar and the page come to disagree.
 */

import { useRef, useState } from "react";
import type { KeyboardEvent } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";

import { artifactOfKind } from "../api/canonical";
import { api } from "../api/client";
import type {
  Artifact,
  EntityRef,
  IndexedRelation,
  KnowledgeKind,
  ProvenanceClass,
  Source,
} from "../api/contract";
import { useAsync } from "../api/useAsync";
import { usePaged } from "../api/usePaged";
import { KNOWLEDGE_KINDS, PROVENANCE_CLASSES, RELATION_VOCABULARIES } from "../api/vocabulary";
import { AdapterDiagnostics } from "../components/Diagnostics";
import { EntityCard } from "../components/EntityCard";
import { ErrorState } from "../components/ErrorState";
import { PagedList } from "../components/PagedList";
import { Markdown } from "../components/Markdown";
import { MediaPanel, type SeekRequest } from "../components/MediaPanel";
import { RelationRow } from "../components/RelationRow";
import { RunStatusPanel } from "../components/Provenance";
import { TranscriptPanel } from "../components/TranscriptPanel";
import { DefinitionList, ExternalLink, Missing, Mono } from "../components/primitives";
import { useI18n } from "../i18n";
import type { MessageKey } from "../i18n";
import { formatBytes, formatSeconds, formatTimestamp } from "../lib/format";
import {
  DEFAULT_TAB,
  parseSeconds,
  parseTab,
  type ReaderTab,
} from "../lib/readerLink";

type Tab = ReaderTab;

const TABS: readonly { id: Tab; label: MessageKey }[] = [
  { id: "overview", label: "reader.tab.overview" },
  { id: "transcript", label: "reader.tab.transcript" },
  { id: "report", label: "reader.tab.report" },
  { id: "units", label: "reader.tab.units" },
  { id: "relations", label: "reader.tab.relations" },
  { id: "artifacts", label: "reader.tab.artifacts" },
];

const PAGE = 50;

function Overview({ source }: { source: Source }) {
  const { t, locale } = useI18n();
  const counts = source.counts ?? {};
  return (
    <div className="stack">
      <DefinitionList
        entries={[
          { label: t("reader.meta.title"), value: source.title },
          { label: t("reader.meta.author"), value: source.author },
          { label: t("reader.meta.language"), value: source.language },
          { label: t("reader.meta.duration"), value: formatSeconds(source.duration_sec) },
          {
            label: t("reader.meta.url"),
            value: source.url ? (
              <ExternalLink href={source.url}>
                {source.url}
              </ExternalLink>
            ) : null,
          },
          {
            label: t("reader.meta.importedAt"),
            value: formatTimestamp(source.imported_at, locale),
          },
          {
            label: t("reader.meta.extractedAt"),
            value: formatTimestamp(source.extracted_at, locale),
          },
          { label: t("reader.meta.sourceId"), value: <Mono>{source.id}</Mono> },
          { label: t("reader.meta.sourceType"), value: source.source_type },
          { label: t("reader.meta.externalId"), value: <Mono>{source.external_id}</Mono> },
          { label: t("reader.meta.canonicalDir"), value: <Mono>{source.canonical_dir}</Mono> },
          {
            label: t("reader.meta.adapter"),
            value: `${source.adapter.name} ${source.adapter.version}`,
          },
        ]}
      />
      <h2>{t("reader.counts.title")}</h2>
      <DefinitionList
        entries={(
          [
            ["reader.counts.knowledge_units", counts.knowledge_units],
            ["reader.counts.source_units", counts.source_units],
            ["reader.counts.derived_units", counts.derived_units],
            ["reader.counts.relationships", counts.relationships],
            ["reader.counts.captions", counts.captions],
            ["reader.counts.segments", counts.segments],
          ] as const
        ).map(([key, value]) => ({
          label: t(key),
          value: typeof value === "number" ? String(value) : null,
        }))}
      />
    </div>
  );
}

function ReportPanel({ artifact }: { artifact: Artifact | null }) {
  const { t } = useI18n();
  const state = useAsync((signal) => api.media(artifact?.id ?? "", signal), [artifact?.id ?? ""], {
    enabled: artifact !== null,
  });

  if (artifact === null) return <p className="muted">{t("reader.report.unavailable")}</p>;
  if (state.error !== null) return <ErrorState error={state.error} onRetry={state.reload} />;
  if (state.status !== "ready" || state.data === null)
    return <p className="muted">{t("common.loading")}</p>;
  return <Markdown source={state.data} />;
}

function UnitsPanel({ source, onSeek }: { source: Source; onSeek: (seconds: number) => void }) {
  const { t } = useI18n();
  const [kind, setKind] = useState<KnowledgeKind | "">("");
  const [provenance, setProvenance] = useState<ProvenanceClass | "">("");
  const [minConfidence, setMinConfidence] = useState("");

  const state = usePaged<EntityRef>(
    async (cursor, signal) => {
      const floor = Number.parseFloat(minConfidence);
      const response = await api.call("listSourceEntities", {
        params: { source_id: source.id },
        query: {
          limit: PAGE,
          ...(kind === "" ? {} : { kind }),
          ...(provenance === "" ? {} : { provenance_class: provenance }),
          ...(minConfidence !== "" && Number.isFinite(floor) ? { min_confidence: floor } : {}),
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
    [source.id, kind, provenance, minConfidence],
  );

  return (
    <div className="stack">
      <div className="filters">
        <label className="field">
          {t("library.filter.kind")}
          <select value={kind} onChange={(event) => setKind(event.currentTarget.value as KnowledgeKind | "")}>
            <option value="">{t("common.any")}</option>
            {KNOWLEDGE_KINDS.map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          {t("library.filter.sourceClass")}
          <select
            value={provenance}
            onChange={(event) => setProvenance(event.currentTarget.value as ProvenanceClass | "")}
          >
            <option value="">{t("common.any")}</option>
            {PROVENANCE_CLASSES.map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          {t("library.filter.minConfidence")}
          <input
            type="number"
            min={0}
            max={1}
            step={0.05}
            value={minConfidence}
            onChange={(event) => setMinConfidence(event.currentTarget.value)}
          />
        </label>
      </div>

      {/* `PagedList` owns the ladder and every decision in it (D-203). */}
      <PagedList
        state={state}
        label={t("reader.tab.units")}
        empty={t("reader.units.empty")}
      >
        {(entities) =>
          entities.map((entity) => (
            <EntityCard
              key={entity.global_id}
              entity={entity}
              sourceUrl={source.url}
              onSeek={onSeek}
            />
          ))
        }
      </PagedList>
    </div>
  );
}

function RelationsPanel({ source }: { source: Source }) {
  const { t } = useI18n();
  const [vocabulary, setVocabulary] = useState<IndexedRelation["relation_vocabulary"] | "">("");

  const state = usePaged<IndexedRelation>(
    async (cursor, signal) => {
      const response = await api.call("listSourceRelations", {
        params: { source_id: source.id },
        query: {
          limit: PAGE,
          ...(vocabulary === "" ? {} : { relation_vocabulary: vocabulary }),
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
    [source.id, vocabulary],
  );

  return (
    <div className="stack">
      <label className="field">
        {t("reader.relations.vocabulary")}
        <select
          value={vocabulary}
          onChange={(event) =>
            setVocabulary(event.currentTarget.value as IndexedRelation["relation_vocabulary"] | "")
          }
        >
          <option value="">{t("common.any")}</option>
          {RELATION_VOCABULARIES.map((value) => (
            <option key={value} value={value}>
              {value}
            </option>
          ))}
        </select>
      </label>

      <PagedList
        state={state}
        label={t("reader.tab.relations")}
        empty={t("reader.relations.empty")}
      >
        {(relations) =>
          relations.map((relation) => <RelationRow key={relation.id} relation={relation} />)
        }
      </PagedList>
    </div>
  );
}

function ArtifactsPanel({ artifacts }: { artifacts: readonly Artifact[] }) {
  const { t } = useI18n();
  return (
    <div className="stack">
      {artifacts.map((artifact) => (
        <article className="card stack" key={artifact.id}>
          <div className="row">
            <Mono>{artifact.id}</Mono>
            <span className="badge">{artifact.kind}</span>
            <span className="badge">{artifact.role}</span>
            {artifact.immutable && <span className="badge">{t("reader.artifacts.immutable")}</span>}
          </div>
          <DefinitionList
            entries={[
              { label: t("reader.artifacts.mediaType"), value: artifact.media_type },
              {
                label: t("reader.artifacts.path"),
                value: artifact.path ? <Mono>{artifact.path}</Mono> : null,
              },
              {
                label: t("reader.artifacts.bytes"),
                // The unit is a word, so it comes from the catalogue; the
                // number is not, so it does not. `null` in stays `null` out and
                // renders as a stated absence.
                value: (() => {
                  const size = formatBytes(artifact.bytes);
                  if (size === null) return null;
                  // Spelled out rather than built as `bytes.${unit}`: a
                  // computed key is invisible both to `MessageKey` and to
                  // `test_ui_scaffold`'s check that no catalogue entry is
                  // rendered by nothing.
                  const unit =
                    size.unit === "B"
                      ? t("bytes.B")
                      : size.unit === "KB"
                        ? t("bytes.KB")
                        : t("bytes.MB");
                  return `${size.amount} ${unit}`;
                })(),
              },
              {
                label: t("reader.artifacts.available"),
                value: artifact.available ? t("common.yes") : t("common.no"),
              },
            ]}
          />
          <div className="row">
            {artifact.role === "external" || artifact.path == null ? (
              <span className="faint">{t("reader.artifacts.externalOnly")}</span>
            ) : (
              artifact.available && (
                <a href={api.mediaUrl(artifact.id)} target="_blank" rel="noopener noreferrer">
                  {t("reader.artifacts.open")}
                </a>
              )
            )}
            {artifact.url != null && (
              <ExternalLink href={artifact.url}>
                {artifact.url}
              </ExternalLink>
            )}
          </div>
        </article>
      ))}
    </div>
  );
}

export function ReaderView() {
  const { t } = useI18n();
  const { sourceId = "" } = useParams();
  const [search, setSearch] = useSearchParams();
  const tab = parseTab(search.get("tab")) ?? DEFAULT_TAB;
  const linkedSeconds = parseSeconds(search.get("t"));

  // D-095: D-069 carried the offset into the Reader and then dropped it here.
  // `linkedSeconds` went only to `TranscriptPanel`'s `highlightSec`, so
  // `?tab=transcript&t=300` highlighted the right caption and then "Load
  // player" started the embed at 0 -- `embedUrl` has supported `start` all
  // along. Seeding the seek request with the linked offset is the whole fix:
  // `MediaPanel` already turns a request made before the player exists into
  // the frame's `start`, and one made after it into a seek.
  const [seek, setSeek] = useState<SeekRequest | null>(
    linkedSeconds === null ? null : { seconds: linkedSeconds, nonce: 0 },
  );

  // `replace` rather than `push`: the Reader is one page, and six tabs would
  // otherwise put six entries between the reader and the library they came
  // from. The URL still updates, so any tab is copyable.
  const setTab = (next: Tab) =>
    setSearch(
      (current) => {
        const params = new URLSearchParams(current);
        if (next === DEFAULT_TAB) params.delete("tab");
        else params.set("tab", next);
        return params;
      },
      { replace: true },
    );

  const requestSeek = (seconds: number) =>
    setSeek((current) => ({ seconds, nonce: (current?.nonce ?? 0) + 1 }));

  /*
   * The arrow keys the `tablist` role promises (WAI-ARIA tabs, D-203).
   *
   * A `role="tab"` announces itself as one of a set a reader moves through
   * with the arrows; without them the role describes a control that does not
   * exist. `Home`/`End` are the same promise at the ends, and the moved tab is
   * focused as well as selected, because a roving `tabIndex` that does not
   * follow focus leaves the keyboard on an element that is no longer the stop.
   *
   * The refs are how focus reaches the new tab: this is a controlled set with
   * no DOM query to make, and `querySelector` on an id would be a second
   * spelling of the id the markup already writes.
   */
  const tabs = useRef(new Map<Tab, HTMLButtonElement>());
  const onTabKeyDown = (event: KeyboardEvent<HTMLButtonElement>) => {
    const step =
      event.key === "ArrowRight" || event.key === "ArrowDown"
        ? 1
        : event.key === "ArrowLeft" || event.key === "ArrowUp"
          ? -1
          : 0;
    const index = TABS.findIndex((entry) => entry.id === tab);
    let next: Tab | null = null;
    if (step !== 0) {
      // Wrapping, which the pattern specifies: the set is a ring.
      next = (TABS[(index + step + TABS.length) % TABS.length] as (typeof TABS)[number]).id;
    } else if (event.key === "Home") {
      next = (TABS[0] as (typeof TABS)[number]).id;
    } else if (event.key === "End") {
      next = (TABS[TABS.length - 1] as (typeof TABS)[number]).id;
    }
    if (next === null) return;
    event.preventDefault();
    setTab(next);
    tabs.current.get(next)?.focus();
  };

  const state = useAsync(
    (signal) => api.call("getSource", { params: { source_id: sourceId }, signal }),
    [sourceId],
  );

  if (state.error !== null) {
    return (
      <div className="stack">
        <Link to="/">{t("common.back")}</Link>
        <ErrorState error={state.error} onRetry={state.reload} />
      </div>
    );
  }
  if (state.status !== "ready" || state.data === null) {
    return <p className="muted">{t("common.loading")}</p>;
  }

  const { source, artifacts } = state.data.data;
  const transcript = artifactOfKind(artifacts, "transcript");
  const report = artifactOfKind(artifacts, "report");

  return (
    <div className="stack">
      <Link to="/">{t("common.back")}</Link>
      <h1 dir="auto">{source.title ?? <Missing />}</h1>

      <div className="reader">
        <div>
          {/*
            The whole ARIA tabs pattern, not the one attribute of it (D-203).
            
            These were six `role="tab"` buttons with no `id`, no
            `aria-controls`, no `role="tabpanel"` anywhere in `src/`, no roving
            `tabIndex` and no arrow keys — so a screen reader announced
            "Transcript, tab, 2 of 6" and nothing told the reader where its
            content was, and the keyboard had to walk through all six to reach
            the panel. A role that lies is worse than no role: it promises a
            relationship and a set of keys that are not there.

            Four things make it true, and each one is a promise the role makes:
            `aria-controls` naming the panel, the panel's `aria-labelledby`
            naming the tab back, a roving `tabIndex` so the tablist is one stop
            rather than six, and the arrow keys the pattern specifies.
          */}
          <div className="tabs" role="tablist" aria-label={t("reader.tablist")}>
            {TABS.map((entry) => (
              <button
                key={entry.id}
                type="button"
                role="tab"
                id={`reader-tab-${entry.id}`}
                className="tabs__tab"
                aria-selected={tab === entry.id}
                aria-controls={`reader-panel-${entry.id}`}
                // One tab stop for the whole set, which is what makes the
                // arrow keys below the way through it (WAI-ARIA tabs).
                tabIndex={tab === entry.id ? 0 : -1}
                ref={(element) => {
                  if (element !== null) tabs.current.set(entry.id, element);
                  else tabs.current.delete(entry.id);
                }}
                onClick={() => setTab(entry.id)}
                onKeyDown={onTabKeyDown}
              >
                {t(entry.label)}
              </button>
            ))}
          </div>

          {/*
            One panel per tab, and only the selected one is rendered — which is
            allowed: the pattern requires the *selected* panel to exist and be
            labelled, not all six. `tabIndex={0}` makes it the keyboard's next
            stop after the tablist, so Tab out of a tab lands in what it
            controls.
          */}
          <div
            role="tabpanel"
            id={`reader-panel-${tab}`}
            aria-labelledby={`reader-tab-${tab}`}
            tabIndex={0}
            data-reader-panel={tab}
          >
            {tab === "overview" && <Overview source={source} />}
            {tab === "transcript" && (
              <TranscriptPanel
                artifact={transcript}
                sourceUrl={source.url ?? null}
                onSeek={requestSeek}
                highlightSec={linkedSeconds}
              />
            )}
            {tab === "report" && <ReportPanel artifact={report} />}
            {tab === "units" && <UnitsPanel source={source} onSeek={requestSeek} />}
            {tab === "relations" && <RelationsPanel source={source} />}
            {tab === "artifacts" && <ArtifactsPanel artifacts={artifacts} />}
          </div>
        </div>

        <aside className="stack">
          <MediaPanel source={source} artifacts={artifacts} seek={seek} />
          <section className="panel stack" aria-label={t("status.legend")}>
            <h2 className="panel__title">{t("status.legend")}</h2>
            <RunStatusPanel source={source} />
          </section>
          <AdapterDiagnostics source={source} />
        </aside>
      </div>
    </div>
  );
}
