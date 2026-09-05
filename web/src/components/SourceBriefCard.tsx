/**
 * The one readable card on the Source Map's stage (`T-256`).
 *
 * ADR 0006 clause 4 allows one rich card at a time, and this is the Source
 * Map's. It carries what a source *is* — its title, its medium, whether it has
 * a brief and what its run said — and then the brief itself: thesis, key
 * points, limitations, each naming the knowledge units it rests on.
 *
 * Three things this card will not do, each because a record does not support it:
 *
 * - **It never summarises a brief.** The narrative is Persian in the canonical
 *   document and is rendered as written. Shortening it here would be a second,
 *   unsourced statement of what the source says, and the output-language policy
 *   is explicit that a brief's text is the record's.
 * - **It never shows a status without a brief.** `PASS`/`PARTIAL` come from the
 *   brief, and a source with no brief has no status to state — the run has one,
 *   but this response does not carry it, and reading one in from elsewhere would
 *   be the card asserting something it was not told.
 * - **It never hides a stale brief.** `stale` is carried with its state said out
 *   loud, which is what the response does and why `stale` differs from
 *   `unavailable` by more than a word.
 */

import type { EntityRef, SourceKnowledgeAvailability } from "../api/contract";
import { useI18n } from "../i18n";
import { readerPath } from "../lib/readerLink";
import { mapPath } from "../lib/mapLink";
import { Bidi, Mono } from "./primitives";
import { StatusBadge } from "./Provenance";
import { BasedOn, BriefStateBadge, MediumBadge } from "./SourceMarks";
import { Link } from "react-router-dom";

export function SourceBriefCard({
  source,
  knowledge,
  compact = false,
}: {
  source: EntityRef;
  knowledge: SourceKnowledgeAvailability;
  /** Below the widest tier the brief shows its thesis and counts the rest. */
  compact?: boolean;
}) {
  const { t } = useI18n();
  const brief = knowledge.brief;
  const points = brief === null ? [] : compact ? brief.key_points.slice(0, 1) : brief.key_points;
  const hidden = brief === null ? 0 : brief.key_points.length - points.length;

  return (
    <article
      className="sourcecard sourcecard--primary"
      data-source-card={source.source_id ?? source.global_id}
      data-source-brief={knowledge.state}
    >
      <div className="sourcecard__head">
        <MediumBadge sourceType={source.source_type} />
        <BriefStateBadge state={knowledge.state} />
        {brief !== null && <StatusBadge status={brief.status} label={t("source.status")} />}
      </div>
      {brief !== null && brief.status !== "PASS" && (
        // A brief may never claim more than the run it was written from, so a
        // status below PASS is explained rather than left to read as a defect.
        <p className="faint" data-source-status-note>
          {t("source.brief.statusNote")}
        </p>
      )}

      {/*
        A heading, with the title bidi-isolated inside it. `Bidi` renders a span,
        a paragraph, a div or a blockquote and deliberately not a heading — the
        outline is the document's and a component that could mint an `h2`
        anywhere is a component that can break it — so the heading is here and
        the isolation is inside it.
      */}
      <h2 className="sourcecard__title">
        <Bidi>{source.label}</Bidi>
      </h2>

      {brief === null ? (
        <div className="sourcecard__brief">
          <h3 className="sourcecard__label">{t("source.brief.title")}</h3>
          <p className="muted">
            {knowledge.state === "unavailable"
              ? t("source.brief.unavailableNote")
              : t("source.brief.staleNote")}
          </p>
          {knowledge.reason !== null && (
            <p className="faint">
              <Mono>{knowledge.reason}</Mono>
            </p>
          )}
        </div>
      ) : (
        <div className="sourcecard__brief">
          {knowledge.state === "stale" && (
            <p className="notice notice--stale" data-source-stale>
              {t("source.brief.staleNote")}
              {knowledge.reason !== null && (
                <>
                  {" "}
                  <Mono>{knowledge.reason}</Mono>
                </>
              )}
            </p>
          )}

          <h3 className="sourcecard__label">{t("source.brief.thesis")}</h3>
          <p className="sourcecard__thesis">
            <Bidi>{brief.thesis.content}</Bidi>
            <BasedOn ids={brief.thesis.based_on} />
          </p>

          {points.length > 0 && (
            <>
              <h3 className="sourcecard__label">{t("source.brief.keyPoints")}</h3>
              <ul className="sourcecard__points">
                {points.map((point) => (
                  <li key={point.id}>
                    <Mono>{point.id}</Mono>
                    <span>
                      <Bidi>{point.content}</Bidi>
                      <BasedOn ids={point.based_on} />
                    </span>
                  </li>
                ))}
              </ul>
            </>
          )}

          {hidden > 0 && (
            <p className="faint" data-source-points-hidden={String(hidden)}>
              {/*
                Counted rather than dropped. The whole brief is in the drawer at
                every tier, so this is a statement about this card's height and
                not about the record.
              */}
              {t("source.bound.stage", { count: hidden })}
            </p>
          )}

          {!compact && brief.limitations_or_tensions.length > 0 && (
            <>
              <h3 className="sourcecard__label">{t("source.brief.limitations")}</h3>
              <ul className="sourcecard__points">
                {brief.limitations_or_tensions.map((point) => (
                  <li key={point.id}>
                    <Mono>{point.id}</Mono>
                    <span>
                      <Bidi>{point.content}</Bidi>
                      <BasedOn ids={point.based_on} />
                    </span>
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>
      )}

      {/*
        Out of the Map and into the records. Two links, and both are addresses
        the application already has: the Reader for the source itself, and the
        Knowledge Map scoped to this source for the units the brief rests on.
        Neither is a new route and neither invents an id.
      */}
      <div className="sourcecard__foot">
        {source.source_id !== null && source.source_id !== undefined && (
          <>
            <Link className="button" to={readerPath(source.source_id)}>
              {t("source.openReader")}
            </Link>
            <Link className="button" to={mapPath({ source: source.source_id })}>
              {t("source.openKnowledge")}
            </Link>
          </>
        )}
        <Mono>{source.source_id ?? source.global_id}</Mono>
      </div>
    </article>
  );
}
