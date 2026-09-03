/**
 * Provenance and status, never signalled by colour alone (`T-113`).
 *
 * ADR 0001 invariant 10 is the whole design brief for this module: `source`,
 * `derived` and `user` must be distinguishable by icon, label, or line style
 * as well as colour. So every badge here renders **three** independent
 * signals -- a glyph, a translated text label, and a border style
 * (`solid` / `dashed` / `dotted`) -- and colour is the fourth. Printed in
 * greyscale, or read by someone who cannot separate green from amber, the
 * distinction survives.
 *
 * The same rule is applied to run status, for a different reason. `PARTIAL`
 * and `FAIL` must be as legible as `PASS` and must never be coerced toward it
 * (ADR 0001 invariant 2), so each status carries its own glyph and word, and
 * `UNKNOWN` -- the file is absent or unreadable -- is a fourth state rather
 * than a missing one.
 */

import type { IndexedRelation, ProvenanceClass, RunStatus, Source } from "../api/contract";
import { useI18n } from "../i18n";
import { KIND_FAMILY_COLOUR, kindFamily } from "../map/mapStyle";
import type { MessageKey } from "../i18n";
import { DefinitionList, Missing, Mono } from "./primitives";

/** Glyph per provenance class. Distinct in shape, not only in colour. */
export const PROVENANCE_GLYPH: Record<ProvenanceClass, string> = {
  source: "◆",
  derived: "◇",
  user: "✎",
};

/** Border style per provenance class, mirroring the CSS tokens. */
export const PROVENANCE_LINE: Record<ProvenanceClass, "solid" | "dashed" | "dotted"> = {
  source: "solid",
  derived: "dashed",
  user: "dotted",
};

const PROVENANCE_LABEL: Record<ProvenanceClass, MessageKey> = {
  source: "provenance.source",
  derived: "provenance.derived",
  user: "provenance.user",
};

export function ProvenanceBadge({ provenance }: { provenance: ProvenanceClass }) {
  const { t } = useI18n();
  return (
    <span
      className={`badge provenance provenance--${provenance}`}
      data-provenance={provenance}
      data-line-style={PROVENANCE_LINE[provenance]}
    >
      <span className="badge__glyph" aria-hidden="true">
        {PROVENANCE_GLYPH[provenance]}
      </span>
      <span>{t(PROVENANCE_LABEL[provenance])}</span>
    </span>
  );
}

/**
 * A `kind`, with its family's hue as a small cue beside the word (`T-214`,
 * SPEC §6).
 *
 * The opposite rule to the badges above, and it needs saying: **hue is never
 * the cue here, it is a second one.** The kind is spelled out in the record's
 * own vocabulary — `claim`, `canonical_concept`, `actionable_experiment` — and
 * the swatch beside it is the colour that same entity's mark wears on the
 * stage, so a reader can carry one to the other. Cropped, printed in greyscale
 * or read by someone who cannot separate the twelve families, the word is
 * still there and nothing has been lost.
 *
 * It is deliberately **not** a card fill. A card tinted by kind reads as a
 * category with a status, and the only classification this project colours a
 * whole surface with is provenance — which is a fact about where a statement
 * came from, not about what sort of statement it is.
 *
 * The hue is `KIND_FAMILY_COLOUR`'s, which is Paul Tol's colourblind-safe
 * qualitative set and is the same table `MapLegend` explains and `mapStyle`
 * draws the mark with. One table, three readers.
 *
 * `null` is rendered as "not stated", never as a family: an absent `kind` is
 * `unstated`, which has a hue of its own precisely so it is not silently
 * folded into a real one.
 */
export function KindBadge({ kind }: { kind: string | null | undefined }) {
  const { t } = useI18n();
  const family = kindFamily(kind);
  const stated = kind !== null && kind !== undefined && kind !== "";
  return (
    <span className="badge" data-kind={kind ?? ""} data-kind-family={family}>
      <span
        className="badge__swatch"
        aria-hidden="true"
        style={{ background: KIND_FAMILY_COLOUR[family] }}
      />
      {stated ? kind : <span className="missing">{t("common.notStated")}</span>}
    </span>
  );
}

