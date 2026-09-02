/**
 * The bounded card constellation over the stage (`T-207`, D-132).
 *
 * One primary card for the selected entity, labelled active relations, and the
 * neighbour previews the density policy in `constellation.ts` could place --
 * anchored to their marks through `MapSession.nodePosition`, which is
 * Sigma's `graphToViewport` and the reason D-132 says a bounded overlay is
 * possible at all.
 *
 * **The overlay is presentation, and nothing else.** It has no buttons, no
 * links and no focusable element; it is `pointer-events: none`, so a click
 * passes through it to the mark underneath, and it is `aria-hidden`, because
 * every card here is a *duplicate view* of a row that already exists in the
 * complete related list beside it. That is a deliberate answer to two problems
 * D-132 and `T-208` name together: an overlay of HTML nodes that can be
 * focused builds a second accessibility tree over the same entities, and an
 * overlay that owns controls makes the canvas the only way to reach them. Here,
 * selecting a neighbour is a click on its mark (which reaches the *same*
 * `focusEntity` the rail's buttons call) or a button in the related list --
 * never something that exists only inside this overlay.
 *
 * So the stage answers "what is around this statement, and why is it worth
 * opening" at a glance, and the DOM answers it completely. Nothing is only
 * here.
 *
 * **Cards are placed in physical pixels, on purpose.** `left`/`top` rather
 * than `inset-inline-start`, which is the opposite of the rule everywhere else
 * in this stylesheet (D-012): these coordinates come out of the renderer's
 * viewport, and a logical inset would mirror the card away from its own mark
 * the moment the UI language became Persian. The card's *contents* are still
 * laid out logically, and the statement carries `dir="auto"`.
 *
 * **The text is the record's, cut by the one cutter.** `previewText` from
 * `MapResultCard` -- so a statement shortened on a card is shortened exactly
 * as it is in the rail, with the cut visible (D-131, §8.6).
 *
 * **The Peek is not here.** `MapPeekCard` is rendered in the search rail and
 * in exactly one place (invariant 13); hovering a mark on the canvas opens
 * that same one binding, and the mark itself answers immediately with the
 * hover state and the forced label `mapStyle` computes for it. Which surface
 * the transient card belongs on when the stage is narrow is a disclosure
 * question `T-208` owns.
 */

import type { CSSProperties } from "react";

import type { EntityRef } from "../api/contract";
import { useI18n } from "../i18n";
import type { StageCard, StagePlacement } from "../map/constellation";
import {
  MAP_STAGE_NEIGHBOUR_CHARS,
  MAP_STAGE_PRIMARY_CHARS,
} from "../map/constellation";
import { previewOfEntity } from "../map/useMapSearch";
import { PreviewStatement } from "./MapResultCard";
import { RelationCue } from "./MapRelation";
import { ProvenanceBadge } from "./Provenance";
import { Mono } from "./primitives";

/** Pixels between a mark and the card that points at it. */
const GAP = 12;

function anchorStyle(card: StageCard): CSSProperties {
  return {
    left: `${card.point.x}px`,
    top: `${card.point.y}px`,
    transform: `translate(${card.align === "end" ? `calc(-100% - ${GAP}px)` : `${GAP}px`}, ${
      card.above ? `calc(-100% - ${GAP}px)` : `${GAP}px`
    })`,
  };
}

/** One card on the stage: the record's own text, and what it is to the focus. */
function StageCardView({
  card,
  record,
  primary,
}: {
  card: StageCard;
  record: EntityRef;
  primary: boolean;
}) {
  const { t } = useI18n();
  const preview = previewOfEntity(record, { origin: "index", loaded: true });
  const relation = card.related?.toCentre[0] ?? null;

  return (
    <article
      className={`card stack map__card${primary ? " map__card--primary" : ""}${
        preview.provenance === null ? "" : ` card--${preview.provenance}`
      }`}
      style={anchorStyle(card)}
      data-map-card={card.globalId}
      data-map-card-primary={String(primary)}
      data-map-card-align={card.align}
    >
      <div className="row">
        <span className="badge">
          {primary ? t("map.stage.primary") : t("map.stage.neighbour")}
        </span>
        {preview.provenance !== null && <ProvenanceBadge provenance={preview.provenance} />}
        <span className="badge">{preview.kind ?? t("common.notStated")}</span>
      </div>

      <PreviewStatement
        text={preview.text}
        limit={primary ? MAP_STAGE_PRIMARY_CHARS : MAP_STAGE_NEIGHBOUR_CHARS}
      />

      {relation !== null && <RelationCue relation={relation} subject="this" />}
      {relation === null && !primary && card.related !== null && (
        <p className="faint">{t("map.related.viaPath", { hops: card.related.hops })}</p>
      )}
      <Mono>{card.globalId}</Mono>
    </article>
  );
}

export function MapConstellation({
  placement,
  centre,
}: {
  /** What the density policy decided, or `null` with nothing selected. */
  placement: StagePlacement | null;
  /** The selected entity's record, for the primary card. */
  centre: EntityRef | null;
}) {
  if (placement === null) return null;
  const cards = placement.cards.filter((card) => card.related !== null);
  if (placement.primary === null && cards.length === 0) return null;

  return (
    <div
      className="map__overlay"
      // Presentation over a canvas: every card here is a second view of a row
      // in the related list, and the marks underneath are what is selectable.
      aria-hidden="true"
      data-map-overlay={cards.length + (placement.primary === null ? 0 : 1)}
    >
      {placement.primary !== null && centre !== null && (
        <StageCardView card={placement.primary} record={centre} primary />
      )}
      {cards.map((card) => (
        <StageCardView
          key={card.globalId}
          card={card}
          // Non-null by the filter above: only the primary card carries no
          // related entity, and it is rendered separately.
          record={(card.related as NonNullable<StageCard["related"]>).record}
          primary={false}
        />
      ))}
    </div>
  );
}
