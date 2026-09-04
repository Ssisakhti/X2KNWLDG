/**
 * Quick Read: the stored record, whole, in a stated order (`T-207`, D-131).
 *
 * The last step of D-130's journey, and the one that keeps the reader inside
 * `#/map`. Everything here is copied out of `/api/entities/{entity_id}`; there
 * is no summary, no derived title, no completed field and no rounded number.
 * D-131 names the order and it is the order of the sections below, because the
 * order *is* the requirement:
 *
 * 1. **The complete stored statement.** Not cut. `previewText` exists for
 *    lists and cards, where a 4096-character `normalized_statement` would
 *    bury everything else; this is the surface that exists so the whole
 *    statement can be read (ADR 0005 invariant 12).
 * 2. **The recorded evidence and locator.** The verbatim excerpt the pipeline
 *    stored, the time range as recorded, and the segment and artifact it came
 *    from. A source-class knowledge unit must have a locator by schema; an
 *    entity with none says so rather than showing an empty block.
 * 3. **The active relations** -- what this entity is connected to inside the
 *    bounded neighbourhood, each naming its real relation and direction.
 * 4. **The derivation.** `derived_from` and the recorded `derivation_note`,
 *    verbatim: a derived unit must show its work, and this is where the work
 *    is shown.
 * 5. **Provenance and source**, then
 * 6. **the technical metadata** -- ids, kind, entity type, canonical path,
 *    schema version. Last, because a reader arrives wanting the knowledge and
 *    the identifiers are what they need only once they want to trace it.
 *
 * **`readerPath` is the escape hatch, not the destination.** D-130 reserves
 * the full Reader for reading the *source* in depth, and the link carries the
 * locator's real `start_sec` when the record has one -- `readerLink` builds it,
 * so the timestamp is the same grammar the Library's hits use and a record with
 * no time simply carries none rather than `t=0` (D-069).
 *
 * **Collapsible, through the one disclosure** (`T-208`). `T-207` made this
 * panel a `<details>` of its own and stopped there; the panel is now a
 * `Disclosure`, which is the same platform element written once for the three
 * panels that compete for one screen. What that costs is a nested collapse
 * nobody wanted -- Quick Read's own summary is the *panel's* summary now, and
 * it keeps stating which record is folded away: provenance, kind and identity.
 *
 * Not `EntityCard`. The Reader's card renders the same record and is right for
 * the Reader -- it leads with the provenance badge row and ends with the ids --
 * but D-131 fixes a *different* order for this surface, and the statement
 * coming first is the half of that order that matters. Two components, one
 * record, two stated orders; the atoms (`Bidi`, `DefinitionList`, `Missing`,
 * `Mono`, `ProvenanceBadge`, `formatSeconds`) are shared.
 */

import { Link } from "react-router-dom";

import type { EntityRef, Locator } from "../api/contract";
import { ApiFailure } from "../api/errors";
import { useI18n } from "../i18n";
import { formatConfidence, formatSeconds } from "../lib/format";
import { readerPath } from "../lib/readerLink";
import type { ActiveRelation } from "../map/neighbourhood";
import type { NeighbourhoodFailure } from "../map/useNeighbourhood";
import { Disclosure } from "./Disclosure";
import { ErrorState } from "./ErrorState";
import { RelationCues } from "./MapRelation";
import { KindBadge, ProvenanceBadge } from "./Provenance";
import { Bidi, DefinitionList, Missing, Mono } from "./primitives";

/** The two locator types an adapter produces. The other four are reserved. */
function timeRangeOf(locator: Locator | null | undefined) {
  return locator != null && locator.type === "time_range" ? locator : null;
}

function textSpanOf(locator: Locator | null | undefined) {
  return locator != null && locator.type === "text_span" ? locator : null;
}