/** Glyph per run status. `UNKNOWN` is a state, not an absence of one. */
export const STATUS_GLYPH: Record<RunStatus, string> = {
  PASS: "✔",
  PARTIAL: "◐",
  FAIL: "✖",
  UNKNOWN: "?",
};

const STATUS_LABEL: Record<RunStatus, MessageKey> = {
  PASS: "status.PASS",
  PARTIAL: "status.PARTIAL",
  FAIL: "status.FAIL",
  UNKNOWN: "status.UNKNOWN",
};

/**
 * A run status exactly as the validator files report it.
 *
 * The value is copied through; nothing here maps `PARTIAL` or `FAIL` onto a
 * gentler word, and an unrecognised value is shown verbatim rather than being
 * rounded to `UNKNOWN`.
 */
export function StatusBadge({ status, label }: { status: RunStatus; label?: string }) {
  const { t } = useI18n();
  const known = status in STATUS_GLYPH;
  return (
    <span className={`badge status--${known ? status : "UNKNOWN"}`} data-status={status}>
      <span className="badge__glyph" aria-hidden="true">
        {known ? STATUS_GLYPH[status] : "?"}
      </span>
      <span>
        {label !== undefined ? `${label}: ` : ""}
        {known ? t(STATUS_LABEL[status]) : status}
      </span>
    </span>
  );
}

const VOCABULARY_LABEL: Record<IndexedRelation["relation_vocabulary"], MessageKey> = {
  canonical: "vocabulary.canonical",
  library_synthetic: "vocabulary.library_synthetic",
  user: "vocabulary.user",
};

/**
 * Which of the three edge vocabularies an edge belongs to.
 *
 * `derived_from` and `expresses_concept` are synthesised by `library.py` and
 * are deliberately outside the canonical relation vocabulary; the UI styles
 * them without pretending they are canonical evidence.
 */
export function VocabularyBadge({
  vocabulary,
}: {
  vocabulary: IndexedRelation["relation_vocabulary"];
}) {
  const { t } = useI18n();
  const glyph = vocabulary === "canonical" ? "─" : vocabulary === "library_synthetic" ? "┄" : "┈";
  return (
    <span className="badge" data-vocabulary={vocabulary}>
      <span className="badge__glyph" aria-hidden="true">
        {glyph}
      </span>
      <span>{t(VOCABULARY_LABEL[vocabulary])}</span>
    </span>
  );
}

/**
 * The three status values of a run, plus where they were read from.
 *
 * `validation`, `coverage` and `overall` are shown separately because they can
 * disagree -- the `fail-run` fixture has `coverage: PASS` under
 * `validation: FAIL` -- and collapsing them into one word would be the UI
 * deciding a run's status, which it must never do.
 */
export function RunStatusPanel({ source }: { source: Source }) {
  const { t } = useI18n();
  const status = source.status;
  return (
    <div className="stack">
      <div className="row">
        <StatusBadge status={status.overall} label={t("status.overall")} />
        <StatusBadge status={status.validation} label={t("status.validation")} />
        <StatusBadge status={status.coverage} label={t("status.coverage")} />
      </div>
      <DefinitionList
        entries={[
          {
            label: t("status.auditAttempts"),
            value:
              typeof status.audit_attempts === "number" ? (
                String(status.audit_attempts)
              ) : (
                <Missing reason="common.notRecorded" />
              ),
          },
          {
            label: t("status.validation"),
            value: status.validation_path ? <Mono>{status.validation_path}</Mono> : null,
          },
          {
            label: t("status.coverage"),
            value: status.coverage_path ? <Mono>{status.coverage_path}</Mono> : null,
          },
        ]}
      />
      <p className="faint">{t("status.note")}</p>
    </div>
  );
}
