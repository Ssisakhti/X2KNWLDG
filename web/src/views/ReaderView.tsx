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
 */

import { useState } from "react";
import { Link, useParams } from "react-router-dom";

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
import { Markdown } from "../components/Markdown";
import { MediaPanel, type SeekRequest } from "../components/MediaPanel";
import { RelationRow } from "../components/RelationRow";
import { RunStatusPanel } from "../components/Provenance";
import { TranscriptPanel } from "../components/TranscriptPanel";
import { DefinitionList, Missing, Mono } from "../components/primitives";
import { useI18n } from "../i18n";
import type { MessageKey } from "../i18n";
import { formatBytes, formatSeconds, formatTimestamp } from "../lib/format";

type Tab = "overview" | "transcript" | "report" | "units" | "relations" | "artifacts";

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
              <a href={source.url} target="_blank" rel="noopener noreferrer">
                {source.url}
              </a>
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

      {state.error !== null ? (
        <ErrorState error={state.error} onRetry={state.reload} />
      ) : state.status === "loading" ? (
        <p className="muted">{t("common.loading")}</p>
      ) : state.items.length === 0 ? (
        <p className="muted">{t("reader.units.empty")}</p>
      ) : (
        <>
          <p className="faint">
            {state.total === null
              ? t("common.unknownTotal")
              : t("common.total", { count: state.total })}
          </p>
          {state.items.map((entity) => (
            <EntityCard
              key={entity.global_id}
              entity={entity}
              sourceUrl={source.url}
              onSeek={onSeek}
            />
          ))}
          {state.hasMore && (
            <button type="button" className="button" onClick={state.loadMore}>
              {t("common.more")}
            </button>
          )}
        </>
      )}
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

      {state.error !== null ? (
        <ErrorState error={state.error} onRetry={state.reload} />
      ) : state.status === "loading" ? (
        <p className="muted">{t("common.loading")}</p>
      ) : state.items.length === 0 ? (
        <p className="muted">{t("reader.relations.empty")}</p>
      ) : (
        <>
          <p className="faint">
            {state.total === null
              ? t("common.unknownTotal")
              : t("common.total", { count: state.total })}
          </p>
          {state.items.map((relation) => (
            <RelationRow key={relation.id} relation={relation} />
          ))}
          {state.hasMore && (
            <button type="button" className="button" onClick={state.loadMore}>
              {t("common.more")}
            </button>
          )}
        </>
      )}
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
              { label: t("reader.artifacts.bytes"), value: formatBytes(artifact.bytes) },
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
              <a href={artifact.url} target="_blank" rel="noopener noreferrer">
                {artifact.url}
              </a>
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
  const [tab, setTab] = useState<Tab>("overview");
  const [seek, setSeek] = useState<SeekRequest | null>(null);

  const requestSeek = (seconds: number) =>
    setSeek((current) => ({ seconds, nonce: (current?.nonce ?? 0) + 1 }));

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
          <div className="tabs" role="tablist">
            {TABS.map((entry) => (
              <button
                key={entry.id}
                type="button"
                role="tab"
                className="tabs__tab"
                aria-selected={tab === entry.id}
                onClick={() => setTab(entry.id)}
              >
                {t(entry.label)}
              </button>
            ))}
          </div>

          {tab === "overview" && <Overview source={source} />}
          {tab === "transcript" && (
            <TranscriptPanel
              artifact={transcript}
              sourceUrl={source.url ?? null}
              onSeek={requestSeek}
            />
          )}
          {tab === "report" && <ReportPanel artifact={report} />}
          {tab === "units" && <UnitsPanel source={source} onSeek={requestSeek} />}
          {tab === "relations" && <RelationsPanel source={source} />}
          {tab === "artifacts" && <ArtifactsPanel artifacts={artifacts} />}
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
