/**
 * One source, in the two library layouts.
 *
 * Two rules show up here rather than only in the Reader:
 *
 * - Status is the copied `validation` / `coverage` / `overall` triple. A card
 *   that showed only `overall` would hide the `fail-run` case, where coverage
 *   passes under a failing validation.
 * - D-045's two diagnostic channels are surfaced *wherever a source is shown*,
 *   so a run that was indexed with named gaps says so in the library and not
 *   only after you open it. They are absent when there is nothing to report,
 *   so the line does not appear for a clean run.
 */

import { Link } from "react-router-dom";

import { adapterDiagnostics } from "../api/canonical";
import type { Source } from "../api/contract";
import { useI18n } from "../i18n";
import { formatSeconds, formatTimestamp } from "../lib/format";
import { StatusBadge } from "./Provenance";
import { Missing, Mono } from "./primitives";

function Count({ label, value }: { label: string; value: number | undefined }) {
  return (
    <span>
      {label}: {typeof value === "number" ? value : <Missing />}
    </span>
  );
}

export function SourceCard({ source, compact = false }: { source: Source; compact?: boolean }) {
  const { t, locale } = useI18n();
  const { unmappableArtifacts, unreadableFiles } = adapterDiagnostics(source.adapter_metadata);
  const counts = source.counts ?? {};
  const duration = formatSeconds(source.duration_sec);

  return (
    <article className="card stack" data-source-id={source.id}>
      <h2 className="source-card__title">
        <Link to={`/sources/${encodeURIComponent(source.id)}`} dir="auto">
          {source.title ?? <Missing />}
        </Link>
      </h2>

      <div className="row">
        <StatusBadge status={source.status.overall} label={t("status.overall")} />
        <StatusBadge status={source.status.validation} label={t("status.validation")} />
        <StatusBadge status={source.status.coverage} label={t("status.coverage")} />
      </div>

      <div className="metrics">
        <span>{source.source_type}</span>
        <span>{source.language ?? <Missing />}</span>
        <span>{duration ?? <Missing />}</span>
        {!compact && <span>{formatTimestamp(source.imported_at, locale) ?? <Missing />}</span>}
      </div>

      <div className="metrics">
        <Count label={t("reader.counts.knowledge_units")} value={counts.knowledge_units} />
        <Count label={t("reader.counts.relationships")} value={counts.relationships} />
        {!compact && <Count label={t("reader.counts.captions")} value={counts.captions} />}
      </div>

      {!compact && (
        <p className="faint">
          <Mono>{source.id}</Mono>
        </p>
      )}

      {(unmappableArtifacts.length > 0 || unreadableFiles.length > 0) && (
        <p className="faint diagnostics">
          {t("reader.diagnostics.title")}
          {": "}
          {unmappableArtifacts.length > 0 && (
            <>
              {t("reader.diagnostics.unmappable")} ({unmappableArtifacts.length}){" "}
            </>
          )}
          {unreadableFiles.length > 0 && (
            <>
              {t("reader.diagnostics.unreadable")} ({unreadableFiles.length})
            </>
          )}
        </p>
      )}
    </article>
  );
}
