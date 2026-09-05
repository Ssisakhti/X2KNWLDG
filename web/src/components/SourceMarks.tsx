/**
 * The Source Map's badges and pills (`T-256`).
 *
 * Every distinction the field draws is repeated here in words, which is the
 * whole reason this file is separate from the style table: a mark on a canvas
 * is unreadable to a screen reader, unavailable with no WebGL2 and ambiguous in
 * greyscale, so each of the three added channels — medium, brief state, scope —
 * has a DOM counterpart that says it in text. `sourceStyle.ts` draws them;
 * this states them.
 *
 * The glyph beside each word is the same one the legend and the canvas use, and
 * it is `aria-hidden`: it is a second visual channel for a sighted reader, not a
 * second reading for someone who is already being told the word.
 */

import type { SourceRelationSummary } from "../api/contract";
import { useI18n } from "../i18n";
import type { MessageKey } from "../i18n/catalog";
import { sourceMediumMark, type BriefState } from "../map/sourceStyle";
import { InlineArrow, Mono } from "./primitives";

/*
 * Every key spelled in full, in a table.
 *
 * `t(`source.medium.${value}`)` is one character away from naming a key that
 * does not exist, and `MessageKey` cannot catch it because the type is erased
 * by the interpolation — so the cast that makes it compile is the cast that
 * hides the bug. `tests/test_ui_scaffold.py` reads these literals to prove no
 * translated string is rendered by nothing, and it cannot read a template.
 * `Provenance.tsx`'s `STATUS_LABEL` is the same shape for the same reason.
 */
const MEDIUM_LABEL: Record<string, MessageKey> = {
  youtube: "source.medium.youtube",
  twitter: "source.medium.twitter",
};

const BRIEF_LABEL: Record<BriefState, MessageKey> = {
  available: "source.brief.available",
  stale: "source.brief.stale",
  unavailable: "source.brief.unavailable",
};

export const SCOPE_LABEL: Record<"partial" | "broad", MessageKey> = {
  partial: "source.relations.scope.partial",
  broad: "source.relations.scope.broad",
};

const DIRECTION_LABEL: Record<"incoming" | "outgoing", MessageKey> = {
  incoming: "source.relations.incoming",
  outgoing: "source.relations.outgoing",
};

/** The medium a source was acquired from. */
export function MediumBadge({ sourceType }: { sourceType: string | null | undefined }) {
  const { t } = useI18n();
  const mark = sourceMediumMark(sourceType);
  const label = sourceType === null || sourceType === undefined ? undefined : MEDIUM_LABEL[sourceType];
  return (
    <span
      className="badge badge--medium"
      style={{ "--medium-hue": mark.colour } as Record<string, string>}
      data-source-medium={sourceType ?? "unknown"}
    >
      <span aria-hidden="true" className="badge__glyph">
        {mark.glyph}
      </span>{" "}
      {label === undefined ? t("source.medium.unknown") : t(label)}
    </span>
  );
}

/**
 * Whether this source has a brief, and whether it is current.
 *
 * Three states and three words. `unavailable` is deliberately "none" rather
 * than "missing": a run that did not pass cannot have a brief, so an absent one
 * is a normal and possibly permanent condition rather than something that went
 * wrong (D-257).
 */
export function BriefStateBadge({ state }: { state: BriefState }) {
  const { t } = useI18n();
  return (
    <span className={`badge badge--brief badge--brief-${state}`} data-source-brief={state}>
      {t("source.brief.state")}: {t(BRIEF_LABEL[state])}
    </span>
  );
}

/**
 * One relationship, in words.
 *
 * Direction is a word and an arrow rather than an arrow alone, and the arrow
 * mirrors with the script while the words do not move: `incoming` and
 * `outgoing` are read from the response and are facts about the record, not
 * about which side of a field a card sits on.
 *
 * The basis count is a **count**. It is written as a count, next to the pairs it
 * counts, and nothing here scales, sorts or colours anything by it (D-247).
 */
export function RelationPill({
  relation,
  direction,
  variant = "row",
}: {
  relation: Pick<SourceRelationSummary, "relation_type" | "scope"> & { basis_total?: number };
  direction: "incoming" | "outgoing";
  /** `row` carries the basis count; `mark` is the compact form for a card head. */
  variant?: "row" | "mark";
}) {
  const { t } = useI18n();
  const near = <span className="relpill__focus">{t("source.one")}</span>;
  const name = <strong className="relpill__vocab">{relation.relation_type}</strong>;
  return (
    <span className={`relpill relpill--${variant}`} data-source-relation={relation.relation_type}>
      {/*
        The two ends in reading order. A screen reader gets the same sentence a
        sighted reader does, because the order of the nodes is the order of the
        words rather than a visual arrangement over a fixed order.
      */}
      {/*
        The arrow is `InlineArrow`, never a literal: D-203 records what a bare
        U+2192 does here. A flex row reverses under `dir="rtl"`, so the two ends
        land in the right order — and the glyph does not mirror with them, so
        both arrows went on pointing at the wrong end. The stylesheet mirrors
        this one.
      */}
      {direction === "incoming" ? (
        <>
          {name}
          <InlineArrow />
          {near}
        </>
      ) : (
        <>
          {near}
          <InlineArrow />
          {name}
        </>
      )}
      <span className="visually-hidden">
        {" "}
        · {t(DIRECTION_LABEL[direction])}
      </span>
      <span className="relpill__scope">
        {t(SCOPE_LABEL[relation.scope])}
      </span>
      {variant === "row" && relation.basis_total !== undefined && (
        <span className="relpill__basis">
          {relation.basis_total} {t("source.basis.pairs")}
        </span>
      )}
    </span>
  );
}

/** One knowledge-unit id, as the chip that says a statement rests on it. */
export function UnitChip({ id }: { id: string }) {
  return (
    <span className="basedon__chip">
      <Mono>{id}</Mono>
    </span>
  );
}

/**
 * The knowledge units a narrative element rests on.
 *
 * Drawn rather than described, because "every statement names its supporting
 * knowledge units" is one of the phase's acceptance clauses and a clause that
 * is only true in the record is a clause the reader cannot check.
 */
export function BasedOn({ ids }: { ids: readonly string[] }) {
  const { t } = useI18n();
  if (ids.length === 0) return null;
  return (
    <span className="basedon">
      <span className="visually-hidden">
        {ids.length === 1
          ? t("source.brief.basedOnOne", { count: ids.length })
          : t("source.brief.basedOnMany", { count: ids.length })}
        :{" "}
      </span>
      {ids.map((id) => (
        <UnitChip key={id} id={id} />
      ))}
    </span>
  );
}