function Evidence({ entity }: { entity: EntityRef }) {
  const { t } = useI18n();
  const locator = entity.locator;
  if (locator == null) return <p className="faint">{t("reader.units.locatorNone")}</p>;
  const span = textSpanOf(locator);
  if (span !== null) {
    // T-228 (D-233). The excerpt goes through `Bidi` exactly as a time-range
    // excerpt does, and that is the whole reason this branch exists rather
    // than falling through: a post's excerpt is the case most likely to be
    // Persian, and `JSON.stringify` would render it as an escaped string with
    // no direction isolation — the one rendering the bidi rules forbid.
    return (
      <>
        {span.excerpt !== undefined && (
          <Bidi as="blockquote" className="excerpt" marks={{ "data-map-excerpt": "recorded" }}>
            {span.excerpt}
          </Bidi>
        )}
        <DefinitionList
          entries={[
            {
              label: t("reader.units.locator"),
              value: (
                <Mono>{t("text.range", { start: span.start_char, end: span.end_char })}</Mono>
              ),
            },
            {
              label: t("reader.units.locatorPost"),
              value: <Mono>{span.artifact_id}</Mono>,
            },
          ]}
        />
      </>
    );
  }
  const range = timeRangeOf(locator);
  if (range === null) {
    // One of the four still-reserved types. Its own fields are printed rather
    // than being squeezed into a shape that would misreport its coordinates.
    return (
      <p className="faint">
        <Mono>{JSON.stringify(locator)}</Mono>
      </p>
    );
  }
  const start = formatSeconds(range.start_sec);
  const end = formatSeconds(range.end_sec);
  return (
    <>
      {range.excerpt !== undefined && (
        <Bidi as="blockquote" className="excerpt" marks={{ "data-map-excerpt": "recorded" }}>
          {range.excerpt}
        </Bidi>
      )}
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
            value: range.segment_id === undefined ? null : <Mono>{range.segment_id}</Mono>,
          },
          {
            label: "artifact_id",
            value: range.artifact_id === undefined ? null : <Mono>{range.artifact_id}</Mono>,
          },
        ]}
      />
    </>
  );
}

