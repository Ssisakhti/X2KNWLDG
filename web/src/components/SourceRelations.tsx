/**
 * Every relationship a selected source stands in, and what one of them rests on
 * (`T-256`).
 *
 * Two surfaces in one file because they are one reading: the list is what the
 * stage is a view of, and the basis panel is what a row expands into. Splitting
 * them would put the selection of a relationship in one file and its rendering
 * in another, which is the shape that let a Knowledge Map card and its pill
 * disagree about direction (D-193).
 *
 * **The list is the accessible path, not a summary of the drawn one.** Every
 * relationship the response returned is a row here — including the ones the
 * stage had no room for and the ones whose other end is not on the drawn page.
 * That is the phase's acceptance clause ("every returned relationship remains
 * text-accessible") and it is why the rows are buttons rather than decoration:
 * a reader with no pointer and no WebGL2 selects a relationship the same way a
 * reader with both does.
 *
 * **A basis is shown in full or is said to be cut.** `basis_returned` and
 * `basis_total` are both rendered whenever they differ, because a panel showing
 * only what it was given presents a truncated basis as the whole of it — risk
 * R27 arriving through the UI instead of through the API.
 */

import type { SourceRelationDetail } from "../api/contract";
import { useI18n } from "../i18n";
import { readerPath } from "../lib/readerLink";
import type { SourceEdgeView } from "../map/sourceNeighbourhood";
import { Bidi, InlineArrow, Mono } from "./primitives";
import { MediumBadge, RelationPill, SCOPE_LABEL } from "./SourceMarks";
import { Link } from "react-router-dom";

/**
 * One relationship's grounds.
 *
 * The rationale is the pass's own Persian sentence, rendered as written and
 * bidi-isolated: it sits beside Latin identifiers, and without isolation the
 * surrounding direction reorders its punctuation.
 */
export function SourceBasisPanel({ relation }: { relation: SourceRelationDetail }) {
  const { t } = useI18n();
  const truncated = relation.basis_returned < relation.basis_total;
  return (
    <section className="basis" data-source-basis={relation.id}>
      <h3 className="section__title">{t("source.basis.title")}</h3>

      <dl className="definitions">
        <dt>{t("source.relations.scope")}</dt>
        <dd>
          {t(SCOPE_LABEL[relation.scope])}
          <span className="faint"> — {t("source.relations.scopeNote")}</span>
        </dd>
        <dt>from_source_id</dt>
        <dd>
          <Mono>{relation.from_source_id}</Mono>
        </dd>
        <dt>to_source_id</dt>
        <dd>
          <Mono>{relation.to_source_id}</Mono>
        </dd>
        <dt>id</dt>
        <dd>
          <Mono>{relation.id}</Mono>
        </dd>
      </dl>

      <h4 className="section__title">{t("source.basis.rationale")}</h4>
      <Bidi as="p" className="basis__rationale">
        {relation.rationale}
      </Bidi>

      <h4 className="section__title">
        {t("source.basis.pairs")} ·{" "}
        {t("source.basis.count", {
          returned: relation.basis_returned,
          total: relation.basis_total,
        })}
      </h4>
      <ul className="basis__pairs">
        {relation.basis.map((pair, index) => (
          <li key={`${pair.from_ku_id}:${pair.to_ku_id}:${index}`}>
            <Mono>{pair.from_ku_id}</Mono>
            <span className="basis__arrow">
              <InlineArrow />
            </span>
            <Mono>{pair.to_ku_id}</Mono>
            <span className="basis__type">{pair.relation_type}</span>
          </li>
        ))}
      </ul>
      {truncated && (
        <p className="faint" data-source-basis-truncated>
          {t("source.basis.truncated", {
            returned: relation.basis_returned,
            total: relation.basis_total,
          })}
        </p>
      )}
      <p className="faint">{t("source.basis.note")}</p>
    </section>
  );
}

/**
 * Every returned relationship, as rows that select.
 *
 * `selected` is a relationship id rather than an index, for the reason every
 * identity in this application is the record's own: a list that re-orders — and
 * a bounded response may return a different page — would otherwise move the
 * selection to a different relationship without anything having been clicked.
 */
export function SourceRelationList({
  edges,
  selected,
  onSelect,
  onFocusSource,
  placed,
}: {
  edges: readonly SourceEdgeView[];
  selected: string | null;
  onSelect: (relationId: string) => void;
  onFocusSource: (globalId: string) => void;
  /** Which relationship ids the stage found room for, so a row can say so. */
  placed: ReadonlySet<string>;
}) {
  const { t } = useI18n();
  if (edges.length === 0) {
    return (
      <p className="muted" data-source-relations="0">
        {t("source.relations.none")}
      </p>
    );
  }
  return (
    <ul className="relationlist" data-source-relations={String(edges.length)}>
      {edges.map((edge) => {
        const isSelected = selected === edge.relation.id;
        return (
          <li
            key={edge.relation.id}
            data-source-relation-row={edge.relation.id}
            data-source-relation-placed={String(placed.has(edge.relation.id))}
          >
            <button
              type="button"
              className={`relationlist__select${isSelected ? " relationlist__select--on" : ""}`}
              aria-pressed={isSelected}
              onClick={() => onSelect(edge.relation.id)}
            >
              <span className="visually-hidden">
                {isSelected ? t("source.relations.selected") : t("source.relations.select")}:{" "}
              </span>
              <RelationPill
                relation={edge.relation}
                direction={edge.direction}
                variant="row"
              />
            </button>

            {/*
              The other end, named and reachable. A relationship whose endpoint
              the page did not draw still has an id and still has a record here,
              so it is still a place a reader can go — which is what keeps the
              list from being a view of the drawing rather than of the response.
            */}
            {edge.other !== null ? (
              <button
                type="button"
                className="relationlist__other"
                onClick={() => onFocusSource(edge.other!.global_id)}
              >
                <MediumBadge sourceType={edge.other.source_type} />
                <Bidi>{edge.other.label}</Bidi>
              </button>
            ) : (
              <span className="relationlist__other">
                <Mono>{edge.otherSourceId}</Mono>
              </span>
            )}
          </li>
        );
      })}
    </ul>
  );
}

/**
 * The Reader link for one knowledge unit named in a basis.
 *
 * Exported rather than inlined because a basis pair names units in *two*
 * different sources — `from_ku_id` belongs to one end and `to_ku_id` to the
 * other — and the link a reader needs depends on which. The panel above does
 * not draw these yet: resolving a unit id to its source needs the endpoint the
 * pair belongs to, which the detail record states, and `T-257`'s walk is where
 * that journey is measured rather than assumed.
 */
export function UnitReaderLink({ sourceId, unitId }: { sourceId: string; unitId: string }) {
  const { t } = useI18n();
  return (
    <Link className="button button--quiet" to={readerPath(sourceId, { tab: "units" })}>
      {t("source.basis.openUnit", { id: unitId })}
    </Link>
  );
}
