/**
 * One edge, with its vocabulary visible.
 *
 * Three vocabularies coexist and must stay distinguishable: the 16 canonical
 * relation types the extraction pipeline writes, the two synthetic edges
 * `library.py` adds (`derived_from`, `expresses_concept`), and free-form user
 * links. A synthetic edge is derived synthesis, never source evidence, so it
 * is labelled as such instead of being drawn like a canonical one.
 *
 * A `null` confidence is rendered as an absence, not as a zero. D-025 and
 * D-043 are both about exactly that: `library.py` used to write `0` -- the
 * *least* confident value -- for an edge whose unit stated nothing, and it has
 * stopped. The UI must not put the number back.
 */

import { Link } from "react-router-dom";

import type { IndexedRelation } from "../api/contract";
import { useI18n } from "../i18n";
import { formatConfidence, sourceIdOf } from "../lib/format";
import { ProvenanceBadge, VocabularyBadge } from "./Provenance";
import { InlineArrow, Missing, Mono } from "./primitives";

function Endpoint({ globalId }: { globalId: string }) {
  const owner = sourceIdOf(globalId);
  if (owner === null) return <Mono>{globalId}</Mono>;
  return (
    <Link to={`/sources/${encodeURIComponent(owner)}`}>
      <Mono>{globalId}</Mono>
    </Link>
  );
}

export function RelationRow({ relation }: { relation: IndexedRelation }) {
  const { t } = useI18n();
  const confidence = formatConfidence(relation.confidence);
  return (
    <article className={`card card--${relation.provenance_class} stack`} data-relation={relation.id}>
      <div className="row">
        <VocabularyBadge vocabulary={relation.relation_vocabulary} />
        <ProvenanceBadge provenance={relation.provenance_class} />
        <span className="faint">
          {t("reader.relations.confidence")}: {confidence ?? <Missing />}
        </span>
      </div>
      <div className="row">
        <Endpoint globalId={relation.from_id} />
        <InlineArrow />
        <strong>{relation.relation}</strong>
        <InlineArrow />
        <Endpoint globalId={relation.to_id} />
      </div>
      {relation.canonical_path != null && (
        <p className="faint">
          <Mono>{relation.canonical_path}</Mono>
        </p>
      )}
    </article>
  );
}