export function MapQuickRead({
  focus,
  entity,
  error,
  onRetry,
  relations,
  loading = false,
}: {
  /** The focused `global_id`, or `null`. */
  focus: string | null;
  /** The record `/api/entities/{entity_id}` returned, or `null`. */
  entity: EntityRef | null;
  error: NeighbourhoodFailure | null;
  onRetry: () => void;
  /** The focus's own relations from the bounded neighbourhood. */
  relations: readonly ActiveRelation[];
  loading?: boolean;
}) {
  const { t } = useI18n();

  const start = timeRangeOf(entity?.locator)?.start_sec ?? null;
  const confidence = formatConfidence(entity?.confidence ?? null);

  /*
   * The badge row is the panel's summary now (`T-208`), rather than a second
   * `<summary>` nested inside it. What a collapsed Quick Read has to keep
   * saying is *which record it holds* -- provenance, kind and identity -- so
   * that folding the reading away never costs the reader the knowledge that
   * the reading is there.
   */
  const summary =
    focus === null ? (
      t("map.panel.nothingFocused")
    ) : (
      <span className="row">
        {entity !== null && <ProvenanceBadge provenance={entity.provenance_class} />}
        {entity !== null && <KindBadge kind={entity.kind} />}
        <Mono>{focus}</Mono>
      </span>
    );

  return (
    <Disclosure
      id="quickread"
      className="map__quickread"
      title={t("map.quickRead.title")}
      summary={summary}
      preferOpen={focus !== null}
      {...(focus === null ? {} : { marks: { "data-map-quickread": focus } })}
    >
      {focus === null && <p className="muted">{t("map.quickRead.noFocus")}</p>}

      {focus !== null && (
        <>
          <p className="faint">{t("map.quickRead.hint")}</p>

          {loading && <p className="muted">{t("common.loading")}</p>}
          {error instanceof ApiFailure && <ErrorState error={error} onRetry={onRetry} />}
          {error !== null && !(error instanceof ApiFailure) && (
            <p className="notice notice--internal" role="alert">
              {t("map.conflict.detail", { kind: error.kind, id: error.id, field: error.field })}
            </p>
          )}

          {entity !== null && (
            <div className="stack map__quickread__body">
              {/* 1 — the complete stored statement, uncut. */}
              <section className="stack">
                <h3>{t("map.quickRead.statement")}</h3>
                {entity.label == null ? (
                  <Missing />
                ) : (
                  <Bidi as="p" marks={{ "data-map-statement": "complete" }}>
                    {entity.label}
                  </Bidi>
                )}
                <p className="faint">{t("map.quickRead.statementNote")}</p>
              </section>

              {/* 2 — the recorded evidence and its locator. */}
              <section className="stack">
                <h3>{t("map.quickRead.evidence")}</h3>
                <Evidence entity={entity} />
              </section>

              {/* 3 — the active relations, each naming its own direction. */}
              <section className="stack" data-map-quickread-relations={relations.length}>
                <h3>{t("map.quickRead.relations")}</h3>
                <RelationCues
                  relations={relations}
                  subject="focus"
                  empty={t("map.quickRead.noRelations")}
                  confidence
                />
              </section>

              {/* 4 — the derivation, verbatim. */}
              <section className="stack">
                <h3>{t("map.quickRead.derivation")}</h3>
                {entity.derived_from == null || entity.derived_from.length === 0 ? (
                  <p className="faint">{t("map.quickRead.noDerivation")}</p>
                ) : (
                  <p className="faint">
                    {t("reader.units.derivedFrom")}:{" "}
                    {entity.derived_from.map((id) => (
                      <Mono key={id}>{id} </Mono>
                    ))}
                  </p>
                )}
                {entity.derivation_note != null && (
                  <Bidi as="p">
                    {t("reader.units.derivationNote")}: {entity.derivation_note}
                  </Bidi>
                )}
              </section>

              {/* 5 — provenance and source, with the escape hatch into the Reader. */}
              <section className="stack">
                <h3>{t("map.quickRead.provenance")}</h3>
                <DefinitionList
                  entries={[
                    {
                      label: t("map.quickRead.provenanceClass"),
                      value: <Mono>{entity.provenance_class}</Mono>,
                    },
                    {
                      label: t("reader.units.confidence"),
                      value: confidence,
                    },
                    {
                      label: t("map.quickRead.source"),
                      value: entity.source_id == null ? null : <Mono>{entity.source_id}</Mono>,
                    },
                  ]}
                />
                {entity.source_id != null && (
                  <div className="row">
                    <Link
                      to={readerPath(entity.source_id, { tab: "units", seconds: start })}
                      data-map-reader-link
                    >
                      {t("map.quickRead.openReader")}
                    </Link>
                    <span className="faint">
                      {start === null
                        ? t("map.quickRead.readerNoTime")
                        : t("map.quickRead.readerAt", { time: formatSeconds(start) ?? "" })}
                    </span>
                  </div>
                )}
              </section>

              {/* 6 — the identifiers, last. */}
              <section className="stack">
                <h3>{t("map.quickRead.technical")}</h3>
                <DefinitionList
                  entries={[
                    { label: "global_id", value: <Mono>{entity.global_id}</Mono> },
                    { label: "local_id", value: <Mono>{entity.local_id}</Mono> },
                    {
                      label: t("reader.units.libraryId"),
                      value: entity.library_id == null ? null : <Mono>{entity.library_id}</Mono>,
                    },
                    { label: "entity_type", value: <Mono>{entity.entity_type}</Mono> },
                    {
                      label: t("map.quickRead.kind"),
                      value: entity.kind == null ? null : <Mono>{entity.kind}</Mono>,
                    },
                    {
                      label: t("reader.units.canonicalPath"),
                      value:
                        entity.canonical_path == null ? null : <Mono>{entity.canonical_path}</Mono>,
                    },
                    { label: "schema_version", value: <Mono>{entity.schema_version}</Mono> },
                  ]}
                />
              </section>
            </div>
          )}
        </>
      )}
    </Disclosure>
  );
}
