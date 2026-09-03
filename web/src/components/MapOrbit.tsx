/**
 * The Directional Orbit over the field (`T-213`, ADR 0006 clause 3, D-152).
 *
 * The selected Knowledge Card at the centre, incoming relations to the inline
 * start, outgoing to the inline end, actual hop count as radial distance,
 * visible ports and horizontal relation pills. `placeOrbit` decided every
 * coordinate here; this file only draws what it decided, which is why the
 * composition can be asserted without a browser and why the picture is the
 * same on every run.
 *
 * It replaces `MapConstellation`, and the replacement is total: cards are no
 * longer pinned to the marks ForceAtlas placed, so they no longer move with
 * the camera, no longer vanish while it is moving, and no longer disappear
 * because a neighbour's page has not been loaded. What survives unchanged is
 * everything that made that overlay honest.
 *
 * **The overlay is presentation, and nothing else.** No buttons, no links, no
 * focusable element; `pointer-events: none`, so a click passes through to the
 * mark underneath and selection stays one identity; `aria-hidden`, because
 * every card here is a *duplicate view* of a row that already exists in the
 * complete related list beside it. Selecting a neighbour is a click on its
 * mark -- which reaches the same `focusEntity` the rail's buttons call -- or a
 * button in that list. Nothing is only here.
 *
 * **The graph underneath stays present and faint.** ADR 0006 asks unrelated
 * topology to recede as context rather than be represented as absent, so the
 * canvas keeps drawing the whole accumulated graph and the orbit is drawn over
 * it behind a scrim. Nothing is removed from the picture, and every mark on it
 * stays clickable: the orbit is a diagram *of the neighbourhood*, laid over
 * the picture *of the graph*, and the two are distinguished by the scrim and
 * the accent rather than by one deleting the other.
 *
 * **Placed in physical pixels, on purpose.** `left`/`top` rather than
 * `inset-inline-start`, which is the one deliberate exception to D-012 in this
 * route: the coordinates come out of a layout that has *already* mirrored --
 * `placeOrbit` takes `rtl` and swaps the sides itself -- so a logical inset
 * would mirror an already-mirrored coordinate. That is the defect D-191
 * carries forward from the mockups, and this is the comment that keeps it
 * fixed. Card *contents* are still laid out logically and the statement
 * carries `dir="auto"`.
 *
 * **The text is the record's, cut by the one cutter.** `previewOfEntity` and
 * `PreviewStatement`, so a statement shortened on a card is shortened exactly
 * as it is in the rail, with the cut visible (D-131, §8.6).
 */

import type { CSSProperties } from "react";

import type { EntityRef } from "../api/contract";
import { useI18n } from "../i18n";
import type { OrbitCard, OrbitEdge, OrbitPlacement } from "../map/constellation";
import {
  MAP_STAGE_CHIP_CHARS,
  MAP_STAGE_NEIGHBOUR_CHARS,
  MAP_STAGE_PRIMARY_CHARS,
  orbitCurve,
} from "../map/constellation";
import { previewOfEntity } from "../map/useMapSearch";
import { PreviewStatement } from "./MapResultCard";
import { RelationPill } from "./MapRelation";
import { KindBadge, ProvenanceBadge } from "./Provenance";
import { Mono } from "./primitives";

/** A card's own rectangle, written onto the element exactly as reserved. */
function cardStyle(card: OrbitCard): CSSProperties {
  return {
    left: `${card.rect.left}px`,
    top: `${card.rect.top}px`,
    inlineSize: `${card.rect.right - card.rect.left}px`,
  };
}

/** One card in the orbit: the record's own text, and what it is to the focus. */
function OrbitCardView({
  card,
  record,
  primary,
}: {
  card: OrbitCard;
  record: EntityRef;
  primary: boolean;
}) {
  const { t } = useI18n();
  const preview = previewOfEntity(record, { origin: "index", loaded: true });
  const budget = primary
    ? MAP_STAGE_PRIMARY_CHARS
    : card.chip
      ? MAP_STAGE_CHIP_CHARS
      : MAP_STAGE_NEIGHBOUR_CHARS;

  return (
    <article
      className={`card stack map__card${primary ? " map__card--primary" : ""}${
        card.chip ? " map__card--chip" : ""
      }${preview.provenance === null ? "" : ` card--${preview.provenance}`}`}
      style={cardStyle(card)}
      data-map-card={card.globalId}
      data-map-card-primary={String(primary)}
      data-map-card-hops={card.hops}
      data-map-card-side={card.side ?? "centre"}
    >
      <div className="row">
        <span className="badge">
          {primary ? t("map.stage.primary") : t("map.stage.neighbour")}
        </span>
        {preview.provenance !== null && <ProvenanceBadge provenance={preview.provenance} />}
        {!card.chip && <KindBadge kind={preview.kind} />}
        {card.hops > 1 && (
          <span className="badge">{t("map.orbit.hopBadge", { hops: card.hops })}</span>
        )}
      </div>

      <PreviewStatement text={preview.text} limit={budget} />

      {!card.chip && <Mono>{card.globalId}</Mono>}
    </article>
  );
}

/**
 * One relation, drawn from the card nearer the centre to the card it joins.
 *
 * The path, its two ports and the pill's leader are one `<g>`, so a relation
 * is one object in the picture as well as one record.
 */
