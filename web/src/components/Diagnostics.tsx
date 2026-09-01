/**
 * What the adapter could not map, shown where the source is shown (D-045).
 *
 * The adapter states its omissions on `Source.adapter_metadata` through two
 * channels -- `unmappable_artifacts` (a generated note whose filename cannot
 * spell an id, skipped and named) and `unreadable_files` (a canonical file
 * present but damaged, named so a missing count is not read as a zero). Both
 * are **absent** when there is nothing to report, so this component renders
 * nothing at all in the ordinary case and is never a permanently empty panel.
 *
 * Letting either omission disappear between the run and the Reader is the
 * failure D-045 was written about, so it is surfaced next to the source rather
 * than buried behind a detail toggle.
 */

import { adapterDiagnostics, type Diagnostic } from "../api/canonical";
import type { Source } from "../api/contract";
import { useI18n } from "../i18n";
import { Mono } from "./primitives";

function DiagnosticList({ title, entries }: { title: string; entries: readonly Diagnostic[] }) {
  if (entries.length === 0) return null;
  return (
    <div>
      <strong>{title}</strong>
      <ul>
        {entries.map((entry) => (
          <li key={`${entry.path}|${entry.reason}`}>
            <Mono>{entry.path}</Mono>
            {entry.reason !== "" && (
              <>
                {" — "}
                <span dir="auto">{entry.reason}</span>
              </>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

export function AdapterDiagnostics({ source }: { source: Source }) {
  const { t } = useI18n();
  const { unmappableArtifacts, unreadableFiles } = adapterDiagnostics(source.adapter_metadata);
  if (unmappableArtifacts.length === 0 && unreadableFiles.length === 0) return null;
  return (
    <section className="diagnostics stack" aria-label={t("reader.diagnostics.title")}>
      <h2>{t("reader.diagnostics.title")}</h2>
      <DiagnosticList title={t("reader.diagnostics.unmappable")} entries={unmappableArtifacts} />
      <DiagnosticList title={t("reader.diagnostics.unreadable")} entries={unreadableFiles} />
      <p className="faint">{t("reader.diagnostics.note")}</p>
    </section>
  );
}
