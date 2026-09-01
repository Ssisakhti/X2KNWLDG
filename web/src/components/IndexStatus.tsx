/**
 * What the index can currently answer with, said plainly.
 *
 * `absent` and `building` are reported as themselves. A UI that cannot tell an
 * empty index from an unbuilt one will show "no sources" as a fact about the
 * user's library, which is the failure `503 index_unavailable` and the
 * `IndexState` vocabulary both exist to prevent.
 *
 * The `runs` object is D-050 and is **optional in the contract**: an
 * implementation that scans no filesystem omits it rather than reporting a
 * zero it did not measure. So its absence is rendered as "this server does not
 * report skipped runs" and never as "nothing was skipped" -- those are
 * different claims, and only one of them is supported by the payload.
 */

import type { StatusPayload } from "../api/contract";
import { useI18n } from "../i18n";
import type { MessageKey } from "../i18n";
import { formatTimestamp } from "../lib/format";
import { DefinitionList, Missing, Mono } from "./primitives";

const STATE_MESSAGE: Record<StatusPayload["index"]["state"], MessageKey> = {
  absent: "index.state.absent",
  building: "index.state.building",
  ready: "index.state.ready",
  error: "index.state.error",
};

export function IndexStatusPanel({ status }: { status: StatusPayload }) {
  const { t, locale } = useI18n();
  const state = status.index.state;
  const runs = status.runs;

  return (
    <section className={`notice notice--index-${state} stack`} data-index-state={state}>
      <div className="row">
        <strong>{t("index.title")}</strong>
        <span>{t(STATE_MESSAGE[state])}</span>
      </div>

      <div className="metrics">
        <span>
          {t("index.counts.sources")}: {status.counts.sources}
        </span>
        <span>
          {t("index.counts.artifacts")}: {status.counts.artifacts}
        </span>
        <span>
          {t("index.counts.entities")}: {status.counts.entities}
        </span>
        <span>
          {t("index.counts.relations")}: {status.counts.relations}
        </span>
      </div>

      <DefinitionList
        entries={[
          {
            label: t("index.builtAt"),
            value: formatTimestamp(status.index.built_at, locale),
          },
          {
            label: t("index.version"),
            value:
              typeof status.index.index_version === "number"
                ? String(status.index.index_version)
                : null,
          },
        ]}
      />

      <div>
        <strong>{t("index.runs.title")}</strong>
        {runs === undefined ? (
          <p className="faint">{t("index.runs.unreported")}</p>
        ) : (
          <>
            <p className="faint">
              {t("index.runs.discovered")}: {runs.discovered} · {t("index.runs.indexed")}:{" "}
              {runs.indexed}
            </p>
            {runs.skipped.length === 0 ? (
              <p className="faint">{t("index.runs.noneSkipped")}</p>
            ) : (
              <>
                <p className="faint">{t("index.runs.skipped")}</p>
                <ul>
                  {runs.skipped.map((run) => (
                    <li key={run.relative_path}>
                      <Mono>{run.relative_path}</Mono>
                      {" — "}
                      <span dir="auto">{run.reason || <Missing />}</span>
                    </li>
                  ))}
                </ul>
              </>
            )}
          </>
        )}
      </div>
    </section>
  );
}
