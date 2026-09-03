/**
 * One connection, named (`T-207`, D-132).
 *
 * "An active connection names its real relation and direction" is a `T-207`
 * acceptance criterion, and this is the one place it is rendered -- the stage
 * card, the related row and Quick Read all use this component, so a relation
 * cannot be described one way beside a mark and another way in a list.
 *
 * Three things are stated and none of them is computed:
 *
 * - **The relation, verbatim.** `IndexedRelation.relation` is the pipeline's
 *   own token (`supports`, `contradicts`) or one of `library.py`'s two
 *   synthetic ones (`derived_from`, `expresses_concept`), and a user relation
 *   is free-form text. It is printed as it is stored, never prettified into a
 *   phrase, because the vocabulary *is* the evidence.
 * - **The direction, structurally.** The endpoints are laid out in the record's
 *   own `from_id -> to_id` order, so the direction is visible from the reading
 *   order rather than from an arrow alone. The arrow is decoration and is
 *   hidden from the accessibility tree; the order is not.
 * - **The vocabulary and the provenance, as badges.** A `library_synthetic`
 *   edge is derived synthesis and not source evidence -- 62 of the real graph's
 *   118 edges are -- so it says so beside the relation instead of looking like
 *   a canonical one (D-006, ADR 0005 invariant 9).
 *
 * The endpoint the reader is already looking at is rendered as a *word* rather
 * than as its id: a row inside the card for `KU-000002` that spells
 * `KU-000002` on one side of the arrow makes the reader compare two long ids
 * to find out which way the relation runs.
 */

import { MAP_EDGE_LABEL_CHARS, cutToBudget } from "../map/labelPolicy";
import type { ActiveRelation, RelationDirection } from "../map/neighbourhood";
import { useI18n } from "../i18n";
import { formatConfidence } from "../lib/format";
import { ProvenanceBadge, VocabularyBadge } from "./Provenance";
import { Bidi, InlineArrow, Missing, Mono } from "./primitives";

/** Which endpoint is "the one being looked at", in words. */
export type RelationSubject = "this" | "focus";

export function RelationCue({
  relation,
  subject = "this",
  confidence = false,
}: {
  relation: ActiveRelation;
  /** Whether the shared endpoint is the card's own entity or the focus. */
  subject?: RelationSubject;
  /** Show the recorded confidence. Off in a dense list, on in Quick Read. */
  confidence?: boolean;
}) {
  const { t } = useI18n();
  const { record, direction, otherId } = relation;
  // Spelled out rather than built from `subject`, because a computed
  // catalogue key defeats the guard that tells a shipped string from an
  // abandoned one (§8.6).
  const self = subject === "focus" ? t("map.relation.theFocus") : t("map.relation.thisEntity");
  const near = <strong>{self}</strong>;
  const far = <Mono>{otherId}</Mono>;

  return (
    <span
      className="row map__relation"
      data-relation={record.id}
      data-relation-direction={direction}
    >
      <VocabularyBadge vocabulary={record.relation_vocabulary} />
      <ProvenanceBadge provenance={record.provenance_class} />
      {direction === "incoming" ? far : near}
      <InlineArrow />
      <Bidi>{record.relation}</Bidi>
      <InlineArrow />
      {direction === "incoming" ? near : far}
      {direction === "self" && <span className="faint">{t("map.relation.self")}</span>}
      {confidence && (
        <span className="faint">
          {t("reader.relations.confidence")}: {formatConfidence(record.confidence) ?? <Missing />}
        </span>
      )}
    </span>
  );
}

/**
 * The same connection as a horizontal pill, for the Directional Orbit
 * (`T-213`, SPEC §4).
 *
 * Here rather than in a second module, because this file is *the* place a
 * relation is named: a pill that glossed or ordered the vocabulary differently
 * from `RelationCue` would describe one edge two ways on one screen. What it
 * changes is only what a diagram can carry -- the endpoint nearer the centre
 * is a word or a `local_id` instead of a full identifier, and the badges are
 * one glyph instead of two labels.
 *
 * **Direction is spelled out, not implied by side.** A bare arrow is the same
 * glyph on both sides -- the relation flows towards the reading end *into* the
 * focus on one side and *out of* it on the other -- so an arrow alone states
 * position, not direction. The pill reads `exemplifies -> focus` or
 * `focus -> supports`, and the order mirrors with the script because the
 * elements are laid out logically.
 *
 * **The near end of a hop-2 relation is its parent, not the focus.** `nearId`
 * carries that name; naming the focus there would state a relation the records
 * do not contain.
 */
export function RelationPill({
  relation,
  direction,
  vocabulary,
  nearId,
}: {
  /** The relation as the record spells it. Never prettified. */
  relation: string;
  direction: RelationDirection;
  vocabulary: string | null;
  /** The endpoint nearer the centre: a `local_id`, or `null` for the focus. */
  nearId: string | null;
}) {
  const { t } = useI18n();
  const cut = cutToBudget(relation, MAP_EDGE_LABEL_CHARS);
  const name = (
    <strong className="map__pill-name">
      {cut.shown ?? relation}
      {cut.truncated && <span aria-hidden="true">…</span>}
    </strong>
  );
  const near = (
    <span className="map__pill-near">
      {nearId === null ? t("map.orbit.focus") : nearId}
    </span>
  );
  // The same mirrored glyph as the cue above (D-203): a horizontal pill's
  // items reverse under `dir="rtl"` and U+2192 does not, so the pill named the
  // relation and then pointed the wrong way along it. This site is a fourth
  // one the audit did not name; `primitives.test.tsx` sweeps for the bare
  // glyph so a fifth cannot appear unnoticed.
  const arrow = <InlineArrow />;

  return (
    <span className="row map__pill-body" data-relation-direction={direction}>
      {direction === "incoming" ? (
        <>
          {name}
          {arrow}
          {near}
        </>
      ) : (
        <>
          {near}
          {arrow}
          {name}
        </>
      )}
      <span className="map__pill-vocab" aria-hidden="true">
        {vocabulary === "canonical" ? "◆" : "◇"}
      </span>
    </span>
  );
}

/** Every relation of one entity, or a stated absence. */
export function RelationCues({
  relations,
  subject = "this",
  empty,
  confidence = false,
}: {
  relations: readonly ActiveRelation[];
  subject?: RelationSubject;
  /** What to say when there is none. An absence is rendered, never skipped. */
  empty: string;
  confidence?: boolean;
}) {
  if (relations.length === 0) return <p className="faint">{empty}</p>;
  return (
    <ul className="stack map__list">
      {relations.map((relation) => (
        <li key={relation.record.id}>
          <RelationCue relation={relation} subject={subject} confidence={confidence} />
        </li>
      ))}
    </ul>
  );
}
