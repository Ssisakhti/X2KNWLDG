/**
 * One knowledge unit, with its evidence and its provenance.
 *
 * Everything on this card is copied. The excerpt is the canonical verbatim
 * excerpt, the confidence is the recorded number or a visible absence, and the
 * locator's coordinates are printed as recorded. Nothing is rounded up,
 * defaulted, or summarised: `label` is `normalized_statement` or `content` as
 * the pipeline already chose it, never a new summary.
 *
 * The provenance rail on the inline-start edge, the badge's glyph, and the
 * badge's word are three independent signals of the same fact (ADR 0001
 * invariant 10).
 */

import type { EntityRef, Locator } from "../api/contract";
import { useI18n } from "../i18n";
import { formatConfidence, formatSeconds, youtubeTimestampUrl } from "../lib/format";
import { ProvenanceBadge } from "./Provenance";
import { Bidi, DefinitionList, Missing, Mono } from "./primitives";

function timeRangeOf(locator: Locator | null | undefined) {
  return locator != null && locator.type === "time_range" ? locator : null;
}

function LocatorDetail({ locator }: { locator: Locator }) {
  const { t } = useI18n();
  if (locator.type === "time_range") {
    const start = formatSeconds(locator.start_sec);
    const end = formatSeconds(locator.end_sec);
    return (
      <DefinitionList
        entries={[
          {
            label: t("reader.units.locator"),
            value:
              start === null && end === null ? null : (
                <Mono>{t("time.range", { start: start ?? "?", end: end ?? "?" })}</Mono>
              ),
          },
          {
            label: "segment_id",
            value: locator.segment_id ? <Mono>{locator.segment_id}</Mono> : null,
          },
          {
            label: "artifact_id",
            value: locator.artifact_id ? <Mono>{locator.artifact_id}</Mono> : null,
          },
        ]}
      />
    );
  }
  if (locator.type === "text_span") {
    // T-228: the second locator type an adapter produces (D-233). Its own
    // coordinate, not seconds — a post has no timeline, and rendering one
    // would be a coordinate the record does not carry. The artifact id is the
    // post, so it is labelled as one rather than shown bare.
    return (
      <DefinitionList
        entries={[
          {
            label: t("reader.units.locator"),
            value: (
              <Mono>
                {t("text.range", { start: locator.start_char, end: locator.end_char })}
              </Mono>
            ),
          },
          {
            label: t("reader.units.locatorPost"),
            value: <Mono>{locator.artifact_id}</Mono>,
          },
        ]}
      />
    );
  }
  // The four remaining locator types are reserved in v1 and produced by no
  // adapter. If one ever arrives, its own fields are shown rather than being
  // squeezed into a shape that would misreport its coordinates.
  return (
    <p className="faint">
      <Mono>{JSON.stringify(locator)}</Mono>
    </p>
  );
}

export function EntityCard({
  entity,
  sourceUrl,
  onSeek,
}: {
  entity: EntityRef;
  sourceUrl?: string | null;
  onSeek?: (seconds: number) => void;
}) {
  const { t } = useI18n();
  const range = timeRangeOf(entity.locator);
  const confidence = formatConfidence(entity.confidence);
  const deepLink = youtubeTimestampUrl(sourceUrl ?? null, range?.start_sec ?? null);

  return (
    <article
      className={`card card--${entity.provenance_class} stack`}
      data-global-id={entity.global_id}
    >
      <div className="row">
        <ProvenanceBadge provenance={entity.provenance_class} />
        <span className="badge">{entity.kind ?? t("common.notStated")}</span>
        <span className="faint">
          {t("reader.units.confidence")}: {confidence ?? <Missing />}
        </span>
        <span className="shell__spacer" />
        <Mono>{entity.local_id}</Mono>
      </div>

      <Bidi as="p">{entity.label ?? <Missing />}</Bidi>

      {range !== null && range.excerpt !== undefined && (
        <Bidi as="blockquote" className="excerpt">
          {range.excerpt}
        </Bidi>
      )}

      {entity.locator != null ? (
        <LocatorDetail locator={entity.locator} />
      ) : (
        <p className="faint">{t("reader.units.locatorNone")}</p>
      )}

      {(onSeek !== undefined || deepLink !== null) && range !== null && (
        <div className="row">
          {onSeek !== undefined && typeof range.start_sec === "number" && (
            <button type="button" className="button" onClick={() => onSeek(range.start_sec)}>
              {t("reader.transcript.seek")} · {formatSeconds(range.start_sec)}
            </button>
          )}
          {deepLink !== null && (
            <a href={deepLink} target="_blank" rel="noopener noreferrer">
              {t("search.openExternal")}
            </a>
          )}
        </div>
      )}

      {entity.derived_from != null && entity.derived_from.length > 0 && (
        <p className="faint">
          {t("reader.units.derivedFrom")}:{" "}
          {entity.derived_from.map((id) => (
            <Mono key={id}>{id} </Mono>
          ))}
        </p>
      )}

      {entity.derivation_note != null && (
        <Bidi as="p" className="faint">
          {t("reader.units.derivationNote")}: {entity.derivation_note}
        </Bidi>
      )}

      <p className="faint">
        {entity.library_id != null && (
          <>
            {t("reader.units.libraryId")}: <Mono>{entity.library_id}</Mono>
            {" · "}
          </>
        )}
        {entity.canonical_path != null && (
          <>
            {t("reader.units.canonicalPath")}: <Mono>{entity.canonical_path}</Mono>
          </>
        )}
      </p>
    </article>
  );
}