function OrbitEdgeView({ edge }: { edge: OrbitEdge }) {
  const { p1, p2 } = orbitCurve(edge.from, edge.to);
  const far = edge.hops > 1;
  return (
    <g
      className={`map__orbit-edge${far ? " map__orbit-edge--far" : ""}`}
      data-orbit-edge={edge.key}
    >
      <path
        d={`M${edge.from.x},${edge.from.y} C${p1.x},${p1.y} ${p2.x},${p2.y} ${edge.to.x},${edge.to.y}`}
        fill="none"
        // A library-synthetic edge is dashed as well as badged: at this scale
        // a head is two pixels and the vocabulary distinction has to survive
        // (ADR 0005 invariant 9, SPEC §3).
        strokeDasharray={edge.vocabulary === "library_synthetic" ? "6 5" : undefined}
      />
      {[edge.from, edge.to].map((port, index) => (
        <circle key={index} className="map__orbit-port" cx={port.x} cy={port.y} />
      ))}
      {edge.pill.leader !== null && (
        <line
          className="map__orbit-leader"
          x1={edge.pill.leader.from.x}
          y1={edge.pill.leader.from.y}
          x2={edge.pill.leader.to.x}
          y2={edge.pill.leader.to.y}
        />
      )}
    </g>
  );
}

export function MapOrbit({
  placement,
  centre,
}: {
  /** What `placeOrbit` decided, or `null` with nothing to draw. */
  placement: OrbitPlacement | null;
  /** The selected entity's record, for the centre card. */
  centre: EntityRef | null;
}) {
  const { t } = useI18n();
  if (placement === null || placement.tier === "stack") return null;
  if (placement.centre === null || centre === null) return null;

  return (
    <div
      /*
        Both classes, and the first is load-bearing rather than legacy:
        `.map__overlay` is the *box* -- absolutely placed over the stage,
        clipped to it, taking no pointer events -- and every guard that keeps
        it presentation reads that name, in the stylesheet, in the scaffold
        test and in the browser gate. `.map__orbit` is what this composition
        adds inside it.
      */
      className="map__overlay map__orbit"
      // Presentation over a canvas: every card here is a second view of a row
      // in the related list, and the marks underneath are what is selectable.
      aria-hidden="true"
      data-map-overlay={placement.cards.length + 1}
      data-map-orbit-tier={placement.tier}
    >
      {/*
        The scrim. Unrelated topology stays present and faint rather than
        being removed -- the clause is "fade without representing as absent"
        -- and one translucent layer over the whole canvas is how that is done
        without a second style table deciding per node what the reader may
        still see.
      */}
      <div className="map__orbit-scrim" />

      <svg
        className="map__orbit-lines"
        viewBox={`0 0 ${placement.field.width} ${placement.field.height}`}
        width={placement.field.width}
        height={placement.field.height}
        focusable="false"
      >
        {placement.rings.map((ring) => (
          <ellipse
            key={ring.hop}
            className="map__orbit-ring"
            cx={ring.centre.x}
            cy={ring.centre.y}
            rx={ring.rx}
            ry={ring.ry}
            fill="none"
          />
        ))}
        {placement.edges.map((edge) => (
          <OrbitEdgeView key={edge.key} edge={edge} />
        ))}
      </svg>

      {/* Which side is which, in words: an arrow alone states position. */}
      {placement.sides.map((label) => (
        <div
          key={label.side}
          className="map__orbit-side"
          style={{ left: `${label.at.x}px`, top: `${label.at.y}px` }}
        >
          <strong>
            {label.side === "incoming" ? t("map.orbit.incoming") : t("map.orbit.outgoing")}
          </strong>
          <span className="faint">
            {label.side === "incoming"
              ? t("map.orbit.incomingGloss")
              : t("map.orbit.outgoingGloss")}
          </span>
        </div>
      ))}

      {/* Hop rings are labelled at the foot, on the vertical axis: at the top
          they shared a line with the side labels and the two ran together. */}
      {placement.rings.map((ring) => (
        <div
          key={ring.hop}
          className="map__orbit-ringlabel"
          style={{ left: `${ring.centre.x}px`, top: `${ring.centre.y + ring.ry + 14}px` }}
        >
          {t("map.orbit.ring", { hops: ring.hop })}
        </div>
      ))}

      <OrbitCardView card={placement.centre} record={centre} primary />
      {placement.cards.map((card) => (
        <OrbitCardView
          key={card.globalId}
          card={card}
          // Non-null by construction: only the centre carries no related
          // entity, and it is rendered above.
          record={(card.related as NonNullable<OrbitCard["related"]>).record}
          primary={false}
        />
      ))}

      {placement.edges.map((edge) => (
        <div
          key={edge.key}
          className={`map__pill${edge.hops > 1 ? " map__pill--far" : ""}`}
          style={{
            left: `${edge.pill.at.x}px`,
            top: `${edge.pill.at.y}px`,
            // Exactly the rectangle the seat was found for. The pill can
            // neither outgrow its own reservation nor be seated against a box
            // it does not fill.
            inlineSize: `${edge.pill.box.width}px`,
            blockSize: `${edge.pill.box.height}px`,
          }}
          data-orbit-pill={edge.key}
          data-orbit-pill-crowded={String(edge.pill.crowded)}
        >
          <RelationPill
            relation={edge.relation}
            direction={edge.direction}
            vocabulary={edge.vocabulary}
            nearId={edge.nearId}
          />
        </div>
      ))}
    </div>
  );
}
